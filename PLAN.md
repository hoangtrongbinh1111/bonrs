# bonrs — Ý tưởng → bài báo sẵn sàng nộp, tự động, nhiều người dùng, Claude làm agent

Ngày: 2026-10-26 · Bản điều hành (bản mô tả dài hơn ở `PLAN.md` trong dự án sẽ được đồng bộ sau khi duyệt).

## 1. Context

Người dùng (nhà nghiên cứu đa lĩnh vực) muốn một hệ thống web, host trên server cá nhân, nhiều người dùng: nhập ý tưởng + tạp chí đích → tự research (open access/arXiv, yêu cầu upload PDF trả phí), tự profile tạp chí (guideline + bài đã accept), lên kế hoạch, chạy thí nghiệm trên container hoặc server khác (SSH/Slurm) và đọc log, viết bài đúng format và **văn phong nhà khoa học**, phản biện nhiều vòng, đóng gói nộp; lưu **toàn bộ lịch sử** theo phiên idea; lưu **góp ý người dùng** để học; **kho tri thức phân tầng** tự bồi đắp (cào web, người dùng đẩy lên, chuẩn hoá md → skill), admin quản lý kho chung. Mục tiêu tối thượng: bài hợp lý, ít phải sửa.

Đã đọc mã nguồn/tài liệu của ~45 công cụ (3 agent khảo sát + đọc trực tiếp): autoresearch, Auto-Research, writing-driven-autoresearch, Sibyl, ARK, AutoSci, AI-Scientist v2/v3, AgentLaboratory, AI-Researcher, DeepScientist, AutoResearchClaw, NanoResearch, data-to-paper, Idea2Paper, EvoScientist, InternAgent, RD-Agent, Robin, claude-scholar, Agon, dr-claw, PaperQA2, OpenScholar, STORM, LitLLM, LatteReview, gpt-researcher, deer-flow, scite, Sakana reviewer, MARG, DeepReview, TreeReview, AgentReview, LLM-REVal, statcheck, SciScore, chktex, Paperpal/Trinka/Writefull/Jenni, và chính sách AI của 11 nhà xuất bản. Không hệ thống nào kết hợp: journal-fit theo bài accepted thật, văn phong tác giả, kho tri thức tự bồi đắp, đa người dùng có hàng đợi/lịch sử/góp ý, cổng toàn vẹn số liệu–trích dẫn–thống kê. Đó là bonrs.

Thư mục dự án đã có skeleton CLI (agent, pipeline, lit, journal, remote, audit, 10 prompt, 6 skill).

## 2. Quyết định đã chốt với người dùng

| Chủ đề | Quyết định |
|---|---|
| Lĩnh vực | Đa lĩnh vực; `domain` chọn theo run; skill phân tầng general → domain → article type → journal |
| Định dạng | Do tạp chí quyết định (stage 02 đọc guideline → latex/docx); người dùng có thể ép |
| Model | `claude-opus-5-5` mọi stage; đổi được |
| Ngân sách | Tham số theo run; không cố định |
| Remote | Nhiều loại host (ssh / slurm / local-container), mỗi loại form cấu hình riêng, có wizard kết nối + "Test connection"; mặc định chạy trên container |
| Triển khai | Docker Compose, web nhiều người dùng, admin/member |
| Auth Claude | Admin nhập API key trong Settings (hoặc env); member có thể nhập key riêng |
| Kho tri thức | Chung cho mọi người; member tạo skill riêng cho tạp chí/phiên; admin duyệt vào kho chung |
| Lịch sử | Mọi quá trình lưu theo phiên idea (git + events + transcript) |
| Góp ý | Comment/sửa của người dùng được lưu, trả lời trong revise, tổng hợp thành kinh nghiệm |
| HITL | 5 cổng (sau scope, sau gaps/novelty, sau plan, sau quyết định kết quả, trước submission), thông báo, tự tiếp tục sau timeout |
| Cross-model | Tuỳ chọn: nếu admin nhập key thứ hai, ghế Devil's advocate/Area chair dùng model khác họ |
| Sửa đổi AI | Tracked changes, accept/reject theo section, có accept-all |
| Web-only | Mọi thao tác của người dùng trên trình duyệt (tạo run, cổng HITL, upload, comment, host, kho tri thức, admin); CLI chỉ nội bộ cho worker |
| Dấu vết AI | Làm: dọn ký tự Unicode vô hình, NBSP, smart quotes/dash, artifact Markdown, em-dash, nhãn công cụ trên hình vẽ lại từ dữ liệu của người dùng (lint P2 "artifact hygiene"). Không làm: gỡ watermark nguồn gốc (SynthID, nhãn "AI-generated") để giấu việc dùng AI với tạp chí; thay bằng lint văn phong + khai báo AI đúng mẫu nhà xuất bản |

