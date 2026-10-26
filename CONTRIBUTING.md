# Đóng góp cho bonrs · Contributing

Cảm ơn bạn đã quan tâm! Mọi đóng góp đều được chào đón: báo lỗi, đề xuất tính năng, sửa tài liệu, dịch, thêm skill tri thức, hay gửi mã.
*Thanks for your interest! Bug reports, ideas, docs, translations, knowledge skills and code are all welcome. English is fine everywhere.*

Nếu bonrs có ích, hãy bấm **⭐ Star** trên GitHub. Việc này giúp nhiều người tìm thấy dự án hơn.

## Cách đóng góp nhanh

| Bạn muốn | Làm gì |
|---|---|
| Báo lỗi | Mở [issue "Báo lỗi"](https://github.com/hoangtrongbinh1111/bonrs/issues/new?template=bug_report.md), kèm các bước tái hiện và log |
| Đề xuất tính năng | Mở [issue "Đề xuất"](https://github.com/hoangtrongbinh1111/bonrs/issues/new?template=feature_request.md) |
| Hỏi cách dùng | Mở issue hoặc Discussion; đọc [hướng dẫn](docs/GUIDE.vi.md) trước |
| Lỗ hổng bảo mật | **Không** mở issue công khai, xem [SECURITY.md](SECURITY.md) |
| Gửi mã | Fork → nhánh mới → Pull Request (các bước dưới đây) |

Việc phù hợp cho người mới có nhãn `good first issue`.

## Gửi Pull Request

1. Fork repo, tạo nhánh từ `main`: `git checkout -b fix/ten-ngan-gon`.
2. Cài môi trường và chạy thử:
   ```bash
   python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
   .venv/bin/python test_bonrs.py          # phải xanh, không cần mạng hay API key
   node tools/i18n_check.js web            # nếu bạn sửa giao diện
   ```
   Chạy web thử với Claude giả (không tốn tiền):
   ```bash
   BONRS_DATA=/tmp/bonrs-dev BONRS_CLAUDE_BIN=$PWD/tools/mock_claude \
   BONRS_ADMIN_EMAIL=admin@local BONRS_ADMIN_PASSWORD=admin123 \
   .venv/bin/uvicorn bonrs.web:app --port 8767
   ```
3. Giữ thay đổi nhỏ và tập trung vào một việc. Thêm hoặc sửa test cho logic mới.
4. Viết commit message rõ ràng, ví dụ `fix(remote): retry rsync on timeout`.
5. Mở PR, mô tả **vì sao** cần thay đổi và cách bạn đã kiểm tra. Có thay đổi giao diện thì đính kèm ảnh chụp.

Người duy trì sẽ xem PR trong vòng vài ngày. PR được gộp theo kiểu squash.

## Quy ước

- **Đơn giản trước:** Python stdlib và FastAPI; giao diện là JS thuần, không có bước build. Muốn thêm thư viện mới thì hỏi trước trong issue.
- **Giao diện song ngữ:** chữ giao diện viết bằng tiếng Việt trong `web/app.js`. Sau đó chạy `python3 tools/i18n_extract.py`, thêm bản dịch vào `web/i18n-en.js` và kiểm tra bằng `node tools/i18n_check.js web`.
- **Bảo mật:**
  - Không đọc hay ghi file trong thư mục phiên mà không đi qua `bonrs/safeio.py`.
  - Không đưa khóa API vào môi trường của job.
  - Chạy `tools/security_smoke.py` nếu bạn đụng tới sandbox, proxy hoặc phân quyền.
- **Prompt và tri thức:** skill trong `knowledge/` theo frontmatter có sẵn, thân ≤ 400 từ, viết ở thể mệnh lệnh và kiểm tra được. Ghi rõ nguồn.
- **Dùng AI có trách nhiệm:** bonrs không nhận thay đổi nhằm che giấu việc dùng AI (gỡ watermark, né AI detector, bỏ phần khai báo AI). Thay đổi giúp bài viết minh bạch và chính xác hơn thì luôn được chào đón.

## Giấy phép

Khi gửi đóng góp, bạn đồng ý phát hành phần đó theo [giấy phép MIT](LICENSE) của dự án.

## Quy tắc ứng xử

Mọi người tham gia cần tuân thủ [Quy tắc ứng xử](CODE_OF_CONDUCT.md).
