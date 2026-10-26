# Hướng dẫn cài đặt và sử dụng bonrs

bonrs là ứng dụng web chạy trên server của bạn, cho nhiều người dùng chung. Bạn đưa vào một ý tưởng và tạp chí đích; agent (Claude Code) tự làm 10 bước, từ đọc bài nền và chấm giả thuyết đến viết bài, phản biện nhiều vòng và đóng gói hồ sơ nộp. Bạn chỉ duyệt ở vài điểm quan trọng.

## 1. bonrs làm gì

| Bước | Agent làm gì | Có cổng duyệt |
|---|---|---|
| 0. Giả thuyết | Đọc bài báo nền, cho 4 vai thảo luận hướng cải tiến, chấm khả năng làm thành công và khả năng được accept của từng giả thuyết | Luôn dừng để bạn chọn |
| 1. Tài liệu | Tìm, đọc, tổng hợp tài liệu; kiểm tra tính mới; xin bạn PDF trả phí nếu cần | Có |
| 2. Tạp chí | Đọc hướng dẫn tác giả và bài đã đăng; xác định loại bài, định dạng, văn phong | |
| 3. Kế hoạch | Thiết kế thí nghiệm, chốt tiêu chí thành công trước khi chạy | Có |
| 4. Thí nghiệm | Viết code, chạy trên máy chạy, đọc log, ghi số liệu | |
| 5. Bản thảo | Viết bài theo văn phong tạp chí, mọi con số lấy từ kết quả thật | |
| 6. Phản biện | 6 phản biện ẩn danh và một biên tập viên tổng hợp | |
| 7. Chỉnh sửa | Sửa theo phản biện và góp ý của bạn, lặp đến khi đạt điểm | Có, sau mỗi vòng |
| 8. Hồ sơ nộp | Thư gửi tạp chí, checklist, khai báo dùng AI, thư biên tập | Có |
| 9. Rút kinh nghiệm | Ghi bài học vào kho tri thức (quản trị viên duyệt) | |

Mọi thứ của một phiên được lưu lại: tệp, lịch sử từng lần chạy, góp ý, chi phí.

## 2. Cài đặt

### 2.1. Yêu cầu

- Một máy chủ Linux (Ubuntu 22.04/24.04 khuyên dùng) hoặc máy Mac/Windows có Docker Desktop.
- 4 nhân CPU, 8 GB RAM trở lên (16 GB nếu chạy 2 phiên cùng lúc), 20 GB đĩa trống. Image có TeX Live chiếm khoảng 4 GB.
- Docker 24+ và Docker Compose v2.
- Kết nối Internet tới api.anthropic.com và các nguồn học thuật (OpenAlex, Crossref, arXiv…).
- Một cách kết nối Claude: API key Anthropic, hoặc gói Claude Pro/Max của từng người (xem mục 4).

### 2.2. Cài trên server Linux

1. Cài Docker:
   ```bash
   curl -fsSL https://get.docker.com | sh
   sudo usermod -aG docker $USER   # đăng xuất rồi đăng nhập lại
   ```
2. Lấy mã nguồn:
   ```bash
   git clone https://github.com/hoangtrongbinh1111/bonrs.git bonrs && cd bonrs
   ```
3. Tạo tệp cấu hình và đặt tài khoản quản trị:
   ```bash
   cp .env.example .env
   nano .env      # sửa BONRS_ADMIN_EMAIL và BONRS_ADMIN_PASSWORD (mật khẩu dài)
   ```
   Mật khẩu trong `.env` chỉ dùng ở lần khởi động đầu; sau đó đổi trong trang Tài khoản.
4. Khởi động (chạy nền, tự bật lại khi máy khởi động):
   ```bash
   docker compose up -d --build
   ```
5. Mở `http://<địa-chỉ-server>:8765` và đăng nhập bằng tài khoản quản trị.

Xem nhật ký khi cần: `docker compose logs -f`. Dừng: `docker compose down` (dữ liệu vẫn còn).