## 3. Kiến trúc

```text
docker compose: bonrs-web (FastAPI+uvicorn, worker thread), zotero-translation (metadata→BibTeX), caddy (tuỳ chọn HTTPS)
volume data/: runs/ knowledge/ bonrs.db uploads/ cache/ (sqlite cache API) ssh/ (key sinh trong container)

bonrs/
  pipeline.py   10 stage, contract file đầu ra, state.json, review loop, HITL gates, git commit mỗi stage
  agent.py      claude -p (stream-json → logs/<stage>.jsonl), system prompt = Goal Anchor (bonrs.yaml) + kb.select(cfg)
  kb.py         kho tri thức: index frontmatter, select theo run (+ bán rã 30 ngày cho experience), ingest, crawl, learn, promote
  lit.py        OpenAlex (key, filter/select) + arXiv + Crossref + Unpaywall + Europe PMC fullTextXML + S2 Recommendations; token-bucket + sqlite cache
  journal.py    profiler: OpenAlex source → DOAJ → Scimago CSV → guide-for-authors (URL map + Playwright fallback) → template map → EQUATOR mapping → 20 bài OA accepted + shape + baseline từ vựng
  cite.py       pipeline xác minh trích dẫn 6 bước (DOI → 2 nguồn khớp ≥0.9 → venue → retraction/DOAJ → claim support → BibTeX canonical qua Zotero)
  registry.py   VerifiedRegistry: exp/results/*.json → registry.json; sinh bảng LaTeX/Markdown; trích số ngược từ bài
  lint.py       30 quy tắc P1/P2/P3 (regex/Python + LLM judge), baseline từ bài accepted
  audit.py      gộp registry + claims.yaml + cite + lint → định nghĩa "done"
  remote.py     type ssh | slurm | local; push/run/tail/status/pull; backoff; doctor (reproduce test)
  web/          FastAPI routes + web/static (vanilla JS + Pico.css): runs, new run, hosts wizard, files, history/diff, comments, tracked changes, knowledge, admin
  db.py         sqlite: users, projects, runs, jobs, events, comments, knowledge_drafts, sources, settings
prompts/        00..09 + kb_distill + review seats
knowledge/      00-general/ 10-domain/ 20-article-type/ 30-journal/ 40-experience/ 50-user/ inbox/ sources.yaml INDEX.json
runs/<slug>/    git repo: bonrs.yaml state.json decisions.md scope.md lit/ journal/ plan/ exp/ paper/ reviews/ comments/ submission/ logs/ knowledge/ provenance.json
```

## 4. Pipeline (10 stage, contract file; HITL gate ⏸ nơi đánh dấu)

