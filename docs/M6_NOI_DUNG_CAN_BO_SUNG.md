# M6 — NỘI DUNG CẦN NXB CUNG CẤP

Danh sách mọi chỗ `[CẦN NXB CUNG CẤP: ...]` trên trang công khai (nhánh `m6-public-site`). Owner gửi NXB; khi có nội dung, AI-3 thay vào đúng vị trí.

| # | Trang (URL) | Tệp template | Nội dung cần cung cấp |
|---|---|---|---|
| 1 | Mọi trang công khai (khối liên hệ cuối trang) | `templates/public_site/_layout.html` | Địa chỉ trụ sở |
| 2 | Mọi trang công khai (khối liên hệ cuối trang) | `templates/public_site/_layout.html` | Số điện thoại |
| 3 | Mọi trang công khai (khối liên hệ cuối trang) | `templates/public_site/_layout.html` | Email liên hệ |
| 4 | Trang chủ `/` | `templates/public_site/home.html` | Đoạn giới thiệu ngắn về Nhà xuất bản cho trang chủ |
| 5 | Giới thiệu `/gioi-thieu/` | `templates/public_site/about.html` | Giới thiệu chung (tên đầy đủ, cơ quan chủ quản) |
| 6 | Giới thiệu `/gioi-thieu/` | `templates/public_site/about.html` | Lịch sử hình thành và phát triển |
| 7 | Giới thiệu `/gioi-thieu/` | `templates/public_site/about.html` | Chức năng, nhiệm vụ, lĩnh vực xuất bản |
| 8 | Giới thiệu `/gioi-thieu/` | `templates/public_site/about.html` | Thông tin ban lãnh đạo (nếu muốn công bố) |
| 9 | Quy trình `/quy-trinh/` | `templates/public_site/process.html` | Thời gian xử lý dự kiến của từng bước |
| 10 | Quy trình `/quy-trinh/` | `templates/public_site/process.html` | Tên đầy đủ Mẫu 1 |
| 11 | Quy trình `/quy-trinh/` | `templates/public_site/process.html` | Tên đầy đủ Mẫu 2 (xuất hiện 2 chỗ: tự xuất bản và liên kết) |
| 12 | Quy trình `/quy-trinh/` | `templates/public_site/process.html` | Tên đầy đủ Mẫu 3 (xuất hiện 2 chỗ: tự xuất bản và liên kết) |
| 13 | Quy trình `/quy-trinh/` | `templates/public_site/process.html` | Yêu cầu trình bày bản thảo (khổ giấy, phông chữ, cỡ chữ, lề, đánh số trang, hình ảnh, tài liệu tham khảo) |
| 14 | Liên hệ `/lien-he/` | `templates/public_site/contact.html` | Địa chỉ trụ sở (như mục 1) |
| 15 | Liên hệ `/lien-he/` | `templates/public_site/contact.html` | Số điện thoại (như mục 2) |
| 16 | Liên hệ `/lien-he/` | `templates/public_site/contact.html` | Email liên hệ (như mục 3) |
| 17 | Liên hệ `/lien-he/` | `templates/public_site/contact.html` | Giờ làm việc |

Ngoài ra, nếu NXB muốn dùng **logo/ảnh** trên trang công khai thì cần cung cấp tệp và xác nhận quyền sử dụng; hiện chỉ dùng tên chữ "Nhà xuất bản Kinh tế TP. Hồ Chí Minh".

Kiểm tra lại danh sách: `grep -rn "CẦN NXB CUNG CẤP" templates/public_site/` (19 dòng = 17 mục trên, Mẫu 2 và Mẫu 3 mỗi mẫu xuất hiện 2 lần).
