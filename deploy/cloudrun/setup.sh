#!/usr/bin/env bash
# =============================================================================
# Triển khai UEH Publishing Portal V2 lên Google Cloud Run (chạy trong Cloud Shell)
#
#   bash deploy/cloudrun/setup.sh
#
# - Chạy lại bao nhiêu lần cũng được: bước nào đã làm thì bỏ qua, giá trị nào
#   để trống thì giữ nguyên giá trị cũ. Dùng lại lệnh này để cập nhật code mới.
# - Mật khẩu/khóa bí mật chỉ được đưa thẳng vào Secret Manager, không in ra màn hình,
#   không lưu vào file.
# =============================================================================
set -euo pipefail

CONFIG_FILE="${HOME}/.ueh-portal.env"
REGION="asia-southeast1"
SERVICE="ueh-portal"
JOB="ueh-portal-lenh"
SQL_INSTANCE="ueh-portal-db"
DB_NAME="ueh_portal"
DB_USER="ueh_portal"
RUN_SA_NAME="ueh-portal-run"

say()  { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
ok()   { printf '\033[1;32m    ✓ %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m    ! %s\033[0m\n' "$*"; }

# ---- Đọc cấu hình đã lưu từ lần chạy trước ---------------------------------
PROJECT_ID="" ADMIN_EMAILS="" GDRIVE_SHARED_DRIVE_ID="" GOOGLE_OAUTH_CLIENT_ID=""
# shellcheck disable=SC1090
[ -f "$CONFIG_FILE" ] && source "$CONFIG_FILE"

ask() { # ask BIEN "Câu hỏi"
  local var="$1" prompt="$2" cur="${!1:-}" input
  if [ -n "$cur" ]; then read -r -p "$prompt [Enter = giữ: $cur]: " input; else read -r -p "$prompt: " input; fi
  printf -v "$var" '%s' "${input:-$cur}"
}

secret_exists() { gcloud secrets describe "$1" --project "$PROJECT_ID" >/dev/null 2>&1; }
put_secret() { # put_secret TEN  (đọc giá trị từ stdin)
  if secret_exists "$1"; then
    gcloud secrets versions add "$1" --data-file=- --project "$PROJECT_ID" >/dev/null
  else
    gcloud secrets create "$1" --data-file=- --replication-policy=automatic --project "$PROJECT_ID" >/dev/null
  fi
}

say "1/8 Thông tin dự án"
ask PROJECT_ID "Mã dự án Google Cloud (Project ID)"
ask ADMIN_EMAILS "Email @ueh.edu.vn của Quản trị viên (tối đa 2, cách nhau dấu phẩy)"
ask GDRIVE_SHARED_DRIVE_ID "Mã Shared Drive lưu tài liệu (Enter để bỏ qua nếu chưa có)"
ask GOOGLE_OAUTH_CLIENT_ID "Client ID đăng nhập Google (Enter để bỏ qua nếu chưa có)"
cat >"$CONFIG_FILE" <<EOF
PROJECT_ID="$PROJECT_ID"
ADMIN_EMAILS="$ADMIN_EMAILS"
GDRIVE_SHARED_DRIVE_ID="$GDRIVE_SHARED_DRIVE_ID"
GOOGLE_OAUTH_CLIENT_ID="$GOOGLE_OAUTH_CLIENT_ID"
EOF
ADMIN_EMAILS="${ADMIN_EMAILS// /}"
if [[ "$PROJECT_ID" =~ ^[0-9]+$ ]]; then
  echo "Lỗi: đây là SỐ dự án. Hãy nhập MÃ dự án dạng chữ (ví dụ ueh-publishing-portal)."; rm -f "$CONFIG_FILE"; exit 1
fi
IFS=',' read -r -a _admins <<<"$ADMIN_EMAILS"
for _e in "${_admins[@]}"; do
  if [[ "$_e" != *@ueh.edu.vn ]]; then
    echo "Lỗi: email Quản trị viên '$_e' phải có đuôi @ueh.edu.vn."; rm -f "$CONFIG_FILE"; exit 1
  fi
done
gcloud config set project "$PROJECT_ID" >/dev/null
RUN_SA="${RUN_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
ok "Dự án: $PROJECT_ID – vùng: $REGION"

say "2/8 Bật các dịch vụ Google Cloud cần dùng (lần đầu mất 1–2 phút)"
gcloud services enable run.googleapis.com sqladmin.googleapis.com secretmanager.googleapis.com \
  cloudbuild.googleapis.com artifactregistry.googleapis.com storage.googleapis.com drive.googleapis.com iam.googleapis.com
ok "Đã bật"

say "3/8 Tài khoản máy (service account) của Portal"
if ! gcloud iam service-accounts describe "$RUN_SA" >/dev/null 2>&1; then
  gcloud iam service-accounts create "$RUN_SA_NAME" --display-name "UEH Portal NXB"
fi
for role in roles/cloudsql.client roles/secretmanager.secretAccessor; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" --member "serviceAccount:$RUN_SA" \
    --role "$role" --condition=None >/dev/null
done
# Quyền đóng gói mã nguồn (Cloud Build dùng tài khoản máy mặc định của dự án)
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member "serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
  --role roles/run.builder --condition=None >/dev/null
ok "Tài khoản máy: $RUN_SA"

say "4/8 Cơ sở dữ liệu PostgreSQL (lần đầu mất khoảng 10 phút)"
if ! gcloud sql instances describe "$SQL_INSTANCE" >/dev/null 2>&1; then
  gcloud sql instances create "$SQL_INSTANCE" --database-version=POSTGRES_16 \
    --edition=ENTERPRISE --tier=db-f1-micro --region="$REGION" \
    --storage-size=10 --storage-auto-increase --backup-start-time=18:00
fi
gcloud sql databases describe "$DB_NAME" --instance "$SQL_INSTANCE" >/dev/null 2>&1 \
  || gcloud sql databases create "$DB_NAME" --instance "$SQL_INSTANCE"
CONN_NAME="$(gcloud sql instances describe "$SQL_INSTANCE" --format='value(connectionName)')"
if ! secret_exists DATABASE_URL; then
  DB_PASS="$(openssl rand -hex 24)"
  if gcloud sql users list --instance "$SQL_INSTANCE" --format='value(name)' | grep -qx "$DB_USER"; then
    gcloud sql users set-password "$DB_USER" --instance "$SQL_INSTANCE" --password "$DB_PASS"
  else
    gcloud sql users create "$DB_USER" --instance "$SQL_INSTANCE" --password "$DB_PASS"
  fi
  printf 'postgres://%s:%s@/%s?host=/cloudsql/%s' "$DB_USER" "$DB_PASS" "$DB_NAME" "$CONN_NAME" | put_secret DATABASE_URL
  unset DB_PASS
fi
ok "Cơ sở dữ liệu: $CONN_NAME"

say "5/8 Khóa bí mật của ứng dụng"
secret_exists DJANGO_SECRET_KEY || openssl rand -base64 48 | tr -d '\n' | put_secret DJANGO_SECRET_KEY
ok "Đã có DJANGO_SECRET_KEY"

say "6/8 Email gửi thông báo (nxbkt@ueh.edu.vn)"
APP_PASS=""
if secret_exists EMAIL_URL; then
  read -r -s -p "    Đã có cấu hình email. Gõ c rồi Enter để nhập mật khẩu MỚI, hoặc chỉ bấm Enter để giữ: " again; echo
  # Người dùng dán thẳng mật khẩu vào câu hỏi này: coi đó là mật khẩu mới.
  if [ "${#again}" -ge 12 ]; then APP_PASS="$again"; again="c"; fi
else again="c"; fi
if [ "${again,,}" = "c" ]; then
  if [ -z "$APP_PASS" ]; then
    read -r -s -p "    Dán mật khẩu ứng dụng 16 ký tự của nxbkt@ueh.edu.vn (chữ sẽ không hiện; Enter để tạm tắt email): " APP_PASS; echo
  fi
  if [ -n "$APP_PASS" ]; then
    APP_PASS="${APP_PASS// /}"
    printf 'smtp+tls://nxbkt%%40ueh.edu.vn:%s@smtp.gmail.com:587' "$APP_PASS" | put_secret EMAIL_URL
    ok "Đã lưu cấu hình email"
  else
    secret_exists EMAIL_URL || printf 'consolemail://' | put_secret EMAIL_URL
    warn "Email đang tắt (chỉ ghi vào nhật ký máy chủ)"
  fi
  unset APP_PASS
fi

say "7/8 Đăng nhập Google và Google Drive"
if [ -n "$GOOGLE_OAUTH_CLIENT_ID" ]; then
  CS=""
  if secret_exists GOOGLE_OAUTH_CLIENT_SECRET && [ "$(gcloud secrets versions access latest --secret GOOGLE_OAUTH_CLIENT_SECRET)" != "chua-cau-hinh" ]; then
    read -r -s -p "    Đã có Client secret. Gõ c rồi Enter để nhập MỚI, hoặc chỉ bấm Enter để giữ: " again; echo
    if [ "${#again}" -ge 12 ]; then CS="$again"; again="c"; fi
  else again="c"; fi
  if [ "${again,,}" = "c" ]; then
    [ -z "$CS" ] && { read -r -s -p "    Dán Client secret đăng nhập Google (chữ sẽ không hiện): " CS; echo; }
    [ -n "$CS" ] && printf '%s' "$CS" | put_secret GOOGLE_OAUTH_CLIENT_SECRET
    unset CS
  fi
fi
secret_exists GOOGLE_OAUTH_CLIENT_SECRET || printf 'chua-cau-hinh' | put_secret GOOGLE_OAUTH_CLIENT_SECRET
if [ -n "$GDRIVE_SHARED_DRIVE_ID" ] && ! secret_exists GDRIVE_KEY; then
  # Khóa của tài khoản máy được tạo và đưa thẳng vào Secret Manager, không lưu ra đĩa.
  gcloud iam service-accounts keys create /dev/stdout --iam-account "$RUN_SA" 2>/dev/null | put_secret GDRIVE_KEY
  ok "Đã tạo khóa Drive (lưu trong Secret Manager)"
fi

say "8/8 Đóng gói và chạy Portal trên Cloud Run (5–10 phút)"
VOLUME_ARGS=()
ENV_VARS="DJANGO_SETTINGS_MODULE=portal.settings.prod,DJANGO_DEBUG=False"
ENV_VARS+=",ALLOWED_HOSTS=.run.app,CSRF_TRUSTED_ORIGINS=https://*.run.app"
ENV_VARS+=",DEFAULT_FROM_EMAIL=nxbkt@ueh.edu.vn,STAFF_GOOGLE_DOMAIN=ueh.edu.vn"
[ -n "$GOOGLE_OAUTH_CLIENT_ID" ] && ENV_VARS+=",GOOGLE_OAUTH_CLIENT_ID=${GOOGLE_OAUTH_CLIENT_ID}"
SECRETS="DJANGO_SECRET_KEY=DJANGO_SECRET_KEY:latest,DATABASE_URL=DATABASE_URL:latest"
SECRETS+=",EMAIL_URL=EMAIL_URL:latest,GOOGLE_OAUTH_CLIENT_SECRET=GOOGLE_OAUTH_CLIENT_SECRET:latest"
if [ -n "$GDRIVE_SHARED_DRIVE_ID" ]; then
  ENV_VARS+=",FILE_STORAGE_BACKEND=gdrive,GDRIVE_SHARED_DRIVE_ID=${GDRIVE_SHARED_DRIVE_ID}"
  ENV_VARS+=",GDRIVE_CREDENTIALS_FILE=/secrets/gdrive/key.json"
  SECRETS+=",/secrets/gdrive/key.json=GDRIVE_KEY:latest"
else
  # Chưa có Shared Drive: lưu tài liệu vào kho Cloud Storage của dự án, gắn vào Portal như một thư mục.
  BUCKET="${PROJECT_ID}-tai-lieu"
  if ! gcloud storage buckets describe "gs://${BUCKET}" >/dev/null 2>&1; then
    gcloud storage buckets create "gs://${BUCKET}" --location "$REGION" \
      --uniform-bucket-level-access --public-access-prevention >/dev/null
  fi
  gcloud storage buckets add-iam-policy-binding "gs://${BUCKET}" \
    --member "serviceAccount:$RUN_SA" --role roles/storage.objectUser >/dev/null
  ENV_VARS+=",FILE_STORAGE_BACKEND=local,MEDIA_ROOT=/app/media"
  MAX_INSTANCES=1
  if ! gcloud run services describe "$SERVICE" --region "$REGION" \
      --format='value(spec.template.spec.volumes[].name)' 2>/dev/null | grep -qw tailieu; then
    VOLUME_ARGS=(--add-volume "name=tailieu,type=cloud-storage,bucket=${BUCKET},mount-options=implicit-dirs;metadata-cache-ttl-secs=0"
      --add-volume-mount "volume=tailieu,mount-path=/app/media")
  fi
  ok "Tài liệu lưu trong kho Cloud Storage: ${BUCKET}"
fi
ADMIN_VAR="BOOTSTRAP_ADMIN_EMAILS=${ADMIN_EMAILS}"
: "${MAX_INSTANCES:=2}"
cd "$(dirname "$0")/../.."
gcloud run deploy "$SERVICE" --source . --quiet --region "$REGION" --service-account "$RUN_SA" \
  --add-cloudsql-instances "$CONN_NAME" --allow-unauthenticated \
  --memory 1Gi --cpu 1 --min-instances 0 --max-instances "$MAX_INSTANCES" --timeout 300 \
  --set-env-vars "^|^${ENV_VARS//,/|}|${ADMIN_VAR}" --set-secrets "$SECRETS" "${VOLUME_ARGS[@]}"
IMAGE="$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(spec.template.spec.containers[0].image)')"

# Cloud Run Job dùng để chạy lệnh quản trị (tạo Admin, kiểm tra Drive)
JOB_ARGS=(--image "$IMAGE" --region "$REGION" --service-account "$RUN_SA"
  --set-cloudsql-instances "$CONN_NAME" --memory 1Gi
  --set-env-vars "^|^${ENV_VARS//,/|}|${ADMIN_VAR}" --set-secrets "$SECRETS"
  --command python --args manage.py,bootstrap_admin)
if gcloud run jobs describe "$JOB" --region "$REGION" >/dev/null 2>&1; then
  gcloud run jobs update "$JOB" "${JOB_ARGS[@]}" >/dev/null
else
  gcloud run jobs create "$JOB" "${JOB_ARGS[@]}" >/dev/null
fi
if [ -n "$ADMIN_EMAILS" ]; then
  gcloud run jobs execute "$JOB" --region "$REGION" --wait >/dev/null && ok "Đã tạo/cập nhật tài khoản Quản trị viên"
fi
if [ -n "$GDRIVE_SHARED_DRIVE_ID" ]; then
  if gcloud run jobs execute "$JOB" --region "$REGION" --args manage.py,drive_check --wait >/dev/null 2>&1; then
    ok "Kiểm tra Google Drive: ĐẠT"
  else
    warn "Kiểm tra Google Drive: CHƯA ĐẠT – xem hướng dẫn mục Drive, rồi chạy lại lệnh này"
  fi
fi

URL="$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')"
say "XONG"
echo "    Địa chỉ Portal:            $URL"
echo "    Tài khoản máy (cho Drive): $RUN_SA"
echo "    Địa chỉ chuyển hướng đăng nhập Google: ${URL}/accounts/google/login/callback/"