| # | Stage | Nội dung chính (gồm phần kế thừa) | Đầu ra bắt buộc |
|---|---|---|---|
| 00 | scope | Debate optimist/skeptic/pragmatist; 1 luận điểm chính; RQ/giả thuyết; query; tạp chí đích + 2 dự phòng; **pivot cam kết trước** cho mọi kết cục ⏸ | `scope.md` |
| 01 | literature | `lit` đa nguồn + PDF upload; RCS (PaperQA2) tóm tắt theo query; STORM perspectives → câu hỏi; tổng hợp theo chủ đề; gaps known→unknown→needed; key_papers có số liệu baseline; novelty.md; REQUEST_FULLTEXT.md ⏸ | `lit/review.md gaps.md key_papers.md refs.bib novelty.md` |
| 02 | journal | profiler đầy đủ (ISSN, scope, quartile, APC, DOAJ, guide-for-authors, template, EQUATOR checklist, 20 bài accepted + shape + **baseline từ vựng**); style_guide kiểm tra được; compliance_checklist; ghi `paper_format`; lưu `30-journal/<slug>.md` | `journal/profile.json author_guidelines.md style_guide.md compliance_checklist.md` |
| 03 | plan | Thiết kế thí nghiệm; **evaluator.md niêm phong** (tiêu chí thành công trước khi chạy); danh sách bảng/hình trước; outline theo style guide với word budget; **plan câu-mức** (LitLLM) ⏸ | `plan.md plan/evaluator.md paper/outline.md exp/README.md` |
| 04 | experiment | experiment_loop (baseline → 1 thay đổi/run → results.tsv → git keep/discard); pilot trước; remote với backoff; **analysis_contract.md** (blocker-first); **registry.json** mọi metric; `qualified: true|false` theo evaluator ⏸ | `exp/results/summary.md registry.json exp/analysis_contract.md exp/notebook.md` |
| 05 | draft | Writer **chỉ đọc artifact**; thứ tự T&F; `\ph/\phm`; bảng sinh từ registry; `claims.yaml`; chip nguồn gốc `\prov`; provenance.json; compile trước khi nhận mỗi edit + length guard; lint P1/P2; văn phong từ style guide + `50-user/voice.md` | `paper/main.tex|main.md paper/main.pdf|docx refs.bib claims.yaml wordcount.md` |
| 06 | review | `audit --final` → MUST; 5 ghế mù (Editor desk-reject, Methodologist nhận bản **bỏ framing**, Domain, Writing/clarity, Devil's advocate) + **Killer reviewer** + **Area chair**; so cặp với 3 bài accepted gần chủ đề; auditor điểm–lý do; `/paper-audit` | `reviews/round_k.md round_k.json` |
| 07 | revise | Chỉ trả lời mục area chair phê chuẩn + comments người dùng; thí nghiệm bổ sung nếu cần; **tracked changes**; response letter; lặp 06↔07: dừng khi 0 CRITICAL/MAJOR, điểm ≥ ngưỡng 2 vòng, chênh ghế ≤2; **trần 3 vòng** ⏸ (sau khi quyết định kết quả) | `paper/response_letter.md` |
| 08 | submission | Cover letter; checklist compliance có bằng chứng; **khai báo AI sinh từ provenance** theo nhà xuất bản; highlights/keywords; similarity self-check; backup plan; **thư biên tập 1 trang** làm trang bàn giao ⏸ | `submission/cover_letter.md checklist.md README.md` |
| 09 | retro | Bài học có category + severity → `40-experience`; quy định tạp chí → `30-journal`; **sở thích người dùng** từ comments + diff người sửa → `50-user/<id>/`; đề xuất nâng tầng (admin duyệt) | `retro.md` |

## 5. Kho tri thức (kb.py)

- Tầng: `00-general` (luật + 8 skill viết: thứ tự/section T&F, CARS, abstract/title, desk-reject, review, bibliometrics, experiment_loop, paper_integrity, ai_policy 11 nhà xuất bản) → `10-domain/<d>` → `20-article-type/<t>` → `30-journal/<publisher>/<slug>` → `40-experience` → `50-user/<id>` → `inbox`.
- Frontmatter chuẩn: `name, level, domain, article_type, journal, tags[], source, source_date, added, severity, confidence, status draft|active|retired, supersedes`. Thân ≤400 từ, mệnh lệnh, kiểm tra được.
- `select(cfg)`: general + domain + article type + journal + experience (lọc tag, trọng số `s·exp(−ln2·Δt/30d)`) + user; chỉ `active`; trần ~60k ký tự.
- `ingest(file|url)`: raw → text (pdftotext/pandoc/html) → `claude -p prompts/kb_distill.md` đối chiếu INDEX → 1–N skill `draft` → hàng đợi admin duyệt (tuỳ chọn tự duyệt confidence ≥0.8).
- `crawl()`: `sources.yaml` (T&F Author Services, Elsevier Researcher Academy, Springer Nature, Wiley, PLOS, IEEE Author Center, Nature masterclass public, arXiv về scientific writing, RSS người dùng thêm); WebFetch trong claude -p; dedupe hash; thread nền theo lịch admin đặt.
- `promote()`: bài học lặp ≥3 run hoặc ≥3 người → đề xuất nâng tầng; admin duyệt.

## 6. Web, đa người dùng, lịch sử, góp ý

- Docker: image python 3.12-slim + node 22 (`@anthropic-ai/claude-code`) + texlive-small + pandoc + poppler + openssh-client + rsync + git + playwright-chromium (fallback fetch guide 403). Non-root. Env: `BONRS_ADMIN_EMAIL/PASSWORD`, `BONRS_MAX_PARALLEL_RUNS`. Settings trong UI: Anthropic key, key thứ hai (OpenAI/Gemini) tuỳ chọn, OpenAlex/S2 key, Unpaywall email, model mặc định, trần ngân sách.
- Auth: scrypt + cookie HMAC; Origin check; CORS off; upload ≤50 MB, chỉ PDF/DOCX/MD/CSV/ZIP; không pickle. Vai trò admin/member như §2.
- Hàng đợi: `jobs` + worker thread, mỗi job = subprocess `bonrs.py run --from --to`; stop = SIGTERM nhóm; cost cộng dồn từ stream-json.
- Lịch sử: run dir là git repo, commit sau mỗi stage/vòng; `events` mọi hành động; transcript `logs/<stage>.jsonl`; tab History: timeline + diff hai mốc; project có nhiều run (rerun/fork/đổi tạp chí); export zip.
- Góp ý: `comments` neo theo file/đoạn/dòng, kind suggest|question|must_fix|style; sửa tại chỗ → diff + comment tự sinh; `comments/open.md` cho stage 07; stage 09 tổng hợp.
- HITL: `hitl/waiting.json` + `response.json`; UI banner "đang chờ bạn" Approve/Edit/Guide/Reject; timeout cấu hình (mặc định 12 h) → tự tiếp tục; email/Telegram thông báo (P-sau).
- Tracked changes: LaTeX gói `texchanges` (`\txadd/\txreplace/\txremove`) + merge; docx revision marks; UI accept/reject theo section, accept-all; PDF cuối sạch.
- Màn hình: Runs · New run (domain/format/model/budget/gates; chọn → form đổi) · Hosts wizard · Run (10 stage, log stream, cost, gates) · Files (md/pdf) · Review letter · Comments · History · Knowledge (cây, tìm, sửa, kéo-thả ingest, draft queue, sources, crawl) · Admin (users, settings, keys).

## 7. Lộ trình (mốc, thứ tự thực hiện)

**M1 — Lõi pipeline chạy end-to-end qua CLI (ước 1–2 ngày)**
1. Thêm skill `experiment_loop.md`, `paper_integrity.md`, `ai_policy.md`; cập nhật prompt 00/01/03/04/05/06/07/09 theo §4; `domain`/`paper_format`/model opus-5-5/remote `type` trong bonrs.yaml.
2. `registry.py` + mở rộng `audit.py` (registry, claims.yaml, \ph/\phm, cite↔bib, placeholder, overclaim); `kb.py` tối thiểu (tầng + frontmatter + select); chuyển 6 skill sang `00-general/` có frontmatter.
3. `remote.py` type ssh/slurm/local + `doctor`; `lit.py` thêm Crossref, Unpaywall, Europe PMC, S2 Recommendations, OpenAlex key + token-bucket + cache sqlite.
4. git init mỗi run + commit mỗi stage; `--output-format stream-json` → `logs/<stage>.jsonl`; HITL gate = file `hitl/waiting.json` (CLI: `bonrs approve <slug>`).
5. `vendor.sh` cài `.claude/skills` (paper-audit, latex-paper-en); `test_bonrs.py` (audit, registry, kb.select, journal.shape, lit dedupe, pipeline.new_run — không mạng).
6. Smoke test thật: stage 00 (≈1–2 USD) → `lit`/`journal` thật → 1 run đầy đủ idea nhỏ chạy local; đo chi phí/thời gian từng stage.

**M2 — Web nhiều người dùng + Docker + lịch sử + góp ý (ước 2–3 ngày)**
7. `db.py`, `web/` (FastAPI), auth, jobs worker, màn hình Runs/New run/Hosts wizard/Run/Files/History/Comments/Admin; Dockerfile + compose (kèm zotero translation server); README cài đặt server + hướng dẫn kết nối SSH/Slurm.
8. Kiểm thử bằng Playwright MCP: tạo user, tạo run, wizard host (form đổi theo type), start stage 00, xem log/scope, comment, history diff, upload PDF.

**M3 — Kho tri thức tự bồi đắp (ước 1–2 ngày)**
9. `kb.ingest/crawl/promote`, `prompts/kb_distill.md`, `sources.yaml` mặc định, thread cào theo lịch, màn hình Knowledge (cây, draft queue, sources), quyền admin/member theo §2.

**M4 — Lớp chất lượng để "ít phải sửa" (ước 2–3 ngày)**
10. `lint.py` thêm nhóm "artifact hygiene": regex Unicode (U+200B–U+200D, U+FEFF, U+00A0, U+2060), chuẩn hoá ‘’“” → '' "" theo style tạp chí, `–/—` theo quy tắc, bỏ `**`/`#` sót, kiểm tra hình không có logo/nhãn công cụ (so pixel góc với mẫu). `journal.py` v2 (DOAJ, Scimago CSV, URL map guide + Playwright fallback, template map, EQUATOR mapping, baseline từ vựng); `cite.py` 6 bước + Zotero BibTeX; `lint.py` 30 quy tắc (P1 trước); panel review v2 (mù, bỏ framing, killer+area chair, so cặp bài accepted, auditor điểm–lý do, cross-model tuỳ chọn, dừng/trần 3 vòng); cổng thống kê; kiểm tra hình–chữ bằng subagent xem ảnh.
11. `paper_format: docx` qua pandoc + revision marks; `50-user/voice.md` từ bài đã đăng của người dùng (few-shot văn phong).

**M5 — Bàn giao ít sửa (ước 1–2 ngày)**
12. Tracked changes (texchanges/docx) + UI accept/reject; chip nguồn gốc `\prov` + nhãn lề; provenance.json → khai báo AI tự sinh; trang "thư biên tập" làm trang đầu bàn giao; export gói nộp.

Sau M5: thông báo Telegram/Slack, chế độ bibliometric/systematic review, rebuttal mode với review thật của tạp chí, Scopus plugin cho ai có entitlement.

## 8. Kiểm chứng

- `python3 test_bonrs.py` xanh ở mọi mốc.
- M1: `bonrs new … && bonrs run <slug> --to 00_scope` tạo scope.md + cost; `lit` có ≥1 `local_pdf`; `journal` có `typical.words`; `audit` bắt đúng lỗi cố ý (phm lệch, cite thiếu, số không có trong registry); run đầy đủ tạo main.pdf, round_*.json, checklist, experience mới.
- M2: `docker compose up` → đăng nhập admin → luồng Playwright ở mục 8; dừng job giữa chừng rồi resume; history diff đúng.
- M3: kéo-thả 1 bài về cách viết Discussion → draft skill đúng frontmatter → duyệt → `kb.select` nạp ở stage kế; crawl 1 nguồn tạo skill mới, chạy lần 2 không trùng.
- M4: lint trên bài mẫu có từ "delve" ×5 báo P2; cite giả bị gắn UNVERIFIED; panel cho bài yếu điểm < ngưỡng và dừng sau 3 vòng; docx build được.
- M5: revise tạo tracked changes, accept-all cho PDF sạch; khai báo AI sinh đúng vị trí theo Elsevier và IEEE.

## 9. Rủi ro

OpenAlex chuyển mô hình credit ($1/ngày với key miễn phí) → ưu tiên `filter`, cache; guide-for-authors nhiều nhà xuất bản chặn bot → Playwright + cho phép dán tay; LLM reviewer chấm lỏng → neo theo bài accepted, không tin điểm tuyệt đối; không tối ưu để né AI-detector, chỉ sửa cho dễ đọc; `bypassPermissions` trong container non-root, mạng thí nghiệm có policy; chi phí/run sẽ đo ở M1 và hiển thị trước khi chạy.
