"""Bản giả lập Google Drive API v3 (httplib2-compatible) cho test M1 – không gọi Drive thật.

Hỗ trợ: files.list/create/get/update/delete, tải nội dung (alt=media + Range),
resumable upload (POST tạo phiên, PUT từng phần, hỏi trạng thái, DELETE hủy phiên).
Mọi request được ghi vào `requests` để kiểm tra `supportsAllDrives=true`, `Content-Range`...
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlsplit

import httplib2

API_PREFIX = "/drive/v3/files"
UPLOAD_PREFIX = "/upload/drive/v3/files"
GRANULARITY = 256 * 1024


@dataclass
class RecordedRequest:
    method: str
    uri: str
    headers: dict
    body_size: int

    @property
    def query(self) -> dict:
        return {k: v[0] for k, v in parse_qs(urlsplit(self.uri).query).items()}


@dataclass
class UploadState:
    metadata: dict
    total: int
    data: bytearray = field(default_factory=bytearray)
    file_id: str | None = None


def _resp(status: int, headers: dict | None = None) -> httplib2.Response:
    info = {"status": str(status)}
    info.update({k.lower(): v for k, v in (headers or {}).items()})
    return httplib2.Response(info)


def _json(status: int, payload: dict, headers: dict | None = None):
    hdrs = {"content-type": "application/json; charset=UTF-8"}
    hdrs.update(headers or {})
    return _resp(status, hdrs), json.dumps(payload).encode("utf-8")


def _error(status: int, reason: str = "error", message: str = "fake error"):
    return _json(
        status,
        {"error": {"code": status, "message": message, "errors": [{"reason": reason}]}},
    )


class FakeDrive:
    def __init__(self, drive_id: str = "drive123", *, return_sha256: bool = True):
        self.drive_id = drive_id
        self.return_sha256 = return_sha256
        self.files: dict[str, dict] = {
            drive_id: {
                "id": drive_id,
                "name": "NXB Shared Drive",
                "mimeType": "application/vnd.google-apps.folder",
                "driveId": drive_id,
                "parents": [],
                "trashed": False,
                "appProperties": {},
            }
        }
        self.sessions: dict[str, UploadState] = {}
        self.requests: list[RecordedRequest] = []
        self._failures: list[tuple] = []
        self._counter = 0

    # ------------------------------------------------------------ test helpers
    def fail_next(
        self,
        count: int,
        status: int = 503,
        *,
        method=None,
        path_contains=None,
        reason="backendError",
    ):
        """Trả lỗi `status` cho `count` request kế tiếp khớp điều kiện."""
        for _ in range(count):
            self._failures.append((method, path_contains, status, reason))

    def add_file(self, content: bytes = b"data", **meta) -> str:
        file_id = meta.pop("id", None) or self._new_id()
        self.files[file_id] = {
            "id": file_id,
            "name": meta.pop("name", "file.pdf"),
            "mimeType": meta.pop("mimeType", "application/pdf"),
            "driveId": meta.pop("driveId", self.drive_id),
            "parents": meta.pop("parents", [self.drive_id]),
            "trashed": meta.pop("trashed", False),
            "appProperties": meta.pop("appProperties", {}),
            "content": content,
        }
        return file_id

    def upload_requests(self) -> list[RecordedRequest]:
        return [
            r
            for r in self.requests
            if r.method == "PUT" and "upload_id=" in r.uri and r.body_size > 0
        ]

    def folders(self) -> list[dict]:
        return [
            f
            for f in self.files.values()
            if f["mimeType"].endswith(".folder") and f["id"] != self.drive_id
        ]

    def path_of(self, file_id: str) -> str:
        parts = []
        current = self.files[file_id]
        while current["parents"] and current["parents"][0] != self.drive_id:
            parts.append(current["name"])
            current = self.files[current["parents"][0]]
        parts.append(current["name"])
        return "/".join(reversed(parts))

    # ------------------------------------------------------------ httplib2 API
    def request(self, uri, method="GET", body=None, headers=None, *args, **kwargs):
        headers = {k.lower(): v for k, v in (headers or {}).items()}
        if isinstance(body, str):
            body = body.encode("utf-8")
        body = body or b""
        self.requests.append(RecordedRequest(method, uri, headers, len(body)))

        parts = urlsplit(uri)
        for i, (f_method, f_path, status, reason) in enumerate(self._failures):
            if (f_method is None or f_method == method) and (f_path is None or f_path in uri):
                self._failures.pop(i)
                return _error(status, reason)

        query = {k: v[0] for k, v in parse_qs(parts.query).items()}
        path = parts.path
        if path.startswith(UPLOAD_PREFIX):
            return self._upload(method, query, headers, body, uri)
        if path.startswith(API_PREFIX):
            rest = path[len(API_PREFIX) :].strip("/")
            if not rest:
                if method == "GET":
                    return self._list(query)
                if method == "POST":
                    return self._create(json.loads(body or b"{}"))
            file_id = rest
            if file_id not in self.files:
                return _error(404, "notFound", f"File not found: {file_id}")
            if method == "GET" and query.get("alt") == "media":
                return self._media(file_id, headers)
            if method == "GET":
                return _json(200, self._public(self.files[file_id]))
            if method == "PATCH":
                self.files[file_id].update(json.loads(body or b"{}"))
                return _json(200, self._public(self.files[file_id]))
            if method == "DELETE":
                del self.files[file_id]
                return _resp(204), b""
        return _error(400, "badRequest", f"unsupported {method} {uri}")

    # ------------------------------------------------------------ internals
    def _new_id(self) -> str:
        self._counter += 1
        return f"fid{self._counter:04d}{uuid.uuid4().hex[:8]}"

    def _public(self, f: dict) -> dict:
        out = {k: v for k, v in f.items() if k != "content"}
        if "content" in f:
            out["size"] = str(len(f["content"]))
            if self.return_sha256:
                out["sha256Checksum"] = hashlib.sha256(f["content"]).hexdigest()
        return out

    def _list(self, query: dict):
        q = query.get("q", "")
        parents = re.findall(r"'([^']+)' in parents", q)
        props = dict(re.findall(r"key='([^']*)' and value='([^']*)'", q))
        result = []
        for f in self.files.values():
            if f["id"] == self.drive_id or f["driveId"] != query.get("driveId"):
                continue
            if "trashed=false" in q and f["trashed"]:
                continue
            if "mimeType='application/vnd.google-apps.folder'" in q and not f["mimeType"].endswith(
                ".folder"
            ):
                continue
            if parents and parents[0] not in f["parents"]:
                continue
            if any(f["appProperties"].get(k) != v for k, v in props.items()):
                continue
            result.append({"id": f["id"], "name": f["name"]})
        return _json(200, {"files": result[: int(query.get("pageSize", 100))]})

    def _create(self, meta: dict):
        file_id = self._new_id()
        self.files[file_id] = {
            "id": file_id,
            "name": meta.get("name", ""),
            "mimeType": meta.get("mimeType", "application/octet-stream"),
            "driveId": self.drive_id,
            "parents": meta.get("parents", [self.drive_id]),
            "trashed": False,
            "appProperties": meta.get("appProperties", {}),
        }
        return _json(200, {"id": file_id})

    def _media(self, file_id: str, headers: dict):
        content = self.files[file_id].get("content", b"")
        rng = headers.get("range")
        if not rng:
            return _resp(200), content
        start, end = (int(x) for x in re.match(r"bytes=(\d+)-(\d+)", rng).groups())
        if start >= len(content):
            return _resp(416, {"content-range": f"bytes */{len(content)}"}), b""
        end = min(end, len(content) - 1)
        return (
            _resp(206, {"content-range": f"bytes {start}-{end}/{len(content)}"}),
            content[start : end + 1],
        )

    def _upload(self, method, query, headers, body, uri):
        if method == "POST" and query.get("uploadType") == "resumable":
            upload_id = uuid.uuid4().hex
            self.sessions[upload_id] = UploadState(
                metadata=json.loads(body or b"{}"),
                total=int(headers.get("x-upload-content-length", 0)),
            )
            location = (
                "https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable"
                f"&supportsAllDrives=true&upload_id={upload_id}"
            )
            return _resp(200, {"location": location}), b""

        upload_id = query.get("upload_id")
        state = self.sessions.get(upload_id)
        if state is None:
            return _error(404, "notFound", "upload session not found")
        if method == "DELETE":
            del self.sessions[upload_id]
            return _resp(499), b""
        if method != "PUT":
            return _error(400)

        content_range = headers.get("content-range", "")
        status_query = re.match(r"bytes \*/(\d+|\*)", content_range)
        if status_query:
            return self._upload_status(state)

        m = re.match(r"bytes (\d+)-(\d+)/(\d+)", content_range)
        if not m:
            return _error(400, "badContentRange")
        start, end, total = (int(x) for x in m.groups())
        if start != len(state.data) or end - start + 1 != len(body) or total != state.total:
            return _error(400, "badContentRange", f"range {content_range} vs {len(state.data)}")
        if end + 1 < total and len(body) % GRANULARITY != 0:
            return _error(400, "badChunkSize", "chunk must be multiple of 256 KiB")
        state.data.extend(body)
        if len(state.data) < total:
            return _resp(308, {"range": f"bytes=0-{len(state.data) - 1}"}), b""
        return self._finalize(state)

    def _upload_status(self, state: UploadState):
        if state.file_id:
            return _json(200, {"id": state.file_id, "name": state.metadata.get("name")})
        if not state.data:
            return _resp(308), b""
        return _resp(308, {"range": f"bytes=0-{len(state.data) - 1}"}), b""

    def _finalize(self, state: UploadState):
        if state.file_id is None:
            meta = dict(state.metadata)
            state.file_id = self.add_file(
                bytes(state.data),
                name=meta.get("name", ""),
                mimeType=meta.get("mimeType", "application/octet-stream"),
                parents=meta.get("parents", [self.drive_id]),
                appProperties=meta.get("appProperties", {}),
            )
        return _json(200, {"id": state.file_id, "name": state.metadata.get("name")})
