# bonrs

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE) [![GitHub stars](https://img.shields.io/github/stars/hoangtrongbinh1111/bonrs?style=social)](https://github.com/hoangtrongbinh1111/bonrs/stargazers) [![PRs welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

**Tiếng Việt** · [English](README.md) · [Hướng dẫn đầy đủ](docs/GUIDE.vi.md) · [Đóng góp](CONTRIBUTING.md) · Giấy phép: [MIT](LICENSE)

> ⭐ Nếu bonrs có ích cho bạn, hãy **[Star repo](https://github.com/hoangtrongbinh1111/bonrs)** để ủng hộ và theo dõi bản mới.

bonrs là ứng dụng web chạy trên server của bạn, nhiều người dùng chung. Bạn nhập một ý tưởng và tạp chí đích. Hệ thống dùng Claude (Claude Code) để tự làm 10 bước: xác định phạm vi, tìm và đọc tài liệu, phân tích tạp chí, lập kế hoạch, chạy thí nghiệm, viết bài, phản biện nhiều vòng, chỉnh sửa, đóng gói hồ sơ nộp và rút kinh nghiệm.

Bạn chỉ cần duyệt ở vài cổng quan trọng, tải lên các PDF trả phí khi được nhắc, và đọc bản cuối.

## Cài đặt trên server (Docker)

Yêu cầu: Docker và Docker Compose, khoảng 4 GB đĩa cho image (gồm TeX Live).

```bash
git clone https://github.com/hoangtrongbinh1111/bonrs.git bonrs && cd bonrs
cp .env.example .env          # sửa email và mật khẩu admin
docker compose up -d --build
```

Mở `http://<server>:8765`, đăng nhập bằng tài khoản admin trong `.env`. Vào **Quản trị** để:

- nhập Anthropic API key chung (cho người chưa có kết nối riêng và cho việc tự cập nhật kho tri thức);
- nhập email liên hệ (Crossref, Unpaywall) và OpenAlex / Semantic Scholar key nếu có;
- tạo tài khoản cho thành viên.

Mục **Vận hành** đã có sẵn giá trị mặc định (2 việc song song, 24 giờ mỗi việc, 30 USD mỗi bước, model claude-opus-5-5); chỉ đổi khi cần.

### Kết nối Claude

Mỗi người chọn trong trang **Tài khoản**:

- **Gói Claude Pro/Max của mình**: trên máy tính cá nhân chạy `claude setup-token`, dán mã `sk-ant-oat…` vào. Lượng dùng tính vào hạn mức của gói. Gói là cá nhân: mỗi người dùng mã của chính mình, không nhập mã của mình vào chỗ dùng chung.
- **API key riêng** (console.anthropic.com), trả theo lượng dùng.
- **Key chung của server** (mặc định), do quản trị viên nhập.

### Chạy nền

`docker compose up -d` chạy server ở nền, tự khởi động lại khi máy bật (`restart: unless-stopped`). Mọi việc chạy trên server: tắt trình duyệt hay tắt máy cá nhân không ảnh hưởng. Nếu server khởi động lại giữa chừng (cập nhật, mất điện), các phiên đang chạy tự chạy tiếp từ bước dở dang. Trên Mac/Windows dùng Docker Desktop thì bật “Start Docker Desktop when you sign in”.

Mọi dữ liệu nằm trong thư mục `./data`: các phiên nghiên cứu (mỗi phiên là một git repo), kho tri thức, cơ sở dữ liệu, khoá SSH. Sao lưu thư mục này là đủ.

Khi đưa ra Internet, đặt sau một reverse proxy có HTTPS (Caddy, Nginx) và đặt `BONRS_SECURE_COOKIE=1`.

## Sử dụng

1. **Ý tưởng mới**: viết vài dòng ý tưởng rồi bấm **AI viết & tranh luận giúp**: AI viết thành bản mô tả đủ ý (vấn đề, giả thuyết, dữ liệu, phương pháp, đóng góp, phạm vi), cho 4 vai (người đề xuất, phản biện, biên tập tạp chí, người thực hiện) tranh luận, rồi chốt bản cuối và hỏi lại những điểm chưa rõ; trả lời để tranh luận thêm vòng nữa, hoặc bấm **Dùng bản này**. Chọn tạp chí (gợi ý từ OpenAlex), bài báo nền, lĩnh vực, máy chạy. Mục 6 chọn model từ danh sách, trần chi phí mỗi bước (tự đề xuất theo chi phí các bước đã chạy trên server) và có tự đi tiếp hay không khi không ai duyệt (giờ và phút).
2. **Tổng quan**: theo dõi 10 giai đoạn, chi phí, điểm phản biện. Khi agent dừng ở cổng, bạn chọn Đồng ý, Tiếp tục theo hướng dẫn, hoặc Dừng. Không ai trả lời thì sau số giờ đã đặt, agent tự đi tiếp.
3. **Tệp**: xem mọi kết quả (scope, tổng quan tài liệu, style guide của tạp chí, code và kết quả thí nghiệm, bản thảo PDF/DOCX). Bôi đen đoạn văn để góp ý, hoặc sửa trực tiếp. Tải lên PDF trả phí khi banner “Agent cần bạn hỗ trợ” xuất hiện.
4. **Phản biện & bàn giao**: thư biên tập một trang (đọc đầu tiên), các vòng phản biện, thư trả lời, checklist nộp, khai báo dùng AI.
5. **Góp ý**: mọi góp ý “open” được giao cho agent ở vòng chỉnh sửa kế tiếp, rồi được tổng hợp thành kinh nghiệm cho lần sau.
6. **Lịch sử**: mỗi giai đoạn, vòng phản biện, chỉnh sửa và tải lên là một mốc. Bấm một mốc để xem nó đổi những tệp nào (+/− dòng), bấm tên tệp để xem từng dòng thêm (xanh) và bớt (đỏ). Chế độ **So sánh hai mốc**: bấm mốc A rồi mốc B. Bấm vào một bước trên thanh tiến trình để xem lịch sử và lưu trình riêng của bước đó. Tải toàn bộ phiên (zip, kèm lịch sử git).

## Kết nối server thí nghiệm

Mặc định thí nghiệm chạy ngay trên server cài bonrs, trong thư mục `exp/` của từng phiên (GPU nếu bật phần `deploy` trong `docker-compose.yml`). Không cần cấu hình gì. Để thêm máy GPU riêng, vào **Máy chạy → Thêm máy riêng**:

1. Nhập `tài khoản@địa chỉ` (và cổng nếu khác 22), đúng như khi bạn `ssh` vào máy đó.
2. Đăng nhập máy đó, chạy một lần lệnh trang web đưa ra (thêm khoá SSH của tài khoản bonrs của bạn vào `~/.ssh/authorized_keys`).
3. Bấm **Kiểm tra kết nối**: bonrs đọc CPU, RAM, GPU, Python, ổ đĩa, rồi đề xuất tên máy, thư mục (`~/bonrs-runs`, mỗi phiên một thư mục con) và cách chuẩn bị môi trường (mặc định tự tạo `.venv` và cài `requirements.txt`; dùng conda có sẵn nếu có).
4. Khi tạo phiên (hoặc ở tab Cấu hình), tích các máy muốn dùng. Chọn nhiều máy thì agent gửi mỗi lần chạy độc lập (seed, fold, ablation) sang máy đang rảnh nhất; một lần huấn luyện không bị chia nhỏ.

Khoá SSH gắn với tài khoản bonrs của từng người, không gắn với máy. Cụm Slurm vẫn dùng được qua `bonrs.yaml` (`type: slurm`) nhưng chưa có trên giao diện.

## Kho tri thức

Kho chung cho mọi người, tổ chức từ chung đến cụ thể:

| Tầng | Nội dung |
|---|---|
| `00-general` | Luật bất biến và kỹ năng viết cho mọi lĩnh vực |
| `10-domain/<lĩnh vực>` | Chuẩn báo cáo, thống kê, kiểu thí nghiệm theo ngành |
| `20-article-type` | Theo loại bài: nghiên cứu, tổng quan, bibliometric, case |
| `30-journal` | Quy định riêng của từng tạp chí, tự bổ sung sau mỗi phiên |
| `40-experience` | Bài học tích luỹ, giảm trọng số theo thời gian |
| `50-user/<id>` | Sở thích và văn phong của từng người |

Mỗi skill là một tệp markdown có frontmatter (`level`, `domain`, `journal`, `tags`, `source`, `confidence`, `status`). Agent chỉ nạp các skill `active` khớp với phiên.

Bổ sung tri thức:

- **Đóng góp tài liệu**: tải lên PDF/DOCX/MD/HTML hoặc dán URL. Agent chuẩn hoá thành skill nháp.
- **Nguồn tự động**: 7 nguồn có sẵn (Taylor & Francis, Elsevier, Springer, Wiley, PLOS, IEEE, EQUATOR). Admin thêm, tắt, xoá nguồn ở **Kho tri thức → Nguồn tự động** (tên, đường dẫn, tầng, lĩnh vực) và chọn lịch: mặc định mỗi tuần, hoặc mỗi ngày/mỗi tháng/tắt. Trang không đổi thì bỏ qua, không tốn phí; trang mới hoặc đã đổi thành skill nháp chờ duyệt (hoặc tự duyệt khi độ tin cậy ≥ 0,8/0,9 nếu admin bật). Lịch cần key chung của server.
- **Chờ duyệt**: admin đọc, sửa, duyệt hoặc từ chối từng skill nháp.
- Thành viên tự tạo skill cá nhân hoặc skill riêng cho một phiên, rồi bấm “Đề xuất vào kho chung” để admin duyệt.

## Các bảo đảm về chất lượng

- Mọi con số trong bài phải có trong `exp/results/registry.json`; mọi câu ở Results/Discussion gắn với một mục trong `paper/claims.yaml` với mức độ khẳng định cho phép.
- Mọi trích dẫn phải có DOI/arXiv và có trong kho tài liệu đã tải; tài liệu bị rút (retracted) bị loại.
- Lệnh kiểm tra `bonrs audit` là định nghĩa “xong”: biên dịch sạch, không placeholder, số khớp nguồn, không từ phóng đại.
- Phản biện 5 ghế độc lập, có ghế “phản biện sát thủ” và Area Chair, so sánh với bài đã đăng của chính tạp chí; tối đa 3 vòng.
- Khai báo sử dụng AI được sinh đúng mẫu của nhà xuất bản. bonrs không gỡ hay che dấu vết sử dụng AI.

## Dùng dòng lệnh (phát triển)

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
python3 test_bonrs.py                                    # kiểm thử offline
python3 bonrs.py new "<ý tưởng>" --journal "<tạp chí>" --domain ml
python3 bonrs.py run <slug> [--from 03_plan] [--to 05_draft]
python3 bonrs.py approve <slug> --note "hướng dẫn"
python3 bonrs.py audit <slug> --final
BONRS_ADMIN_EMAIL=a@b BONRS_ADMIN_PASSWORD=x .venv/bin/uvicorn bonrs.web:app --port 8765
```

Kế hoạch chi tiết và các mốc tiếp theo: `PLAN.md`.

## Đóng góp

Rất hoan nghênh báo lỗi, đề xuất, tài liệu, bản dịch, skill tri thức và Pull Request. Xem [CONTRIBUTING.md](CONTRIBUTING.md) để biết cách chạy thử với Claude giả (không tốn tiền) và quy ước mã. Lỗ hổng bảo mật xin báo riêng theo [SECURITY.md](SECURITY.md). Mọi người tham gia tuân thủ [Quy tắc ứng xử](CODE_OF_CONDUCT.md).

Nếu thấy dự án hữu ích, một ⭐ trên [GitHub](https://github.com/hoangtrongbinh1111/bonrs) là cách ủng hộ đơn giản nhất.

## Tài trợ

bonrs miễn phí và mã nguồn mở. Nếu bạn hoặc tổ chức của bạn muốn tài trợ (chi phí máy chủ, GPU, API) hoặc hợp tác, hãy liên hệ **[binhht99@lqdtu.edu.vn](mailto:binhht99@lqdtu.edu.vn)**.

## Giấy phép

bonrs phát hành theo giấy phép MIT (xem [LICENSE](LICENSE)). Thành phần bên thứ ba: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Claude Code do Anthropic phát hành theo điều khoản riêng.