### 2.3. Cài trên máy Mac hoặc Windows

1. Cài [Docker Desktop](https://www.docker.com/products/docker-desktop/), mở và chờ nó chạy.
2. Trong Docker Desktop → Settings → General, bật **Start Docker Desktop when you sign in** để bonrs tự chạy lại sau khi bật máy.
3. Mở Terminal (Windows: PowerShell), làm như bước 2–5 ở trên.

### 2.4. Đưa ra Internet an toàn (HTTPS)

Đặt bonrs sau một reverse proxy có HTTPS. Ví dụ với Caddy (tự lấy chứng chỉ Let's Encrypt):

```
bonrs.ten-mien-cua-ban.vn {
    reverse_proxy 127.0.0.1:8765
}
```

Khi đó sửa `docker-compose.yml` để cổng chỉ mở trong máy: `ports: ["127.0.0.1:8765:8765"]`, và thêm `BONRS_SECURE_COOKIE=1` vào `.env`.

### 2.5. Dùng GPU của chính server bonrs

Cài [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html), rồi bỏ dấu `#` ở dòng `deploy:` trong `docker-compose.yml` và chạy lại `docker compose up -d`. Thí nghiệm chạy trên "Máy chủ bonrs" sẽ thấy GPU.

### 2.6. Biến môi trường

| Biến | Ý nghĩa | Mặc định |
|---|---|---|
| `BONRS_ADMIN_EMAIL`, `BONRS_ADMIN_PASSWORD` | Tài khoản quản trị tạo ở lần khởi động đầu | bắt buộc |
| `BONRS_PORT` | Cổng web trên máy chủ | 8765 |
| `BONRS_SECURE_COOKIE` | `1` khi chạy sau HTTPS | tự nhận |
| `ANTHROPIC_API_KEY` | Key chung (có thể nhập trong giao diện thay vì ở đây) | trống |

### 2.7. Sao lưu, cập nhật, gỡ cài đặt

- **Sao lưu:** mọi dữ liệu nằm trong thư mục `./data` (phiên, kho tri thức, cơ sở dữ liệu, khoá SSH của từng người). Sao chép thư mục này là đủ, ví dụ `tar czf bonrs-backup-$(date +%F).tgz data`.
- **Cập nhật:** `git pull && docker compose up -d --build`. Phiên đang chạy dở sẽ tự chạy tiếp từ bước dở dang sau khi server lên lại.
- **Gỡ:** `docker compose down`, rồi xoá thư mục nếu không cần dữ liệu.

## 3. Thiết lập lần đầu (quản trị viên)

1. **Quản trị → Khoá API & nguồn dữ liệu:** nhập Anthropic API key chung (lấy ở console.anthropic.com → API Keys). Key này dùng cho người chưa có kết nối riêng và cho việc tự cập nhật kho tri thức. Agent không bao giờ nhìn thấy key: server tự gắn key khi chuyển tiếp yêu cầu. Nhập thêm email liên hệ (Crossref/Unpaywall) và OpenAlex / Semantic Scholar key nếu có.
2. **Quản trị → Người dùng:** thêm tài khoản cho thành viên (email, mật khẩu tạm). Họ tự đổi mật khẩu ở trang Tài khoản.
3. **Quản trị → Vận hành:** đã điền sẵn mặc định hợp lý (model Claude Opus 5.5, trần chi phí đề xuất theo dữ liệu thực, tự đi tiếp sau 12 giờ, 2 phiên chạy cùng lúc, mỗi lượt tối đa 24 giờ). Chỉ đổi khi có lý do; có nút đưa về mặc định.
4. **Kho tri thức → Nguồn tự động:** xem 7 nguồn có sẵn, thêm nguồn riêng, chọn lịch cập nhật (mặc định mỗi tuần).

## 4. Kết nối Claude

Mỗi người chọn trong **Tài khoản → Kết nối Claude**:

| Cách | Khi nào dùng | Chi phí |
|---|---|---|
| Gói Claude Pro/Max của tôi | Bạn đã có gói Pro/Max | Trừ vào hạn mức của gói |
| API key của tôi | Muốn tự trả theo lượng dùng | Theo bảng giá API |
| Key chung của server | Mặc định | Tính vào key do quản trị viên quản lý |

Dùng gói Pro/Max:

1. Trên máy tính của bạn, cài Claude Code: `npm install -g @anthropic-ai/claude-code`.
2. Chạy `claude setup-token`, đăng nhập tài khoản Claude trong trình duyệt.
3. Dán mã bắt đầu bằng `sk-ant-oat` vào ô và bấm Lưu.

Gói Claude là cá nhân: mỗi người dùng mã của chính mình, không đưa mã cho người khác và không nhập vào chỗ dùng chung. Mã có hạn khoảng 1 năm. Phiên dài có thể phải chờ hạn mức của gói hồi lại.

## 5. Tạo một phiên nghiên cứu

Vào **Ý tưởng mới**.

1. **Ý tưởng.** Viết vài dòng, rồi bấm **AI viết & tranh luận giúp**. AI viết lại thành bản mô tả đủ ý (vấn đề, giả thuyết, dữ liệu, phương pháp và so sánh, đóng góp, phạm vi), cho 4 vai tranh luận (người đề xuất, phản biện, biên tập tạp chí, người thực hiện) rồi chốt bản cuối và hỏi lại những điểm chưa rõ. Trả lời câu hỏi rồi bấm **Tranh luận thêm một vòng**, hoặc **Dùng bản này** để điền vào ô ý tưởng. Điều gì AI tự đoán được đánh dấu "giả định, cần xác nhận".
2. **Bài báo nền.** Kéo thả PDF/DOCX/MD của vài bài bạn muốn dựa vào, hoặc dán DOI, đường dẫn, tên bài. Không có bài nào thì agent tự chọn 3–5 bài gần nhất và nói rõ.
3. **Tạp chí.** Gõ tên tạp chí đích (gợi ý từ OpenAlex) và tạp chí dự phòng. Loại bài, định dạng và văn phong theo tạp chí này.
4. **Lĩnh vực & định dạng.** Mặc định "Theo tạp chí".
5. **Máy chạy thí nghiệm.** "Máy chủ bonrs" có sẵn. Chọn thêm máy GPU riêng nếu có (mục 8).
6. **Model, chi phí, thời gian chờ duyệt.** Chọn model từ danh sách. Trần chi phí mỗi bước được đề xuất sẵn theo chi phí các bước đã chạy trên server; agent chỉ tốn phần thực dùng, bước nào chạm trần thì dừng. Bật "Tự đi tiếp khi không ai duyệt" và đặt số giờ, phút; tắt thì agent luôn chờ bạn.

Bên phải là lộ trình 10 bước: bật công tắc ở bước nào thì agent dừng chờ bạn sau bước đó. Bấm **Tạo phiên**.

## 6. Theo dõi và duyệt

### 6.1. Tổng quan

Trang phiên hiện thanh tiến trình 10 bước, chi phí, điểm phản biện qua các vòng và hoạt động gần đây. Bấm vào một bước trên thanh tiến trình để mở **trang chi tiết bước**: mọi lần chạy của bước đó (lưu trình từng thao tác của agent, chi phí, thời gian), diễn biến (cổng duyệt, góp ý) và các mốc lưu kèm nút xem thay đổi.

### 6.2. Cổng duyệt

Khi agent dừng, trang hiện banner màu vàng:

- **Duyệt, đi tiếp** (kèm góp ý nếu muốn: góp ý được chuyển cho bước tiếp theo).
- **Làm lại bước này theo góp ý.**
- **Tạm dừng tại đây.** Bấm "Tiếp tục" bất cứ lúc nào để chạy tiếp.

Ở cổng **Chọn giả thuyết**, bạn thấy từng giả thuyết với khả năng làm thành công, khả năng được accept nếu thành công, công sức và rủi ro. Chọn một giả thuyết để làm, hoặc dừng nếu chưa đáng làm. Cổng này luôn chờ bạn.

### 6.3. Tệp & bản thảo

Xem mọi kết quả (tổng quan tài liệu, quy định tạp chí, code và số liệu, bản thảo PDF/DOCX). Bôi đen một đoạn để góp ý, hoặc bấm Sửa để chỉnh trực tiếp. Tải lên PDF trả phí khi agent yêu cầu.

### 6.4. Phản biện & bàn giao

Thư biên tập một trang (đọc đầu tiên), các vòng phản biện kèm điểm từng ghế, thư trả lời phản biện, checklist nộp, thư gửi tạp chí, khai báo dùng AI.

### 6.5. Góp ý

Góp ý đang mở được giao cho agent ở vòng chỉnh sửa kế tiếp, rồi được tổng hợp thành kinh nghiệm cho lần sau.

### 6.6. Lịch sử

Mỗi bước, vòng phản biện, chỉnh sửa và tải lên là một mốc.

- **Xem từng mốc:** bấm một mốc, bên phải hiện các tệp thay đổi (thêm mới/sửa/xoá, số dòng +/−); bấm tên tệp để xem từng dòng, xanh là thêm, đỏ là bớt.
- **So sánh hai mốc:** bấm mốc cũ (A) rồi mốc mới (B).

### 6.7. Cấu hình phiên

Sửa ý tưởng, tạp chí, lĩnh vực, số vòng phản biện, cổng duyệt, máy chạy, model và chi phí bằng form. Thanh Lưu ở cuối màn hình báo khi có thay đổi chưa lưu. Người quen YAML có thể sửa thẳng `bonrs.yaml` ở mục Nâng cao.

### 6.8. Tải về

Nút tải ở góc trên tải toàn bộ phiên (zip, kèm lịch sử git).

## 7. Chạy nền

Mọi việc chạy trên server: tắt trình duyệt hay tắt máy cá nhân không ảnh hưởng. Nếu server khởi động lại (cập nhật, mất điện), phiên đang chạy tự chạy tiếp từ bước dở dang (tối đa 3 lần liên tiếp). Thí nghiệm trên máy SSH chạy bằng `nohup` nên cũng không bị ngắt.

## 8. Máy chạy thí nghiệm

### 8.1. Máy chủ bonrs

Có sẵn, không cần cài. Mỗi phiên có thư mục `exp/` riêng. Chế độ chuẩn bị môi trường **Tự động** tạo môi trường Python riêng (`.venv`) và cài `requirements.txt` do agent viết.

### 8.2. Thêm máy GPU riêng qua SSH

Vào **Máy chạy → Thêm máy riêng**:

1. Nhập `tài khoản@địa chỉ` (và cổng nếu khác 22), đúng như khi bạn `ssh` vào máy đó.
2. Đăng nhập máy đó, dán và chạy một lần lệnh trang web đưa ra. Lệnh thêm khoá SSH của **tài khoản bonrs của bạn** vào `~/.ssh/authorized_keys`. Muốn thu hồi thì xoá dòng `bonrs-user-…` trong tệp đó.
3. Bấm **Kiểm tra kết nối**: bonrs đọc CPU, RAM, GPU, Python, ổ đĩa rồi đề xuất tên máy, thư mục (`~/bonrs-runs/<tên phiên>`) và cách chuẩn bị môi trường (Tự động, conda có sẵn, hoặc lệnh riêng).
4. Bấm **Lưu máy**, rồi chọn máy khi tạo phiên hoặc ở tab Cấu hình.

Server bonrs phải SSH tới được máy đó (cùng mạng LAN, cùng VPN như WireGuard/Tailscale, hoặc máy mở cổng SSH).

### 8.3. Nhiều máy

Chọn nhiều máy cho một phiên: agent gửi mỗi lần chạy độc lập (seed, fold, ablation, baseline) sang máy đang rảnh nhất, đo GPU/CPU ngay lúc gửi. Một lần huấn luyện không bị chia nhỏ sang nhiều máy.

## 9. Kho tri thức

Quy tắc và kinh nghiệm agent nạp vào mỗi phiên, xếp từ chung đến cụ thể: chung, theo lĩnh vực, theo loại bài, theo tạp chí, kinh nghiệm tích luỹ, cá nhân.

- **Duyệt & sửa:** xem và sửa skill (thành viên sửa skill cá nhân của mình).
- **Đóng góp tài liệu:** gửi PDF/DOCX/đường dẫn; agent chuẩn hoá thành skill nháp.
- **Chờ duyệt:** quản trị viên đọc, sửa, duyệt hoặc từ chối skill nháp.
- **Nguồn tự động:** quản trị viên thêm, tắt, xoá nguồn và chọn lịch (mỗi ngày/tuần/tháng/tắt). Trang không đổi thì bỏ qua, không tốn phí. Lịch cần key chung.

## 10. Giao diện

Ở chân thanh bên (hoặc trang Tài khoản trên điện thoại): chọn **VI / EN** để đổi ngôn ngữ giao diện, **Sáng / Tối** để đổi chế độ màu. Lựa chọn lưu trên trình duyệt. Nội dung do bạn và agent viết (ý tưởng, bản thảo, nhật ký) giữ nguyên ngôn ngữ gốc.

## 11. Xử lý sự cố

| Hiện tượng | Cách xử lý |
|---|---|
| Phiên báo "Lỗi" | Mở trang chi tiết bước hoặc tab "Agent đang làm" xem lý do, sửa cấu hình nếu cần, rồi bấm Tiếp tục |
| "no Anthropic API key configured" | Nhập key chung ở Quản trị, hoặc kết nối Claude riêng ở Tài khoản |
| Kiểm tra máy SSH báo từ chối đăng nhập | Chạy lại lệnh ở bước 2 trên đúng tài khoản đã nhập ở bước 1 |
| Kiểm tra máy SSH báo không với tới | Kiểm tra máy đang bật, cổng SSH, VPN/mạng giữa hai máy |
| Bước dừng vì chạm trần chi phí | Tăng trần ở tab Cấu hình rồi bấm Tiếp tục |
| Trang không mở được | `docker compose ps` và `docker compose logs --tail 100` trên server |
| Quên mật khẩu | Quản trị viên đặt lại ở Quản trị → Người dùng |

## 12. Bảo mật và dữ liệu

- Trong Docker, agent của mỗi người chạy dưới một tài khoản hệ điều hành riêng: không đọc được dữ liệu, khoá SSH hay phiên của người khác.
- API key không bao giờ nằm trong tiến trình agent; server gắn key khi chuyển tiếp. Riêng mã gói Pro/Max nằm trong vùng chạy riêng của chính người đó.
- Mỗi người có khoá SSH riêng cho máy chạy.
- Dữ liệu chỉ nằm trên server của bạn, trong thư mục `./data`.

## 13. Dùng AI có trách nhiệm

bonrs ghi lại nguồn gốc mọi phần agent viết và tự soạn **khai báo dùng AI** theo quy định của nhà xuất bản ở bước Hồ sơ nộp. Hãy đọc kỹ, kiểm tra số liệu và trích dẫn, và chịu trách nhiệm về bài trước khi nộp. bonrs không có và sẽ không có tính năng che giấu việc dùng AI.

## 14. Giấy phép

bonrs phát hành theo giấy phép **MIT** (tệp `LICENSE`): bạn được dùng, sửa, phân phối, kể cả cho mục đích thương mại, miễn giữ thông báo bản quyền. Thành phần bên thứ ba và giấy phép của chúng liệt kê trong `THIRD_PARTY_NOTICES.md`. Claude Code do Anthropic phát hành theo điều khoản riêng của Anthropic.
