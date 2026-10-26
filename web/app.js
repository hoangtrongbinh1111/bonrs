"use strict";
// bonrs web UI: hash router + one render function per view. No build step.
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
// Agent/web markdown is untrusted: no raw HTML, and links/images only with safe schemes (blocks javascript:, data:, …).
const num = v => Number.isFinite(+v) ? +v : 0; // agent/user-written numbers: only real numbers reach the markup
const safeUrl = u => { const v = String(u || "").replace(/[\x00-\x20]/g, ""); return /^(https?:|mailto:|#)/i.test(v) || !/^[a-z][\w+.-]*:/i.test(v) ? u : "#"; };
marked.use({ renderer: {
  html: t => esc(typeof t === "string" ? t : t.text),
  link(href, title, text) { return `<a href="${esc(safeUrl(href))}"${title ? ` title="${esc(title)}"` : ""} target="_blank" rel="noopener noreferrer">${text}</a>`; },
  image(href, title, text) { return /^https?:/i.test(String(href || "").trim()) ? `<a href="${esc(safeUrl(href))}" target="_blank" rel="noopener noreferrer">[Hình: ${esc(text || "ảnh ngoài")}]</a>` : esc(text); },  // remote images are never auto-loaded (no tracking beacons)
} });
const md = s => marked.parse(s || "");
const ic = (n, c = "") => `<i data-lucide="${n}" class="ic ${c}" aria-hidden="true"></i>`;
let ME = null, timers = [], RUNS_CACHE = [], routeGen = 0;
const every = (fn, ms) => timers.push(setInterval(fn, ms));

// Lucide swaps <i data-lucide> for inline SVG; batch per frame after every DOM change.
let icq = false;
new MutationObserver(() => { if (icq || !window.lucide) return; icq = true; requestAnimationFrame(() => { icq = false; lucide.createIcons(); }); })
  .observe(document.body, { childList: true, subtree: true });

async function api(path, opt = {}) {
  const gen = routeGen, o = { credentials: "same-origin", ...opt };
  if (o.json !== undefined) { o.body = JSON.stringify(o.json); o.headers = { "Content-Type": "application/json" }; delete o.json; }
  const r = await fetch("/api" + path, o);
  if (r.status === 401) {
    if (path === "/login") { toast("Sai email hoặc mật khẩu", true); throw new Error("bad login"); }
    if (path !== "/me") { if (ME) toast("Phiên đăng nhập đã hết hạn, hãy đăng nhập lại", true); ME = null; location.hash = "#/login"; }
    throw new Error("login required");
  }
  if (gen !== routeGen && (o.method || "GET") === "GET") throw new Error("stale"); // user navigated away: never paint an old page over the new one
  if (!r.ok) { let m = r.statusText; try { m = (await r.json()).detail; } catch {}
    const quiet = [403, 404].includes(r.status) && (o.method || "GET") === "GET"; // page-level: route() shows a friendly banner instead
    if (!quiet) toast("Lỗi: " + m, true); throw Object.assign(new Error(m), { status: r.status }); }
  const ct = r.headers.get("content-type") || "";
  return ct.includes("json") ? r.json() : r.text();
}
function toast(m, err = false) {
  const d = document.createElement("div"); if (err) d.className = "err";
  d.innerHTML = ic(err ? "circle-alert" : "circle-check") + `<span>${esc(m)}</span>`; $("#toast").append(d); setTimeout(() => d.remove(), 4500);
}
const money = n => "$" + (Number(n) || 0).toFixed(2);
const dur = s => { s = Math.round(s || 0); if (s < 60) return s + " giây"; const m = Math.round(s / 60); return m < 60 ? m + " phút" : Math.floor(m / 60) + " giờ " + (m % 60 ? (m % 60) + " phút" : ""); };
const toMs = t => typeof t === "number" ? t * 1000 : Date.parse(t);
function ago(t) {
  const s = (Date.now() - toMs(t)) / 1000; if (!isFinite(s)) return "";
  if (s < 60) return "vừa xong"; if (s < 3600) return Math.floor(s / 60) + " phút trước"; if (s < 86400) return Math.floor(s / 3600) + " giờ trước";
  if (s < 86400 * 30) return Math.floor(s / 86400) + " ngày trước"; return new Date(toMs(t)).toLocaleDateString(LOCALE);
}

const STAGE = {
  "00_scope": ["Giả thuyết", "target", "Đọc bài nền, thảo luận cải tiến, chấm khả năng được accept"],
  "01_literature": ["Tài liệu", "library", "Tìm, đọc, tổng hợp; kiểm tra tính mới"],
  "02_journal": ["Tạp chí", "newspaper", "Đọc quy định và bài đã đăng của tạp chí"],
  "03_plan": ["Kế hoạch", "clipboard-list", "Thiết kế thí nghiệm, chốt tiêu chí thành công"],
  "04_experiment": ["Thí nghiệm", "flask-conical", "Chạy trên máy, đọc log, ghi số liệu"],
  "05_draft": ["Bản thảo", "pen-line", "Viết bài theo văn phong tạp chí"],
  "06_review": ["Phản biện", "users", "6 phản biện ẩn danh + biên tập viên tổng hợp"],
  "07_revise": ["Chỉnh sửa", "git-compare-arrows", "Sửa theo phản biện và góp ý"],
  "08_submission": ["Hồ sơ nộp", "send", "Thư gửi, checklist, khai báo AI"],
  "09_retro": ["Rút kinh nghiệm", "lightbulb", "Ghi bài học vào kho tri thức"],
};
const sv = s => esc((STAGE[s] || [s])[0]); // unknown names come from events/agent output: escape
const STATUS_VI = { running: "Đang chạy", queued: "Chờ lượt chạy", done: "Hoàn tất", failed: "Lỗi", stopped: "Đã dừng", interrupted: "Bị ngắt", waiting: "Chờ duyệt",
  open: "Đang mở", applied: "Đã xử lý", rejected: "Bỏ qua", accept: "Chấp nhận", minor: "Sửa nhỏ", major: "Sửa lớn", reject: "Từ chối" };
const pill = (s, label) => `<span class="pill ${esc(s)}"><span class="dot"></span>${esc(label || STATUS_VI[s] || s)}</span>`;
const GATE = {
  after_scope: ["Chọn giả thuyết (làm hay dừng)", "Agent đã đọc các bài nền, thảo luận hướng cải tiến và chấm khả năng làm thành công cũng như khả năng được accept. Chọn một giả thuyết để làm tiếp, hoặc dừng nếu chưa đáng làm.", ["lit/base_notes.md", "scope.md"]],
  after_literature: ["Sau tài liệu & tính mới", "Xem khoảng trống nghiên cứu và đánh giá tính mới. Nếu có bài trả phí cần đọc, tải PDF lên trước khi đồng ý.", ["lit/novelty.md", "lit/gaps.md", "lit/review.md"]],
  after_plan: ["Sau kế hoạch", "Kế hoạch thí nghiệm và tiêu chí thành công đã niêm phong. Sau bước này agent bắt đầu dùng máy chạy.", ["plan.md", "plan/evaluator.md", "paper/outline.md"]],
  after_results: ["Sau mỗi vòng chỉnh sửa", "Agent vừa sửa bài theo một vòng phản biện. Xem phản biện và thư trả lời trước vòng tiếp theo.", ["paper/response_letter.md", "exp/results/summary.md", "paper/main.pdf"]],
  before_submission: ["Duyệt hồ sơ nộp", "Hồ sơ nộp đã sẵn sàng. Đọc thư biên tập trước, rồi duyệt để agent rút kinh nghiệm.", ["submission/editor_letter.md", "submission/checklist.md", "paper/main.pdf"]],
};
const GATE_AFTER = { after_scope: "00_scope", after_literature: "01_literature", after_plan: "03_plan", after_results: "07_revise", before_submission: "08_submission" };
const DOMAIN_VI = { ml: "Kỹ thuật & tính toán", biomed: "Y sinh", socsci: "Kinh tế & xã hội", other: "Tự xác định" };
const TYPE_VI = { auto: "Loại bài theo tạp chí", research: "Nghiên cứu gốc", review: "Tổng quan", bibliometric: "Trắc lượng thư mục", case: "Báo cáo ca bệnh" };
const SEAT_VI = { "Editor (desk)": "Biên tập (sàng lọc)", Methodologist: "Phương pháp", "Domain expert": "Chuyên môn", "Writing & clarity": "Văn phong", "Devil's advocate": "Phản biện ngược", "Killer reviewer": "Phản biện khó tính" };
const COMMENT_KIND = { suggest: "Gợi ý", must_fix: "Bắt buộc sửa", question: "Câu hỏi", style: "Văn phong", edit: "Sửa trực tiếp" };

function stageState(r, s) {
  if (r.gate && r.gate.stage === s) return "gate";
  if (!r.gate && r.current === s) return "running";
  const busy = ["failed", "queued"].includes(r.job?.status) || (r.job?.status === "running" && !r.current);
  if (r.done.includes(s) || (s === "06_review" && r.reviews?.length && r.current !== s && !busy)) return "done";
  if (s === r.stages.find(x => !r.done.includes(x))) {
    const js = r.job?.status;
    if (js === "failed") return "failed";
    if (!r.gate && ((js === "running" && !r.current) || js === "queued")) return "running";
    return "next";
  }
  return "todo";
}
function runStatus(r) {
  if (r.gate) return ["waiting", "Chờ bạn duyệt"];
  const js = r.job?.status;
  if (["running", "queued", "failed", "stopped", "interrupted"].includes(js)) return [js, STATUS_VI[js]];
  if (r.done.length === r.stages.length) return ["done", "Hoàn tất"];
  return ["", r.done.length ? "Tạm dừng" : "Chưa chạy"];
}
const isLive = r => ["running", "queued"].includes(r.job?.status);

// ---------- language and theme (stored per browser) ----------
const curTheme = () => document.documentElement.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
const prefsHtml = () => `<div class="prefs"><div class="seg" role="radiogroup" aria-label="Ngôn ngữ / Language">${[["vi", "VI"], ["en", "EN"]].map(([k, l]) =>
    `<label title="${k === "vi" ? "Tiếng Việt" : "English"}"><input type="radio" name="p-lang" value="${k}" ${LANG === k ? "checked" : ""} data-setlang><span>${l}</span></label>`).join("")}</div>
  <div class="seg" role="radiogroup" aria-label="Giao diện sáng hoặc tối">${[["light", "sun", "Sáng"], ["dark", "moon", "Tối"]].map(([k, i, l]) =>
    `<label><input type="radio" name="p-theme" value="${k}" ${curTheme() === k ? "checked" : ""} data-settheme><span>${ic(i, "sm")}${l}</span></label>`).join("")}</div></div>`;
document.addEventListener("change", e => {
  const t = e.target;
  if (t.matches("[data-settheme]")) { document.documentElement.dataset.theme = t.value; try { localStorage.setItem("bonrs.theme", t.value); } catch {} $$("[data-settheme]").forEach(x => x.checked = x.value === t.value); }
  if (t.matches("[data-setlang]") && t.value !== LANG) { try { localStorage.setItem("bonrs.lang", t.value); } catch {} location.reload(); }
});

// ---------- shell ----------
function nav() {
  const side = $("#side"); side.hidden = !ME;
  if (!ME) return;
  const page = location.hash.split("/")[1] || "runs";
  const waiting = RUNS_CACHE.filter(r => r.gate).length;
  const items = [["runs", "Phiên nghiên cứu", "layout-grid", waiting], ["new", "Ý tưởng mới", "circle-plus"], ["hosts", "Máy chạy", "server"],
    ["kb", "Kho tri thức", "book-open"], ...(ME.role === "admin" ? [["admin", "Quản trị", "shield"]] : []), ["guide", "Hướng dẫn", "life-buoy"]];
  $("#nav").innerHTML = items.map(([k, l, i, n]) => { const on = page === k || (k === "runs" && page === "run");
    return `<a href="#/${k}" class="${on ? "on" : ""}" ${on ? 'aria-current="page"' : ""} title="${l}">${ic(i)}<span>${l}</span>${n ? `<span class="count" aria-label="${n} phiên chờ duyệt">${n}</span>` : ""}</a>`; }).join("");
  $("#who").innerHTML = `<a href="#/me" title="Tài khoản"><span class="avatar">${esc(ME.email[0].toUpperCase())}</span><span class="who"><b>${esc(ME.email)}</b><span class="muted small">${ME.role === "admin" ? "Quản trị viên" : "Thành viên"}</span></span></a>${prefsHtml()}`;
}
let refreshTimer = null;
function autoRefresh(fn, ms) { // one refresh loop per page: views that re-render themselves must not stack intervals
  clearInterval(refreshTimer);
  refreshTimer = setInterval(() => {
    const a = document.activeElement;
    if ($("#dlg").open || (a && /^(INPUT|TEXTAREA|SELECT)$/.test(a.tagName) && $("#app").contains(a)) || $("#gnote")?.value || $("#ta") || $("details.more[open]") || getSelection().toString()) return;
    fn();
  }, ms);
}
async function route() {
  timers.forEach(clearInterval); timers = []; clearInterval(refreshTimer); const gen = ++routeGen;
  if (!ME) { try { ME = await api("/me"); } catch { ME = null; } }
  const [, page = "runs", a, b, c] = location.hash.split("/");
  if (!ME && !["login", "guide"].includes(page)) return (location.hash = "#/login");
  if (page === "admin" && ME.role !== "admin") return (location.hash = "#/runs");
  if (ME && !RUNS_CACHE.length && page !== "runs" && page !== "login") api("/runs").then(r => { RUNS_CACHE = r; nav(); }).catch(() => {});
  nav();
  const app = $("#app");
  const views = { login: vLogin, guide: vGuide, runs: vRuns, new: vNew, run: vRun, hosts: vHosts, kb: vKB, admin: vAdmin, me: vMe };
  try { await (views[page] || vRuns)(app, a, b, c && decodeURIComponent(c)); }
  catch (e) { if (!["login required", "stale", "bad login"].includes(e.message) && gen === routeGen) app.innerHTML = `<div class="wrap"><div class="banner bad"><span class="bic">${ic("circle-alert")}</span><div><h2>${e.status === 403 ? "Bạn không có quyền xem trang này" : e.status === 404 ? "Không tìm thấy" : "Không tải được trang"}</h2><p>${e.status === 403 ? "Phiên này thuộc về người khác. Hãy nhờ quản trị viên hoặc chủ phiên." : e.status === 404 ? "Trang hoặc phiên này không còn tồn tại." : esc(e.message)}</p><a class="btn ghost sm" href="#/runs">Về danh sách phiên</a></div></div></div>`; }
}
let lastPage = "";
window.addEventListener("hashchange", () => { const p = location.hash.split("/").slice(0, 3).join("/"); route(); if (p !== lastPage) $("#app").focus({ preventScroll: true }); lastPage = p; });
route();
const head = (title, sub = "", actions = "", crumb = "") => `<div class="phead"><div>${crumb}<h1>${title}</h1>${sub ? `<p class="sub">${sub}</p>` : ""}</div><div class="actions">${actions}</div></div>`;

// ---------- dialog helpers ----------
function dialog(html, onSubmit) {
  const d = $("#dlg"); d.innerHTML = `<form method="dialog">${html}</form>`; d.showModal();
  const f = $("form", d);
  $$("[data-close]", d).forEach(b => b.onclick = e => { e.preventDefault(); d.close(); });
  f.onsubmit = async e => { e.preventDefault(); const btn = $("button:not([data-close])", f.lastElementChild); if (btn) btn.disabled = true;
    try { await onSubmit(new FormData(f), f); d.close(); } catch {} finally { if (btn) btn.disabled = false; } };
  setTimeout(() => $("textarea, input:not([type=radio])", f)?.focus(), 30);
}
function commentDialog(slug, path = "", quote = "", after) {
  dialog(`<h2>${ic("message-square-plus")} Góp ý ${path ? `cho <code>${esc(path)}</code>` : "chung"}</h2>
    ${quote ? `<div class="cmt" style="border:0;padding:0;display:block"><blockquote>${esc(quote.slice(0, 400))}</blockquote></div>` : ""}
    <div style="margin-bottom:.9rem"><span class="small" style="font-weight:600;color:var(--fg-2)">Loại góp ý</span><div class="seg" role="radiogroup" aria-label="Loại góp ý" style="margin-top:.35rem">${Object.entries(COMMENT_KIND).filter(([k]) => k !== "edit").map(([k, v], i) =>
      `<label><input type="radio" name="kind" value="${k}" ${i ? "" : "checked"}><span>${v}</span></label>`).join("")}</div></div>
    <label>Nội dung<textarea name="body" rows="4" required placeholder="Agent sẽ xử lý góp ý này ở vòng chỉnh sửa kế tiếp."></textarea></label>
    <div class="dfoot"><button type="button" class="btn ghost" data-close>Huỷ</button><button class="btn">${ic("send")} Gửi góp ý</button></div>`,
    async f => { await api(`/runs/${slug}/comments`, { method: "POST", json: { path, quote, body: f.get("body"), kind: f.get("kind") } }); toast("Đã lưu góp ý"); after?.(); });
}

// ---------- guide: docs/GUIDE.<lang>.md rendered with a table of contents ----------
async function vGuide(app) {
  if (!ME) $("#side").hidden = true;
  const text = await (await fetch(`/api/guide?lang=${LANG}`)).text();
  const slug = (t, i) => "g" + i + "-" + t.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/đ/g, "d").replace(/[^a-z0-9]+/g, "-").slice(0, 40);
  app.innerHTML = `<div class="wrap">${ME ? "" : `<p><a href="#/login">${ic("arrow-left", "sm")} Đăng nhập</a></p>`}<div class="guide"><nav class="card toc" aria-label="Mục lục" id="toc"></nav><article class="card prose" id="gd" data-raw>${md(text)}</article></div></div>`;
  const hs = $$("#gd h2, #gd h3");
  hs.forEach((h, i) => h.id = slug(h.textContent, i));
  $("#toc").innerHTML = `<b class="small">Mục lục</b>` + hs.map(h => `<a href="#" data-to="${h.id}" class="${h.tagName === "H3" ? "l3" : ""}">${esc(h.textContent)}</a>`).join("");
  $$("[data-to]", app).forEach(a => a.onclick = e => { e.preventDefault(); document.getElementById(a.dataset.to).scrollIntoView({ behavior: "smooth" }); });
}

// ---------- login ----------
function vLogin(app) {
  $("#side").hidden = true;
  app.innerHTML = `<div class="login"><div class="art"><div class="brand" style="color:inherit;padding:0"><span class="logo" style="background:#fff;color:#0F766E">b</span><span>bonrs</span></div>
      <div><h1>Từ ý tưởng đến bài báo sẵn sàng nộp</h1><p>Agent tự tìm tài liệu, đọc yêu cầu tạp chí, chạy thí nghiệm, viết và phản biện nhiều vòng. Bạn chỉ duyệt ở những điểm quan trọng.</p></div>
      <div class="flow">${Object.values(STAGE).map(([l, i]) => `<div><span>${ic(i)}</span>${l}</div>`).join("")}</div></div>
    <form id="f"><h2>Đăng nhập</h2><p class="muted">Dùng tài khoản do quản trị viên cấp.</p>
      <label>Email<input name="email" type="email" required autocomplete="username"></label>
      <label>Mật khẩu<input name="password" type="password" required autocomplete="current-password"></label>
      <button class="btn" style="width:100%">${ic("log-in")} Đăng nhập</button>
      <p class="muted small" style="margin-top:1rem;text-align:center"><a href="#/guide">${ic("life-buoy", "sm")} Hướng dẫn cài đặt và sử dụng</a></p></form>${prefsHtml()}</div>`;
  $("#f").onsubmit = async e => { e.preventDefault(); const f = new FormData(e.target);
    await api("/login", { method: "POST", json: Object.fromEntries(f) }); ME = null; location.hash = "#/runs"; };
}

// ---------- runs dashboard ----------
const mini = r => `<div class="mini" aria-hidden="true">${r.stages.map(s => `<i class="${stageState(r, s)}" title="${sv(s)}"></i>`).join("")}</div>`;
async function vRuns(app) {
  const runs = RUNS_CACHE = await api("/runs"); nav();
  const f = sessionStorage.getItem("runFilter") || "all";
  const live = runs.filter(isLive).length, wait = runs.filter(r => r.gate).length, done = runs.filter(r => r.done.length === r.stages.length).length;
  const total = runs.reduce((a, r) => a + (r.cost || 0), 0);
  const match = r => ({ all: true, live: isLive(r), wait: !!r.gate, done: r.done.length === r.stages.length }[f]);
  const q = (sessionStorage.getItem("runQ") || "").toLowerCase();
  const list = runs.filter(r => match(r) && (!q || `${r.idea} ${r.journal}`.toLowerCase().includes(q)));
  app.innerHTML = `<div class="wrap">${head("Phiên nghiên cứu", "Mỗi phiên là một ý tưởng đi qua 10 bước để thành bài báo.", `<a class="btn" href="#/new">${ic("plus")} Ý tưởng mới</a>`)}
    <div class="kpis">
      <button class="kpi" data-f="all"><span class="kic">${ic("folder-kanban")}</span><span><b>${runs.length}</b><small>Tổng số phiên</small></span></button>
      <button class="kpi" data-f="live"><span class="kic b">${ic("activity")}</span><span><b>${live}</b><small>Đang chạy</small></span></button>
      <button class="kpi" data-f="wait"><span class="kic w">${ic("hand")}</span><span><b>${wait}</b><small>Chờ bạn duyệt</small></span></button>
      <button class="kpi" data-f="done"><span class="kic">${ic("badge-check")}</span><span><b>${done}</b><small>Đã hoàn tất</small></span></button>
      <div class="kpi"><span class="kic o">${ic("wallet")}</span><span><b>${money(total)}</b><small>Chi phí (giá API tương đương)</small></span></div>
    </div>
    <div class="filter" role="group" aria-label="Lọc phiên">${[["all", "Tất cả"], ["live", "Đang chạy"], ["wait", "Chờ duyệt"], ["done", "Hoàn tất"]].map(([k, l]) =>
      `<button data-f="${k}" class="${f === k ? "on" : ""}" aria-pressed="${f === k}">${l}</button>`).join("")}
      <input id="q" type="search" placeholder="Tìm theo ý tưởng hoặc tạp chí…" value="${esc(q)}" aria-label="Tìm phiên"></div>
    ${list.length ? `<div class="rgrid">${list.map((r, i) => { const [st, lb] = runStatus(r); const rv = r.reviews?.at(-1);
      return `<a class="rcard ${r.gate ? "gate" : ""}" href="#/run/${esc(r.slug)}" style="--i:${i}">
        <div class="top">${pill(st, lb)}<span class="chip">${esc(DOMAIN_VI[r.domain] || r.domain || "")}</span></div>
        <h2>${esc(r.idea || r.slug)}</h2><div class="jr">${ic("newspaper", "sm")} ${esc(r.journal)}</div>
        ${mini(r)}
        ${r.gate ? `<div class="cta-gate">${ic("hand", "sm")} Chờ bạn duyệt: ${esc(GATE[r.gate.gate]?.[0] || r.gate.gate)}${(() => { const l = gateLeft(r); return l == null ? "" : l > 0 ? ` · tự đi tiếp sau ${dur(l / 1000)}` : " · quá hạn"; })()}</div>` : ""}
        <div class="foot"><span>${ic("list-checks", "sm")}<b>${r.done.length}/10</b> bước</span><span>${ic("wallet", "sm")}<b>${money(r.cost)}</b></span>
          ${rv ? `<span>${ic("star", "sm")}<b>${rv.score}</b>/10</span>` : ""}<span>${ic("clock", "sm")}${ago(r.created)}</span>
          ${ME.role === "admin" && r.email ? `<span>${ic("user", "sm")}${esc(r.email.split("@")[0])}</span>` : ""}</div></a>`; }).join("")}</div>`
      : runs.length ? `<div class="empty"><h2>Không có phiên nào khớp bộ lọc</h2></div>`
      : `<div class="empty card"><span class="big">${ic("sparkles", "lg")}</span><h2>Chưa có phiên nào</h2><p>Bắt đầu bằng cách mô tả một ý tưởng nghiên cứu và chọn tạp chí bạn muốn nộp.</p><a class="btn" href="#/new">${ic("plus")} Tạo ý tưởng đầu tiên</a></div>`}</div>`;
  $$("[data-f]", app).forEach(b => b.onclick = () => { sessionStorage.setItem("runFilter", b.dataset.f); vRuns(app); });
  let tm; const g = routeGen; $("#q").oninput = e => { clearTimeout(tm); tm = setTimeout(() => { if (g !== routeGen) return; sessionStorage.setItem("runQ", e.target.value); vRuns(app).then(() => { const i = $("#q"); i.focus(); i.setSelectionRange(99, 99); }); }, 250); };
  autoRefresh(() => vRuns(app), runs.some(isLive) ? 5000 : 20000);
}

// ---------- new run ----------
// ---------- shared controls: model list, budget with a suggestion, auto-continue with hours and minutes ----------
const MODEL_INFO = [["claude-opus-5-5", "Claude Opus 5.5", "mặc định, khuyên dùng cho cả quy trình"], ["claude-fable-5-1", "Claude Fable 5.1", "thế hệ mới nhất"],
  ["claude-sonnet-5-5", "Claude Sonnet 5.5", "nhanh và rẻ hơn"], ["claude-haiku-5-5", "Claude Haiku 5.5", "rẻ nhất, chỉ nên chạy thử"]];
const modelName = id => (MODEL_INFO.find(m => m[0] === id) || [id, id])[1];
const modelSel = (name, v) => `<select name="${name}" data-model>${MODEL_INFO.map(([id, l, d]) => `<option value="${id}" ${id === v ? "selected" : ""}>${l} · ${d}</option>`).join("")}
  ${v && !MODEL_INFO.some(m => m[0] === v) ? `<option value="${esc(v)}" selected>${esc(v)}</option>` : ""}</select>`;
const budgetField = (name, v, tag = "") => `<div class="budget"><label><span class="lblrow">Trần chi phí mỗi bước (USD) ${tag}</span><input name="${name}" type="number" min="1" max="1000" step="1" value="${esc(v ?? "")}" data-budget></label><div class="bh" aria-live="polite"></div></div>`;
async function budgetHint(root, fill) {
  const inp = $("[data-budget]", root), box = $(".bh", root), model = $("[data-model]", root)?.value || "";
  if (!inp) return null;
  inp.oninput = () => { inp.dataset.touched = 1; budgetHint(root, false); };
  let h; try { h = await api("/budget-hint?model=" + encodeURIComponent(model)); } catch { return null; }
  if (fill && !inp.dataset.touched) inp.value = h.recommended;
  box.innerHTML = `<div class="rec">${ic("lightbulb", "sm")}<div>Đề xuất <b>${money(h.recommended)}</b> mỗi bước${+inp.value !== h.recommended ? ` <button type="button" class="linkbtn" data-use>Dùng mức này</button>` : ""}
    <small>${h.n ? `Các bước đã chạy trên server ${h.basis === "model" ? "với model này" : "(mọi model)"}: trung bình ${money(h.mean)}, cao nhất ${money(h.max)}, ${h.n} lần.` : "Chưa có lần chạy nào trên server: dùng mức mặc định."}
    Đây là trần an toàn: agent chỉ tốn phần thực dùng; bước nào chạm trần sẽ dừng lại.${h.est_run_total ? ` Cả phiên thường tốn khoảng ${money(h.est_run_total)}.` : ""}</small></div></div>`;
  $("[data-use]", box) && ($("[data-use]", box).onclick = () => { inp.value = h.recommended; inp.dataset.touched = 1; budgetHint(root, false); inp.dispatchEvent(new Event("change", { bubbles: true })); });
  return h;
}
const hm = hours => { const t = Math.round(num(hours) * 60); return [Math.floor(t / 60), t % 60]; };
const fmtWait = hours => { const [h, m] = hm(hours); return num(hours) > 0 ? `tự đi tiếp sau ${h ? h + " giờ" : ""}${h && m ? " " : ""}${m ? m + " phút" : ""}` : "luôn chờ bạn duyệt"; };
function waitCtl(name, hours) {
  const on = num(hours) > 0, [h, m] = on ? hm(hours) : [12, 0];
  return `<div class="waitctl" data-wait="${name}"><label class="switch"><input type="checkbox" name="${name}__on" ${on ? "checked" : ""}> Tự đi tiếp khi không ai duyệt</label>
    <div class="hm" ${on ? "" : "hidden"}><span>sau</span><input type="number" name="${name}__h" min="0" max="999" value="${h}" aria-label="Số giờ"><span>giờ</span>
      <input type="number" name="${name}__m" min="0" max="59" step="5" value="${m}" aria-label="Số phút"><span>phút</span></div>
    <p class="hint" data-on ${on ? "" : "hidden"}>Hết thời gian này mà chưa ai duyệt thì agent đi tiếp. Cổng chọn giả thuyết luôn chờ bạn.</p>
    <p class="hint" data-off ${on ? "hidden" : ""}>Agent luôn dừng chờ bạn duyệt ở mỗi cổng đã bật.</p></div>`;
}
function bindWait(root) {
  $$("[data-wait]", root).forEach(w => { const cb = $("input[type=checkbox]", w);
    cb.addEventListener("change", () => { $(".hm", w).hidden = !cb.checked; $("[data-on]", w).hidden = !cb.checked; $("[data-off]", w).hidden = cb.checked; }); });
}
const readWait = (f, n) => f.has(n + "__on") ? Math.max(1 / 60, num(f.get(n + "__h")) + num(f.get(n + "__m")) / 60) : 0;
const hmCtl = (name, hours, label, tag = "") => { const [h, m] = hm(hours); return `<div class="hmrow"><span class="lbl lblrow">${label} ${tag}</span><div class="hm"><input type="number" name="${name}__h" min="0" max="240" value="${h}" aria-label="${label}: giờ"><span>giờ</span>
  <input type="number" name="${name}__m" min="0" max="59" step="5" value="${m}" aria-label="${label}: phút"><span>phút</span></div></div>`; };
const readHM = (f, n) => num(f.get(n + "__h")) + num(f.get(n + "__m")) / 60;

// ---------- idea assistant: AI drafts, 4 roles debate, final brief ----------
const ROLE_IC = { "Người đề xuất": ["lightbulb", ""], "Phản biện": ["swords", "bad"], "Biên tập tạp chí": ["newspaper", "run"], "Người thực hiện": ["wrench", "ok"] };
function ideaAssist(form) {
  const box = $("#aip"), rounds = [];
  const ask = async (extra = {}) => {
    const f = new FormData(form);
    box.innerHTML = `<div class="assist"><p class="loading"><span class="spin"></span> AI đang viết lại ý tưởng và cho 4 vai tranh luận (thường 30–90 giây)…</p></div>`;
    $("#ai").disabled = true;
    try {
      const { id } = await api("/assist/idea", { method: "POST", json: { idea: f.get("idea"), journal: f.get("journal"), domain: f.get("domain"), base_papers: f.get("base_papers"), model: f.get("model"), ...extra } });
      let a; for (let i = 0; i < 150; i++) { await new Promise(r => setTimeout(r, 2000)); a = await api("/assist/" + id); if (a.status !== "running") break; }
      if (a.status !== "done") throw new Error(a.error || "hết thời gian chờ");
      rounds.push(a.result); draw();
    } catch (e) { box.innerHTML = `<div class="banner bad" style="margin:.8rem 0 0"><span class="bic">${ic("circle-alert")}</span><div><h2>AI chưa trả lời được</h2><p>${esc(e.message)}</p></div></div>`; }
    finally { $("#ai").disabled = false; }
  };
  const draw = () => {
    const r = rounds.at(-1), n = rounds.length;
    box.innerHTML = `<div class="assist"><div class="assist-head"><span class="chip">${ic("sparkles", "sm")} Vòng ${n}</span><b>${esc(r.title)}</b>${r.cost ? `<span class="muted small">${money(r.cost)}</span>` : ""}</div>
      <details class="debate" ${n === 1 ? "open" : ""}><summary>${ic("messages-square", "sm")} Tranh luận (${r.debate.length} lượt)</summary>
        ${r.debate.map(d => { const [i, c] = ROLE_IC[d.role] || ["user", ""]; return `<div class="turn"><span class="tic ${c}">${ic(i, "sm")}</span><div><b>${esc(d.role)}</b><p>${esc(d.say)}</p></div></div>`; }).join("")}
        ${r.journal_fit ? `<p class="muted small">${ic("newspaper", "sm")} ${esc(r.journal_fit)}</p>` : ""}</details>
      <label>Bản chốt sau tranh luận (sửa trực tiếp được)<textarea id="aifinal" rows="11">${esc(r.final)}</textarea></label>
      ${r.changes.length ? `<div class="small"><b>Đã sửa sau tranh luận:</b><ul>${r.changes.map(x => `<li>${esc(x)}</li>`).join("")}</ul></div>` : ""}
      ${r.questions.length ? `<div class="qs"><b class="small">AI cần bạn làm rõ (trả lời câu nào cũng được):</b>${r.questions.map((q, i) => `<label>${esc(q)}<input data-q="${i}" placeholder="Câu trả lời của bạn…"></label>`).join("")}</div>` : ""}
      <label>Góp ý thêm cho AI (tuỳ chọn)<textarea id="aifb" rows="2" placeholder="Ví dụ: chỉ dùng dữ liệu công khai, tập trung vào pin LFP…"></textarea></label>
      <div class="actions"><button type="button" class="btn" id="aiuse">${ic("check", "sm")} Dùng bản này</button>
        <button type="button" class="btn ghost" id="aimore">${ic("messages-square", "sm")} Tranh luận thêm một vòng</button><button type="button" class="btn quiet" id="aix">Đóng</button></div></div>`;
    $("#aiuse").onclick = () => { form.idea.value = $("#aifinal").value; const d = form.querySelector(`[name=domain][value="${r.domain}"]`); if (d && r.domain !== "other") d.checked = true;
      box.innerHTML = `<p class="muted small" style="margin-top:.5rem">${ic("circle-check", "sm")} Đã điền bản chốt vào ô ý tưởng. Bạn vẫn sửa tiếp được.</p>`; form.idea.focus(); };
    $("#aix").onclick = () => box.innerHTML = "";
    $("#aimore").onclick = () => { const ans = r.questions.map((q, i) => [q, $(`[data-q="${i}"]`, box).value.trim()]).filter(x => x[1]).map(([q, a]) => `Hỏi: ${q}\nĐáp: ${a}`);
      ask({ previous: $("#aifinal").value, feedback: [...ans, $("#aifb").value.trim()].filter(Boolean).join("\n") }); };
  };
  return ask;
}

async function vNew(app) {
  const [hosts, DEF] = await Promise.all([api("/hosts"), api("/defaults")]);
  const opt = (name, v, l, i, d, on) => `<label class="opt"><input type="radio" name="${name}" value="${v}" ${on ? "checked" : ""}><span>${ic(i)}${l}<small>${d}</small></span></label>`;
  app.innerHTML = `<div class="wrap">${head("Ý tưởng mới", "Mô tả ý tưởng và tạp chí đích. Phần còn lại agent tự làm, dừng ở những cổng bạn chọn.", "",
      `<div class="crumb"><a href="#/runs">Phiên nghiên cứu</a>${ic("chevron-right", "sm")}Ý tưởng mới</div>`)}
    <form id="f" class="cols newrun"><div class="stack">
      <section class="card"><h2><span class="step-n">1</span> Ý tưởng</h2>
        <label>Mô tả ý tưởng hoặc hướng nghiên cứu<textarea name="idea" rows="6" required placeholder="Muốn nghiên cứu gì, vì sao, dữ liệu hoặc thí nghiệm dự kiến… Chỉ cần vài dòng thô, AI có thể viết lại giúp bạn."></textarea></label>
        <div class="aibar"><button type="button" class="btn ghost" id="ai">${ic("sparkles", "sm")} AI viết & tranh luận giúp</button>
          <span class="muted small">AI viết thành bản mô tả đủ ý (vấn đề, giả thuyết, dữ liệu, phương pháp, đóng góp, phạm vi), cho 4 vai tranh luận rồi chốt bản cuối. Bạn duyệt trước khi dùng.</span></div>
        <div id="aip"></div></section>
      <section class="card"><h2><span class="step-n">2</span> Bài báo nền</h2>
        <p class="muted small">Vài bài bạn muốn dựa vào để cải tiến. Agent đọc kỹ từng bài (phương pháp, số liệu, hạn chế, hướng mở), thảo luận các hướng cải tiến, rồi chấm khả năng thành công và khả năng được accept của từng giả thuyết trước khi làm.</p>
        <div class="drop" id="bdrop">${ic("files", "lg")}<div>Kéo thả PDF, DOCX hoặc MD vào đây, hoặc chọn tệp (tối đa 20)</div><input type="file" name="base" multiple accept=".pdf,.docx,.md,.txt" aria-label="Chọn bài báo nền"></div>
        <label style="margin-top:1rem">Hoặc DOI, đường dẫn, tên bài (mỗi dòng một bài)<textarea name="base_papers" rows="3" placeholder="10.1016/j.est.2023.107734\nhttps://arxiv.org/abs/2401.01234\nTên bài báo…"></textarea>
        <span class="hint">Không có bài nào thì agent tự chọn 3–5 bài sát ý tưởng nhất và nói rõ điều đó.</span></label></section>
      <section class="card"><h2><span class="step-n">3</span> Tạp chí</h2>
        <div class="grid2"><label>Tạp chí đích<input name="journal" list="jl" required placeholder="Gõ ít nhất 3 ký tự để gợi ý…" autocomplete="off"><datalist id="jl"></datalist>
          <span class="hint">Gợi ý từ OpenAlex. Loại bài, định dạng và văn phong sẽ theo tạp chí này.</span></label>
          <label>Tạp chí dự phòng<input name="backup_journals" placeholder="Phân cách bằng dấu phẩy"><span class="hint">Dùng khi kết quả không đủ mạnh cho tạp chí đích.</span></label></div></section>
      <section class="card"><h2><span class="step-n">4</span> Lĩnh vực & định dạng</h2>
        <fieldset class="bare"><legend>Lĩnh vực</legend><div class="opts">
          ${opt("domain", "ml", "Kỹ thuật & tính toán", "cpu", "ML, kỹ thuật, khoa học máy tính", true)}${opt("domain", "biomed", "Y sinh", "heart-pulse", "Y học, sinh học, khoa học sự sống")}
          ${opt("domain", "socsci", "Kinh tế & xã hội", "landmark", "Kinh tế, quản trị, KHXH")}${opt("domain", "other", "Tự xác định", "compass", "Agent tự nhận diện lĩnh vực")}</div></fieldset>
        <fieldset class="bare"><legend>Định dạng bản thảo</legend><div class="opts">
          ${opt("format", "auto", "Theo tạp chí", "wand-sparkles", "Theo hướng dẫn tác giả của tạp chí", true)}${opt("format", "latex", "LaTeX", "sigma", "Template của nhà xuất bản")}${opt("format", "docx", "Word", "file-text", "Tệp .docx")}</div></fieldset></section>
      <section class="card"><h2><span class="step-n">5</span> Máy chạy thí nghiệm</h2>
        <div class="opts"><label class="opt"><input type="checkbox" name="hosts" value="local" checked><span>${ic("container")}Máy chủ bonrs<small>Có sẵn, không cần cài</small></span></label>
          ${hosts.filter(h => h.type !== "local").map(h => `<label class="opt"><input type="checkbox" name="hosts" value="${h.id}"><span>${ic(h.type === "slurm" ? "network" : "server")}${esc(h.name)}<small>${esc(h.config.ssh || h.type)}</small></span></label>`).join("")}</div>
        <p class="muted small">Chọn nhiều máy thì agent gửi mỗi lần chạy sang máy đang rảnh nhất. ${hosts.length ? "" : `Muốn dùng máy GPU riêng? <a href="#/hosts">Thêm máy</a>.`}</p>
        </section>
      <section class="card"><details id="adv"><summary class="advsum"><span class="step-n">6</span><span><b>Model, chi phí, thời gian chờ duyệt</b><small id="advsum">Đang tải mặc định…</small></span>${ic("chevron-down", "sm")}</summary>
        <div class="grid2" style="margin-top:1rem"><label>Model${modelSel("model", DEF.model)}</label>${budgetField("budget", "")}</div>
        <fieldset class="bare"><legend>Khi agent dừng ở cổng duyệt</legend>${waitCtl("gate_timeout_hours", DEF.gate_timeout_hours)}</fieldset></details></section>
    </div>
    <aside class="card sticky" aria-label="Lộ trình của phiên"><h2>${ic("route")} Lộ trình của phiên</h2>
      <p class="muted small">Bật công tắc ở bước nào thì agent dừng chờ bạn duyệt sau bước đó.</p>
      <ol class="tl">${Object.keys(STAGE).map(s => { const g = Object.keys(GATE_AFTER).find(k => GATE_AFTER[k] === s);
        return `<li><span class="tic">${ic(STAGE[s][1], "sm")}</span><span class="what"><b>${STAGE[s][0]}</b><small>${STAGE[s][2]}</small></span>
          ${g === "after_scope" ? `<span class="chip" title="Luôn dừng để bạn chọn giả thuyết">${ic("lock", "sm")} luôn dừng</span>`
            : g ? `<label class="switch" title="Dừng chờ duyệt sau bước này"><input type="checkbox" name="gates" value="${g}" checked aria-label="Dừng chờ duyệt: ${GATE[g][0]}"></label>` : "<span></span>"}</li>`; }).join("")}</ol>
      <label class="switch" style="margin:1rem 0"><input type="checkbox" name="start" checked> Bắt đầu chạy ngay</label>
      <button class="btn" id="create" style="width:100%">${ic("rocket")} Tạo phiên</button>
      <p class="muted small" style="margin-top:.7rem" id="est"></p></aside></form></div>`;
  const form = $("#f"), adv = $("#adv");
  const sum = () => { const f = new FormData(form); $("#advsum").textContent = `${modelName(f.get("model"))} · trần ${money(f.get("budget"))}/bước · ${fmtWait(readWait(f, "gate_timeout_hours"))}`; };
  const hint = async () => { const h = await budgetHint(adv, true); sum();
    $("#est").textContent = h?.est_run_total ? `Ước tính cả phiên khoảng ${money(h.est_run_total)} giá API (theo các phiên đã chạy); nếu dùng gói Claude thì trừ vào hạn mức.` : "Nếu dùng gói Claude, chi phí trừ vào hạn mức của gói thay vì tính tiền."; };
  bindWait(adv); adv.addEventListener("change", e => { if (e.target.matches("[data-model]")) hint(); else sum(); }); adv.addEventListener("input", sum); hint();
  const assist = ideaAssist(form);
  $("#ai").onclick = () => { if (form.idea.value.trim().length < 5) { form.idea.focus(); return toast("Viết vài từ về ý tưởng trước", true); } assist(); };
  const jl = $("#jl"); let tm;
  $("[name=journal]").oninput = e => { clearTimeout(tm); const q = e.target.value; if (q.length < 3) return;
    tm = setTimeout(async () => { try { const r = await (await fetch("https://api.openalex.org/autocomplete/sources?q=" + encodeURIComponent(q))).json();
      jl.innerHTML = r.results.map(x => `<option value="${esc(x.display_name)}">${esc(x.hint || "")}</option>`).join(""); } catch {} }, 300); };
  dropZone($("#bdrop"));
  $("#f").onsubmit = async e => { e.preventDefault(); const f = new FormData(e.target); const files = f.getAll("base").filter(x => x && x.size); f.delete("base");
    if (files.length > 20) return toast("Tối đa 20 bài báo nền", true);
    const b = Object.fromEntries([...f].filter(([k]) => !k.includes("__"))); b.gates = ["after_scope", ...f.getAll("gates")]; b.hosts = f.getAll("hosts").map(v => v === "local" ? v : Number(v));
    b.budget = b.budget ? Number(b.budget) : null; b.gate_timeout_hours = readWait(f, "gate_timeout_hours");
    const startNow = f.has("start"); b.start = false;
    $("#create").disabled = true;
    try {
      const r = await api("/runs", { method: "POST", json: b });
      if (files.length) { const u = new FormData(); u.append("where", "lit/base"); files.forEach(x => u.append("files", x)); await api(`/runs/${r.slug}/upload`, { method: "POST", body: u }); }
      if (startNow) await api(`/runs/${r.slug}/start`, { method: "POST", json: {} });
      toast(files.length ? `Đã tạo phiên với ${files.length} bài báo nền` : "Đã tạo phiên"); RUNS_CACHE = []; location.hash = "#/run/" + r.slug;
    } finally { $("#create") && ($("#create").disabled = false); } };
}

// ---------- run detail ----------
const TABS = [["overview", "Tổng quan", "layout-dashboard"], ["log", "Agent đang làm", "bot"], ["files", "Tệp & bản thảo", "folder-open"], ["review", "Phản biện & bàn giao", "scale"],
  ["comments", "Góp ý", "message-square"], ["history", "Lịch sử", "history"], ["config", "Cấu hình", "settings-2"]];
function pipeline(r) {
  const gates = r.config?.gates || {};
  return `<ol class="pipe" aria-label="Tiến trình 10 bước">${r.stages.map(s => { const st = stageState(r, s), inf = r.stage_info?.[s], g = r.gates_map?.[s];
    const icon = st === "done" ? "check" : st === "gate" ? "hand" : st === "failed" ? "x" : STAGE[s][1];
    const meta = st === "running" ? "đang chạy…" : st === "gate" ? "chờ bạn" : inf ? `${money(inf.cost)} · ${dur(inf.seconds)}` : "";
    const sr = { done: "đã xong", running: "đang chạy", gate: "chờ duyệt", failed: "lỗi", next: "bước kế tiếp", todo: "chưa chạy" }[st];
    return `<li class="${st}" title="${esc(STAGE[s][2])} · bấm để xem lịch sử bước này">${g && gates[g] ? `<span class="gmark" title="Có cổng duyệt sau bước này">${ic("hand")}</span>` : ""}
      <a class="pstep" href="#/run/${esc(r.slug)}/stage/${s}"><span class="node">${ic(icon)}</span><div><span class="lbl">${STAGE[s][0]}<span class="sr"> (${sr})</span></span><span class="meta">${meta}</span></div></a></li>`; }).join("")}</ol>
    <div class="legend"><span><i style="background:var(--ok)"></i>Xong</span><span><i style="background:var(--run)"></i>Đang chạy</span><span><i style="background:var(--wait)"></i>Chờ bạn duyệt</span>
      <span><i style="border:2px dashed var(--primary)"></i>Bước kế tiếp</span><span>${ic("hand", "sm")} Có cổng duyệt</span><span class="muted">Bấm vào một bước để xem lịch sử và lưu trình của bước đó</span></div>`;
}
const nowStage = r => r.stages.find(s => ["running", "gate", "failed"].includes(stageState(r, s))) || r.stages.find(s => !r.done.includes(s));
const gateLeft = r => { if ((r.always_wait || []).includes(r.gate?.gate)) return null; const h = +(r.config?.gate_timeout_hours ?? 12); return h ? toMs(r.gate.since) + h * 3600e3 - Date.now() : null; };
function heroHtml(r, slug, tab) {
  const live = isLive(r), [st, lb] = runStatus(r), full = tab === "overview", allDone = r.done.length === r.stages.length, cur = nowStage(r);
  let actions;
  if (r.gate) { const left = gateLeft(r); actions = `<span class="chip">${ic("timer", "sm")} ${left == null ? "Chờ bạn, không tự đi tiếp" : left > 0 ? `Tự đi tiếp sau ${dur(left / 1000)}` : "Quá hạn, sẽ tự đi tiếp"}</span>`; }
  else if (live) actions = `<button class="btn danger" id="stop">${ic("square")} Dừng</button>`;
  else if (allDone) actions = `<a class="btn" href="#/run/${esc(slug)}/review">${ic("mail-open")} Đọc thư biên tập</a><button class="btn ghost" id="rerun">${ic("rotate-ccw")} Chạy lại…</button>`;
  else actions = `<button class="btn" id="go">${ic("play")} ${r.done.length ? "Tiếp tục" : "Bắt đầu"}</button><button class="btn ghost" id="rerun">${ic("rotate-ccw")} Chạy lại từ…</button>`;
  return `<div class="crumb"><a href="#/runs">Phiên nghiên cứu</a>${ic("chevron-right", "sm")}<span class="mono">${esc(slug)}</span></div>
    <div class="phead" style="margin-bottom:${full ? "1.2rem" : ".6rem"}"><div><h1>${esc(r.idea)}</h1>
      <p class="sub">${pill(st, lb)}<span>${ic("newspaper", "sm")}${esc(r.journal)}</span><span>${ic("tag", "sm")}${esc(DOMAIN_VI[r.domain] || r.domain)} · ${esc(TYPE_VI[r.config?.article_type] || r.config?.article_type || "")}</span>
        <span>${ic("wallet", "sm")}${money(r.cost)}</span></p></div>
      <div class="actions">${actions}<a class="btn ghost icon" href="/api/runs/${esc(slug)}/export" title="Tải toàn bộ phiên (zip)" aria-label="Tải toàn bộ phiên">${ic("download")}</a></div></div>
    ${full ? `<div class="pipe-full">${pipeline(r)}</div>` : ""}
    <div class="pipe-compact ${full ? "only-m" : ""}">${mini(r)}<span class="small"><b>${r.done.length}/10 bước</b>${cur && !allDone ? ` · ${{ running: "Đang chạy", gate: "Chờ bạn duyệt sau", failed: "Lỗi ở" }[stageState(r, cur)] || "Tiếp theo"}: <b>${sv(cur)}</b>` : allDone ? " · Hoàn tất" : ""}</span></div>`;
}
const pct = v => `${Math.round(num(v) * 100)}%`;
const VERDICT = { go: ["Nên làm", "ok"], pivot: ["Nên làm nhưng đổi hướng", "wait"], no_go: ["Chưa đáng làm", "bad"] };
function hypothesesHtml(h, pick) {
  if (!h?.hypotheses?.length) return "";
  const best = Math.max(...h.hypotheses.map(x => num(x.overall)), 0.0001), v = VERDICT[h.verdict];
  return `<div class="hyp">${v ? `<p class="hyp-verdict ${v[1]}">${ic(h.verdict === "no_go" ? "octagon-x" : h.verdict === "pivot" ? "shuffle" : "circle-check", "sm")} <b>${v[0]}.</b> ${esc(h.reason)}</p>` : ""}
    ${h.base_papers?.length ? `<p class="muted small">Dựa trên: ${h.base_papers.map(b => `<span class="chip" title="${esc(b.source)}">${esc(b.id)} · ${esc(b.title.slice(0, 60))}</span>`).join(" ")}</p>` : ""}
    <div class="hyp-grid">${h.hypotheses.map(x => `<label class="hyp-card ${x.id === h.recommended ? "rec" : ""}">
      ${pick ? `<input type="radio" name="hyp" value="${esc(x.id)}" ${x.id === h.recommended ? "checked" : ""}>` : ""}
      <div class="hyp-head"><b>${esc(x.id)} · ${esc(x.title)}</b>${x.id === h.recommended ? `<span class="pill done"><span class="dot"></span>Agent đề xuất</span>` : ""}</div>
      <p>${esc(x.statement)}</p>
      <div class="hyp-nums"><span><small>Làm thành công</small><b>${pct(x.p_success)}</b></span><span><small>Được accept nếu thành công</small><b>${pct(x.p_accept_if_success)}</b></span>
        <span><small>Tổng</small><b>${pct(x.overall)}</b></span><span><small>Công sức</small><b>${num(x.effort_weeks) ? num(x.effort_weeks) + " tuần" : "—"}</b></span></div>
      <div class="bar" aria-hidden="true"><i style="width:${Math.round(num(x.overall) / best * 100)}%"></i></div>
      <dl class="kv small"><dt>Cải tiến</dt><dd>${esc(x.improvement)}${x.grounded_in.length ? ` <span class="muted">(${x.grounded_in.map(esc).join(", ")})</span>` : ""}</dd>
        <dt>Tính mới</dt><dd>${esc(x.novelty)}</dd><dt>Khả thi</dt><dd>${esc(x.feasibility)}</dd>
        ${x.risks.length ? `<dt>Rủi ro</dt><dd>${x.risks.map(esc).join("; ")}</dd>` : ""}<dt>Thử nhanh</dt><dd>${esc(x.minimal_experiment)}</dd></dl></label>`).join("")}</div>
    <p class="muted small">Xác suất do agent ước lượng từ tỉ lệ nhận bài của tạp chí, độ mới so với bài nền và độ mạnh của bằng chứng. Hãy coi đây là căn cứ để quyết định, không phải cam kết.</p></div>`;
}
function gateHtml(r, slug, compact) {
  if (!r.gate) return "";
  const [t, d, fs] = GATE[r.gate.gate] || [r.gate.gate, "", []];
  if (compact) return `<section class="banner gate slim" role="region" aria-label="Cổng duyệt"><span class="bic">${ic("hand")}</span><div><b>Agent đang chờ bạn duyệt: ${esc(t)}.</b> <span class="muted">Đọc tệp ở đây, rồi duyệt.</span></div>
    <div class="actions">${r.gate.gate === "after_scope" ? `<a class="btn sm" href="#/run/${esc(slug)}">${ic("target", "sm")} Xem và chọn giả thuyết</a>`
      : `<button class="btn sm" data-g="approve">${ic("check", "sm")} Duyệt, đi tiếp</button><a class="btn sm ghost" href="#/run/${esc(slug)}">Góp ý / làm lại…</a>`}</div></section>`;
  const rv = r.gate.gate === "after_results" && r.reviews?.length ? [`reviews/round_${r.reviews.at(-1).round}.md`] : [];
  const reqs = r.gate.gate === "after_literature" ? r.requests : [];
  const canRedo = r.gate.stage !== "07_revise";
  return `<section class="banner gate" aria-live="polite"><span class="bic">${ic("hand", "lg")}</span><div>
    <h2>Agent đang chờ bạn duyệt: ${esc(t)}</h2><p>${esc(d)}</p>${r.gate.gate === "after_scope" ? hypothesesHtml(r.hypotheses, true) : ""}
    <ol class="steps gsteps"><li>Đọc kết quả: <span class="linkrow">${[...rv, ...fs].map(p => fileLink(slug, p)).join("")}</span></li>
      ${reqs.length ? `<li>Nếu có thể, tải PDF các bài agent yêu cầu (${reqs.map(p => fileLink(slug, p, "danh sách")).join("")}) ở mục <a href="#/run/${esc(slug)}/files">Tệp</a>.</li>` : ""}
      <li>Chọn cách đi tiếp.</li></ol>
    <label>Góp ý cho agent ${canRedo ? "(bắt buộc nếu làm lại)" : "(tuỳ chọn)"}<textarea id="gnote" rows="2" placeholder="Ví dụ: thu hẹp phạm vi, thêm một baseline, đổi tạp chí dự phòng…"></textarea></label>
    <div class="actions"><button class="btn" data-g="approve">${ic("check")} ${r.gate.gate === "after_scope" && r.hypotheses?.hypotheses?.length ? "Làm giả thuyết đã chọn" : "Duyệt, đi tiếp"}</button>
      ${canRedo ? `<button class="btn ghost" data-g="redo">${ic("rotate-ccw")} Làm lại bước ${esc(sv(r.gate.stage))} theo góp ý</button>` : ""}
      <button class="btn quiet" data-g="reject">${ic("pause")} ${r.gate.gate === "after_scope" ? "Chưa làm, dừng tại đây" : "Tạm dừng tại đây"}</button></div>
    <p class="muted small" style="margin:.6rem 0 0">Góp ý đi kèm “Duyệt” được chuyển cho bước tiếp theo. ${gateLeft(r) == null ? "Phiên này luôn chờ bạn duyệt." : "Nếu không ai duyệt, agent tự đi tiếp sau thời gian đã đặt."}</p></div></section>`;
}
function bindHead(root, slug, r) {
  const go = $("#go", root), stop = $("#stop", root), rerun = $("#rerun", root);
  go && (go.onclick = async () => { go.disabled = true; try { await api(`/runs/${slug}/start`, { method: "POST", json: {} }); } finally { go.disabled = false; } toast("Đã xếp lượt chạy"); route(); });
  stop && (stop.onclick = async () => { if (!confirm("Dừng phiên đang chạy? Bước đang làm dở sẽ phải chạy lại.")) return; await api(`/runs/${slug}/stop`, { method: "POST" }); toast("Đã dừng"); route(); });
  rerun && (rerun.onclick = () => dialog(`<h2>${ic("rotate-ccw")} Chạy lại từ một bước</h2>
    <p class="muted">Agent chạy lại bước được chọn và mọi bước sau đó. Kết quả cũ vẫn còn trong Lịch sử.</p>
    <label>Bắt đầu lại từ<select name="from">${r.stages.filter(s => s !== "07_revise").map(s => `<option value="${s}">${sv(s)}</option>`).join("")}</select></label>
    <p class="banner req small" style="margin:0 0 1rem;padding:.7rem .9rem">${ic("wallet", "sm")} Chi phí ước tính tương đương lần chạy trước của các bước đó (cả phiên vừa rồi: ${money(r.cost)}).</p>
    <div class="dfoot"><button type="button" class="btn ghost" data-close>Huỷ</button><button class="btn">${ic("play", "sm")} Chạy lại</button></div>`,
    async f => { await api(`/runs/${slug}/start`, { method: "POST", json: { from: f.get("from"), force: true } }); toast("Đã xếp lượt chạy lại từ " + sv(f.get("from"))); route(); }));
  $$("[data-g]", root).forEach(b => b.onclick = async () => {
    const note = ($("#gnote")?.value || "").trim(), g = b.dataset.g;
    if (g === "reject" && !confirm("Tạm dừng phiên tại cổng này? Bấm “Tiếp tục” bất cứ lúc nào để chạy tiếp.")) return;
    if (g === "redo" && !note) { $("#gnote").focus(); return toast("Viết góp ý để agent biết cần làm lại thế nào", true); }
    b.disabled = true;
    const hyp = g === "approve" ? $("input[name=hyp]:checked", root)?.value : undefined;
    try { await api(`/runs/${slug}/gate`, { method: "POST", json: { action: g === "approve" && note ? "guide" : g, note, hypothesis: hyp } }); }
    finally { b.disabled = false; }
    toast({ approve: "Đã duyệt, agent đi tiếp", redo: "Agent sẽ làm lại bước này theo góp ý", reject: "Đã tạm dừng phiên" }[g]); RUNS_CACHE = []; route(); });
}
async function vRun(app, slug, tab = "overview", arg) {
  const r = await api(`/runs/${slug}`);
  const nRounds = r.reviews?.length || 0;
  app.innerHTML = `<div class="wrap"><section class="hero" id="hero">${heroHtml(r, slug, tab)}</section>
    <div id="gatebar">${tab === "overview" ? "" : gateHtml(r, slug, true)}</div>
    <nav class="tabs" aria-label="Các mục của phiên">${TABS.map(([k, v, i]) => `<a href="#/run/${esc(slug)}/${k}" class="${k === tab ? "on" : ""}" ${k === tab ? 'aria-current="page"' : ""}>${ic(i, "sm")}${v}
      ${k === "review" && nRounds ? `<span class="count">${nRounds}</span>` : ""}</a>`).join("")}</nav><div id="tab"></div></div>`;
  bindHead(app, slug, r);
  const on = $(".tabs a.on"); if (on) on.parentElement.scrollLeft = on.offsetLeft - on.parentElement.clientWidth / 2; // horizontal only: never move the page
  const el = $("#tab");
  await ({ overview: tOverview, log: tLog, stage: tStage, files: tFiles, review: tReview, comments: tComments, history: tHistory, config: tConfig }[tab] || tOverview)(el, slug, r, arg);
  let last = heroHtml(r, slug, tab) + gateHtml(r, slug, true);
  if (tab !== "overview") every(async () => { // keep header, gate bar and nav badge in sync on every tab
    const n = await api(`/runs/${slug}`), h = heroHtml(n, slug, tab), g = gateHtml(n, slug, true);
    if (h + g !== last) { last = h + g; $("#hero").innerHTML = h; $("#gatebar").innerHTML = g; bindHead(app, slug, n); } // only on change: keeps focus and in-flight buttons
    const c = RUNS_CACHE.find(x => x.slug === slug); if (c && !!c.gate !== !!n.gate) { c.gate = n.gate; nav(); } }, isLive(r) ? 4000 : 15000);
}
const fileLink = (slug, p, label) => `<a href="#/run/${esc(slug)}/files/${encodeURIComponent(p)}">${ic(/\.pdf$/.test(p) ? "file-type" : "file-text", "sm")}${esc(label || p)}</a>`;

function tOverview(el, slug, r) {
  let html = gateHtml(r, slug, false);
  const uploaded = r.events.some(e => e.type === "upload");
  if (r.requests.length && !r.gate && !uploaded && !r.done.includes("02_journal")) html += `<section class="banner req"><span class="bic">${ic("file-up", "lg")}</span><div><h2>Agent cần bạn tải tài liệu</h2>
    <p>Một số bài quan trọng không có bản mở. Xem danh sách, tải PDF ở mục Tệp, rồi chạy lại từ “Tài liệu”.</p><div class="linkrow">${r.requests.map(p => fileLink(slug, p)).join("")}</div></div></section>`;
  if (r.job?.status === "failed") html += `<section class="banner bad"><span class="bic">${ic("circle-alert", "lg")}</span><div><h2>Lần chạy gần nhất bị lỗi</h2>
    <p>Xem nhật ký để biết lý do, sửa cấu hình hoặc tệp nếu cần, rồi bấm Tiếp tục.</p><a class="btn sm ghost" href="#/run/${esc(slug)}/log">${ic("bot", "sm")} Mở nhật ký</a></div></section>`;
  if (r.done.length === r.stages.length) html += `<section class="banner ok"><span class="bic">${ic("party-popper", "lg")}</span><div><h2>Bài đã sẵn sàng để bạn đọc</h2>
    <ol class="steps gsteps"><li>Đọc thư biên tập: kết luận, rủi ro phản biện và việc bạn cần làm. ${fileLink(slug, "submission/editor_letter.md", "Mở thư")}</li>
      <li>Đọc bản thảo ${fileLink(slug, "paper/main.pdf", "PDF")}, góp ý trực tiếp lên đoạn văn nếu cần.</li>
      <li>Điền tác giả, cơ quan, CRediT theo ${fileLink(slug, "submission/checklist.md", "checklist")}.</li>
      <li>Tải gói nộp bằng nút ${ic("download", "sm")} ở trên và nộp trên trang tạp chí.</li></ol></div></section>`;

  if (r.hypotheses?.hypotheses?.length && r.gate?.gate !== "after_scope") html += `<details class="card" style="margin-bottom:1rem"><summary style="cursor:pointer"><h2 style="display:inline-flex;margin:0">${ic("target")} Giả thuyết và khả năng được accept</h2></summary>${hypothesesHtml(r.hypotheses, false)}</details>`;
  const secs = Object.values(r.stage_info || {}).reduce((a, i) => a + i.seconds, 0), rv = r.reviews?.at(-1), pct = r.done.length / 10;
  const C = 2 * Math.PI * 26;
  html += `<div class="kpis k4">
    <div class="kpi"><span class="ring"><svg width="64" height="64" viewBox="0 0 64 64" aria-hidden="true"><circle cx="32" cy="32" r="26" fill="none" stroke="var(--border)" stroke-width="7"/>
      ${pct ? `<circle cx="32" cy="32" r="26" fill="none" stroke="var(--ok)" stroke-width="7" stroke-linecap="round" stroke-dasharray="${C * pct} ${C}"/>` : ""}</svg><b>${r.done.length}/10</b></span>
      <span><b>${Math.round(pct * 100)}%</b><small>Tiến độ</small></span></div>
    <div class="kpi"><span class="kic o">${ic("wallet")}</span><span><b>${money(r.cost)}</b><small>Chi phí (giá API tương đương)</small></span></div>
    <div class="kpi"><span class="kic">${ic("star")}</span><span><b>${rv ? num(rv.score) + "<small>/10</small>" : "—"}</b><small>${rv ? `Phản biện vòng ${num(rv.round)} · ${esc(STATUS_VI[rv.decision] || rv.decision)}` : "Chưa phản biện"}</small></span></div>
    <div class="kpi"><span class="kic b">${ic("timer")}</span><span><b>${secs ? dur(secs) : "—"}</b><small>Thời gian agent làm việc</small></span></div></div>`;

  const thr = Number.isFinite(+r.config?.review?.accept_score) ? +r.config.review.accept_score : 7.5;
  const inf = r.stage_info || {}, maxc = Math.max(0.01, ...Object.values(inf).map(i => i.cost));
  html += `<div class="cols"><section class="card"><div class="card-head"><h2>${ic("chart-bar")} Chi phí theo bước</h2><span class="muted small">trần ${money(r.config?.max_budget_usd)} mỗi bước</span></div>
      ${Object.keys(inf).length ? `<div class="bars">${r.stages.filter(s => inf[s]).map(s => `<div class="bar"><span>${sv(s)}${inf[s].runs > 1 ? ` <span class="muted">×${inf[s].runs}</span>` : ""}</span>
        <span class="track"><span class="fill ${["06_review", "07_revise"].includes(s) ? "o" : ""}" style="width:${(inf[s].cost / maxc) * 100}%;display:block"></span></span><span class="v">${money(inf[s].cost)}</span></div>`).join("")}</div>`
        : `<p class="muted">Chưa có bước nào chạy xong.</p>`}</section>
    <section class="card"><div class="card-head"><h2>${ic("chart-line")} Điểm phản biện qua các vòng</h2><span class="muted small">ngưỡng chấp nhận ${thr}</span></div>
      ${scoreChart(r.reviews || [], thr)}</section></div>
    <section class="card" style="margin-top:1rem"><div class="card-head"><h2>${ic("activity")} Hoạt động gần đây</h2>${isLive(r) ? `<span class="live">Đang cập nhật</span>` : ""}</div>
      ${(() => { const ev = r.events.filter((e, i, a) => !(e.type === "run_created" && a.findIndex(x => x.type === "run_created") !== i)).reverse();
        return `<ol class="tl">${ev.slice(0, 12).map(evRow).join("")}</ol>${ev.length > 12 ? `<details class="more"><summary>Xem thêm ${ev.length - 12} hoạt động cũ hơn</summary><ol class="tl">${ev.slice(12).map(evRow).join("")}</ol></details>` : ""}`; })()}</section>`;
  el.innerHTML = html;
  bindHead(el, slug, r);
  autoRefresh(route, isLive(r) ? 4000 : 20000);
}
function scoreChart(rs, thr) {
  if (!rs.length) return `<p class="muted">Điểm xuất hiện sau bước Phản biện. Mỗi vòng gồm 6 phản biện ẩn danh và một biên tập viên tổng hợp.</p>`;
  const W = 420, H = 190, P = 32, X0 = P + 28, X1 = W - 28, n = Math.max(rs.length, 3), x = i => X0 + (i * (X1 - X0)) / (n - 1), y = v => H - P - (v / 10) * (H - 2 * P);
  return `<div class="chart"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Điểm: ${rs.map(v => `vòng ${v.round} ${v.score}`).join(", ")}">
    <g class="grid">${[0, 2.5, 5, 7.5, 10].map(v => `<line x1="${P}" x2="${W - P}" y1="${y(v)}" y2="${y(v)}"/><text x="${P - 8}" y="${y(v) + 4}" text-anchor="end">${v}</text>`).join("")}</g>
    <line class="thr" x1="${P}" x2="${W - P}" y1="${y(thr)}" y2="${y(thr)}"/>
    <polyline class="line" points="${rs.map((v, i) => `${x(i)},${y(v.score)}`).join(" ")}"/>
    ${rs.map((v, i) => `<circle class="pt" cx="${x(i)}" cy="${y(v.score)}" r="6"/><text class="val" x="${x(i)}" y="${y(v.score) + (v.score < thr ? 22 : -12)}" text-anchor="middle">${v.score}</text>
      <text x="${x(i)}" y="${H - 8}" text-anchor="${i === 0 && n > 1 ? "start" : i === n - 1 ? "end" : "middle"}" dx="${i === 0 ? -12 : i === n - 1 ? 12 : 0}">Vòng ${v.round} · ${esc(STATUS_VI[v.decision] || v.decision)}</text>`).join("")}</svg></div>`;
}
function evRow(e) {
  const who = (e.actor || "").replace(/^user:/, "").replace(/^agent:.*/, "agent");
  const S = e.actor?.startsWith("agent:") ? sv(e.actor.slice(6)) : "";
  const m = {
    run_created: ["sparkles", "", "Tạo phiên"], stage_start: ["play", "run", `Bắt đầu bước <b>${S}</b>`],
    stage_end: e.error ? ["x", "bad", `Bước <b>${S}</b> bị lỗi`] : ["check", "ok", `Xong bước <b>${S}</b><small>${money(e.cost)} · ${dur(e.seconds)}</small>`],
    gate_opened: ["hand", "wait", `Mở cổng duyệt: <b>${esc(GATE[e.gate]?.[0] || e.gate)}</b>`],
    gate_answered: ["user-check", "user", `${esc(who)} ${{ approve: "đồng ý", guide: "hướng dẫn", reject: "dừng phiên" }[e.action] || esc(e.action)} ở cổng <b>${esc(GATE[e.gate]?.[0] || e.gate)}</b>${e.note ? `<small>“${esc(e.note)}”</small>` : ""}`],
    gate_timeout: ["timer", "wait", `Hết giờ chờ ở cổng ${esc(GATE[e.gate]?.[0] || e.gate)}, tự đi tiếp`],
    user_edit: ["pencil", "user", `${esc(who)} sửa <code>${esc(e.path)}</code>`], upload: ["upload", "user", `${esc(who)} tải lên ${(e.files || []).length} tệp`],
    comment: ["message-square", "user", `${esc(who)} góp ý${e.path ? ` cho <code>${esc(e.path)}</code>` : ""}`], config_change: ["settings-2", "user", `${esc(who)} sửa cấu hình`],
  }[e.type] || ["dot", "", esc(e.type)];
  return `<li><span class="tic ${m[1]}">${ic(m[0], "sm")}</span><span class="what">${m[2]}</span><span class="when" title="${esc(e.ts)}">${ago(e.ts)}</span></li>`;
}

const TOOL = { Read: ["file-text", "Đọc"], Write: ["file-plus", "Ghi"], Edit: ["file-pen", "Sửa"], Bash: ["terminal", "Chạy lệnh"], WebFetch: ["globe", "Mở trang"], WebSearch: ["search", "Tìm trên web"],
  Agent: ["users", "Giao việc"], Skill: ["sparkles", "Dùng kỹ năng"], Grep: ["search", "Tìm trong tệp"], Glob: ["folder-search", "Liệt kê tệp"] };
const toolArg = raw => { try { const o = JSON.parse(raw); return o.file_path || o.command || o.url || o.query || o.description || o.pattern || o.skill || raw; } catch { return raw; } };
const fmtTs = t => { const d = new Date(toMs(t)); return isFinite(d) ? d.toLocaleString(LOCALE, { dateStyle: "short", timeStyle: "short" }) : ""; };
function feedItem(e) {
  if (e.t === "say") return `<div class="say"><span class="av">${ic("bot", "sm")}</span><div class="bub">${md(e.v)}</div></div>`;
  if (e.t === "tool") { const [n, ...rest] = e.v.split(": "), [i, l] = TOOL[n] || ["wrench", n]; return `<div class="tool">${ic(i, "sm")}<b>${esc(l)}</b><span title="${esc(rest.join(": "))}">${esc(toolArg(rest.join(": ")))}</span></div>`; }
  if (e.t === "attempt") return `<div class="attempt"><span>${ic("rotate-cw", "sm")} Lần chạy lúc ${esc(fmtTs(e.v))}</span></div>`;
  return `<div class="result">${ic("circle-check")}<span>${esc(e.v)}</span></div>`;
}
async function tLog(el, slug, r) {
  const ran = r.stages.filter(s => r.stage_info?.[s] || r.current === s);
  let stage = sessionStorage.getItem("logStage:" + slug);
  if (!ran.includes(stage)) stage = r.current || ran.at(-1);
  const draw = async () => {
    const l = stage ? await api(`/runs/${slug}/log?stage=${stage}`) : { events: [], pipeline: "" };
    const live = isLive(r) && stage === r.current;
    const feed = $("#feed"), stick = !feed || feed.scrollHeight - feed.scrollTop - feed.clientHeight < 60;
    el.innerHTML = `<div class="filter" role="group" aria-label="Chọn bước">${ran.map(s => `<button data-s="${s}" class="${s === stage ? "on" : ""}" aria-pressed="${s === stage}">${sv(s)}</button>`).join("") || '<span class="muted">Chưa có bước nào chạy.</span>'}
      ${live ? `<span class="live" style="margin-left:auto">Đang chạy, tự cập nhật</span>` : ""}</div>
      <p class="muted small" style="margin:-.4rem 0 .8rem">Xem đầy đủ lịch sử từng lần chạy ở <a href="#/run/${esc(slug)}/stage/${stage || ""}">trang chi tiết bước ${stage ? sv(stage) : ""}</a>.</p>
      <section class="card"><div class="feed" id="feed">${l.events.map(feedItem).join("") || '<p class="muted">Chưa có nhật ký cho bước này.</p>'}
        ${live ? `<div class="say"><span class="av">${ic("bot", "sm")}</span><div class="bub"><span class="spin" aria-label="Agent đang làm việc"></span></div></div>` : ""}</div></section>
      <details class="card more" style="margin-top:1rem"><summary style="cursor:pointer;font-weight:700;color:var(--fg)">Nhật ký pipeline (kỹ thuật)</summary><pre class="code" style="margin-top:.8rem">${esc(l.pipeline || "—")}</pre></details>`;
    const f = $("#feed"); if (stick) f.scrollTop = f.scrollHeight;
    $$("[data-s]", el).forEach(b => b.onclick = () => { stage = b.dataset.s; sessionStorage.setItem("logStage:" + slug, stage); draw(); });
  };
  await draw();
  autoRefresh(async () => { r = await api(`/runs/${slug}`); if (r.current && !ran.includes(r.current)) { ran.push(r.current); stage = r.current; } draw(); }, isLive(r) ? 3000 : 30000);
}

const FOLDER = { "": ["Tổng quan phiên", "file-text"], lit: ["Tài liệu", "library"], journal: ["Tạp chí", "newspaper"], plan: ["Kế hoạch", "clipboard-list"], exp: ["Thí nghiệm", "flask-conical"],
  paper: ["Bản thảo", "pen-line"], reviews: ["Phản biện", "users"], submission: ["Hồ sơ nộp", "send"], comments: ["Góp ý", "message-square"], knowledge: ["Skill riêng của phiên", "book-open"],
  logs: ["Kỹ thuật (nhật ký, trạng thái)", "terminal"] };
const fileIcon = f => /\.pdf$/.test(f) ? "file-type" : /\.(png|jpe?g|svg)$/.test(f) ? "image" : /\.(json|ya?ml|bib|tex|py|sh|jsonl)$/.test(f) ? "file-code" : /\.md$/.test(f) ? "file-text" : "file";
async function tFiles(el, slug, r, want) {
  const files = await api(`/runs/${slug}/tree`);
  const tech = f => /^(logs|hitl)\//.test(f) || (!f.includes("/") && !/\.md$/.test(f));
  const folderOf = want ? (tech(want) ? "logs" : want.includes("/") ? want.split("/")[0] : "") : "";
  const groups = {}; files.filter(f => !/(^|\/)\./.test(f) && (tech(f) || !/\.(aux|log|out)$/.test(f))).forEach(f => { const top = tech(f) ? "logs" : f.includes("/") ? f.split("/")[0] : ""; (groups[top] ||= []).push(f); });
  const order = Object.keys(FOLDER).filter(k => groups[k]).concat(Object.keys(groups).filter(k => !FOLDER[k]));

  el.innerHTML = `<div class="split"><aside class="card tree" aria-label="Danh sách tệp">
      <button class="btn ghost sm" id="up" style="width:100%;margin-bottom:.5rem">${ic("upload", "sm")} Tải tệp lên</button>
      ${order.map(k => `<details ${k !== "logs" || folderOf === "logs" ? "open" : ""}><summary>${ic((FOLDER[k] || ["", "folder"])[1], "sm")}${esc((FOLDER[k] || [k])[0])}<span class="n">${groups[k].length}</span></summary>
        ${groups[k].map(f => `<a href="#/run/${esc(slug)}/files/${encodeURIComponent(f)}" data-f="${esc(f)}">${ic(fileIcon(f), "sm")}<span>${esc(f.startsWith(k + "/") ? f.slice(k.length + 1) : f)}</span></a>`).join("")}</details>`).join("")}</aside>
    <section class="card viewer" id="v"><div class="empty"><span class="big">${ic("mouse-pointer-click", "lg")}</span><h2>Chọn một tệp để xem</h2><p>Bôi đen đoạn văn để góp ý cho agent, hoặc bấm Sửa để chỉnh trực tiếp.</p></div></section></div>`;
  const open = async f => {
    $$(".tree a", el).forEach(a => a.classList.toggle("on", a.dataset.f === f));
    const url = `/api/runs/${slug}/file?path=${encodeURIComponent(f)}`, v = $("#v");
    const bar = extra => `<div class="vhead"><span class="path">${ic(fileIcon(f), "sm")}${esc(f)}</span><div class="actions">${extra}<a class="btn ghost sm" href="${url}&raw=1" download>${ic("download", "sm")} Tải về</a></div></div>`;
    if (/\.pdf$/i.test(f)) return (v.innerHTML = bar("") + `<iframe src="${url}&raw=1" title="${esc(f)}"></iframe>`);
    if (/\.(png|jpe?g|svg)$/i.test(f)) return (v.innerHTML = bar("") + `<img src="${url}&raw=1" alt="${esc(f)}">`);
    if (/\.(docx|zip|bundle)$/i.test(f)) return (v.innerHTML = bar("") + `<p class="muted">Tệp nhị phân, tải về để xem.</p>`);
    let text = await api(`/runs/${slug}/file?path=${encodeURIComponent(f)}`);
    if (/\.json$/.test(f)) try { text = JSON.stringify(JSON.parse(text), null, 2); } catch {}
    const big = text.length >= 2e6; // server sends at most 2M chars: saving would truncate the file
    v.innerHTML = bar(`<button class="btn ghost sm" id="cm">${ic("message-square-plus", "sm")} Góp ý</button>${big ? "" : `<button class="btn ghost sm" id="ed">${ic("pencil", "sm")} Sửa</button>`}
      ${/^knowledge\/.*\.md$/.test(f) ? `<button class="btn ghost sm" id="pr">${ic("share", "sm")} Đề xuất vào kho chung</button>` : ""}`)
      + `<div id="body" style="position:relative">${/\.md$/.test(f) ? `<div class="prose">${md(text)}</div>` : `<pre class="code">${esc(text)}</pre>`}</div>`;
    if (!big) $("#ed").onclick = () => { $("#body").innerHTML = `<textarea class="code" id="ta" aria-label="Nội dung tệp" spellcheck="false">${esc(text)}</textarea>
      <div class="actions" style="margin-top:.6rem"><button class="btn" id="sv">${ic("save", "sm")} Lưu</button><button class="btn ghost" id="cx">Huỷ</button>
      <span class="muted small">Lưu sẽ tạo một mốc lịch sử; agent coi bản sửa của bạn là sở thích để học theo.</span></div>`;
      $("#ta").focus(); $("#cx").onclick = () => open(f);
      $("#sv").onclick = async () => { await api(`/runs/${slug}/file?path=${encodeURIComponent(f)}`, { method: "PUT", body: $("#ta").value }); toast("Đã lưu"); open(f); }; };
    $("#cm").onclick = () => commentDialog(slug, f, String(getSelection()).trim());
    if ($("#pr")) $("#pr").onclick = async () => { await api("/kb/promote", { method: "POST", json: { slug, path: f } }); toast("Đã gửi admin duyệt"); };
    $("#body").onmouseup = () => setTimeout(() => { // floating "comment on selection" button
      $(".selbtn")?.remove(); const sel = getSelection(), q = String(sel).trim(); if (!q || !sel.rangeCount || !$("#body")?.contains(sel.getRangeAt(0).commonAncestorContainer) || $("#ta")) return;
      const rc = sel.getRangeAt(0).getBoundingClientRect(), base = $("#body").getBoundingClientRect();
      const b = document.createElement("button"); b.className = "btn sm selbtn"; b.innerHTML = ic("message-square-plus", "sm") + " Góp ý đoạn này";
      b.style.top = (rc.bottom - base.top + 6) + "px"; b.style.left = Math.min(Math.max(0, rc.left - base.left), base.width - 170) + "px";
      b.onmousedown = e => e.preventDefault(); b.onclick = () => { b.remove(); commentDialog(slug, f, q); }; $("#body").append(b);
    }, 10);
  };
  $("#up").onclick = () => { dialog(`<h2>${ic("upload")} Tải tệp lên</h2>
    <label>Loại tệp<select name="where"><option value="lit/uploads">PDF bài báo (tài liệu tham khảo)</option><option value="journal/accepted">Bài đã đăng của tạp chí (mẫu văn phong)</option>
      <option value="exp/data">Dữ liệu thí nghiệm</option><option value="knowledge">Skill riêng cho phiên này (.md)</option></select></label>
    <div class="drop" id="drop">${ic("cloud-upload", "lg")}<div>Kéo thả tệp vào đây hoặc chọn tệp</div><input type="file" name="files" multiple required aria-label="Chọn tệp"></div>
    <p class="muted small">PDF, DOCX, MD, TXT, CSV, ZIP, BIB, TEX; tối đa 50 MB mỗi tệp.</p>
    <div class="dfoot"><button type="button" class="btn ghost" data-close>Huỷ</button><button class="btn">${ic("upload", "sm")} Tải lên</button></div>`,
    async fd => { const res = await api(`/runs/${slug}/upload`, { method: "POST", body: fd }); toast(`Đã tải lên ${res.saved.length} tệp`); tFiles(el, slug, r, res.saved[0]); });
    dropZone($("#drop")); };
  $$("[data-f]", el).forEach(a => a.onclick = e => { e.preventDefault(); history.replaceState(null, "", a.getAttribute("href")); open(a.dataset.f); });
  const first = want && files.includes(want) ? want : ["submission/editor_letter.md", "paper/main.pdf", "scope.md"].find(x => files.includes(x));
  if (first) open(first);
}
function dropZone(dz) {
  const inp = $("input[type=file]", dz);
  dz.addEventListener("dragover", e => { e.preventDefault(); dz.classList.add("over"); });
  dz.addEventListener("dragleave", () => dz.classList.remove("over"));
  dz.addEventListener("drop", e => { e.preventDefault(); dz.classList.remove("over"); inp.files = e.dataTransfer.files; dz.querySelector("div").textContent = [...inp.files].map(f => f.name).join(", "); });
  inp.addEventListener("change", () => { dz.querySelector("div").textContent = [...inp.files].map(f => f.name).join(", ") || "Kéo thả tệp vào đây hoặc chọn tệp"; });
}

async function tReview(el, slug) {
  const files = await api(`/runs/${slug}/tree`);
  const rounds = files.filter(f => /^reviews\/round_\d+\.json$/.test(f)).sort((a, b) => parseInt(a.match(/\d+/)) - parseInt(b.match(/\d+/)));
  const data = await Promise.all(rounds.map(f => api(`/runs/${slug}/file?path=${encodeURIComponent(f)}`).then(t => { try { return JSON.parse(t); } catch { return {}; } })
    .then(d => ({ score: num(d.score), decision: String(d.decision || ""), open_major: num(d.open_major), seats: d.seats && typeof d.seats === "object" ? Object.fromEntries(Object.entries(d.seats).map(([k, v]) => [k, num(v)])) : null }))));
  const docs = [["submission/editor_letter.md", "Thư biên tập (đọc đầu tiên)", "mail-open"], ...rounds.map((f, i) => [f.replace(".json", ".md"), `Phản biện vòng ${i + 1}`, "users"]).reverse(),
    ["paper/response_letter.md", "Thư trả lời phản biện", "reply"], ["submission/checklist.md", "Checklist nộp bài", "list-checks"], ["submission/cover_letter.md", "Thư gửi tạp chí", "mail"],
    ["submission/highlights.md", "Điểm nổi bật (highlights)", "highlighter"], ["submission/ai_disclosure.md", "Khai báo sử dụng AI", "shield-check"], ["paper/main.pdf", "Bản thảo PDF", "file-type"]].filter(([f]) => files.includes(f));
  if (!docs.length) return (el.innerHTML = `<div class="empty card"><span class="big">${ic("scale", "lg")}</span><h2>Chưa có phản biện</h2><p>Phản biện bắt đầu sau khi có bản thảo. Thư bàn giao xuất hiện sau bước Hồ sơ nộp.</p></div>`);
  el.innerHTML = `${data.length ? `<div class="rounds">${data.map((d, i) => `<button class="card round" data-f="${esc(rounds[i].replace(".json", ".md"))}" aria-label="Mở phản biện vòng ${i + 1}">
      <div class="card-head" style="margin-bottom:.4rem"><h2>Vòng ${i + 1}</h2>${pill(d.decision, STATUS_VI[d.decision])}</div>
      <div class="score">${esc(d.score)}<small>/10</small></div><div class="muted small">${d.open_major ? `${d.open_major} vấn đề lớn còn mở` : "Không còn vấn đề lớn"}</div>
      ${d.seats ? `<div class="seats">${Object.entries(d.seats).map(([k, v]) => `<div class="seat"><span>${esc(SEAT_VI[k] || k)}</span><span class="track" style="display:block;background:var(--surface-2);border-radius:4px;overflow:hidden"><span style="display:block;height:100%;width:${v * 10}%;background:${v < 7.5 ? "var(--accent)" : "var(--primary)"}"></span></span><span class="v">${v}</span></div>`).join("")}</div>` : ""}</button>`).join("")}</div>` : ""}
    <div class="split"><nav class="card doclist" aria-label="Tài liệu phản biện">${docs.map(([f, l, i]) => `<button data-d="${esc(f)}">${ic(i, "sm")}${esc(l)}</button>`).join("")}</nav>
    <section class="card viewer" id="rv"></section></div>`;
  const show = async f => {
    $$("[data-d]", el).forEach(b => b.classList.toggle("on", b.dataset.d === f)); $$(".round", el).forEach(b => b.classList.toggle("on", b.dataset.f === f));
    const url = `/api/runs/${slug}/file?path=${encodeURIComponent(f)}`;
    $("#rv").innerHTML = /\.pdf$/.test(f) ? `<iframe src="${url}&raw=1" title="Bản thảo"></iframe>`
      : `<div class="vhead"><span class="path">${esc(f)}</span><button class="btn ghost sm" id="cm">${ic("message-square-plus", "sm")} Góp ý</button></div><div class="prose">${md(await api(`/runs/${slug}/file?path=${encodeURIComponent(f)}`))}</div>`;
    $("#cm") && ($("#cm").onclick = () => commentDialog(slug, f, String(getSelection()).trim()));
  };
  $$("[data-d]", el).forEach(b => b.onclick = () => show(b.dataset.d)); $$(".round", el).forEach(b => b.onclick = () => show(b.dataset.f));
  show(docs[0][0]);
}

async function tComments(el, slug, r) {
  const cs = await api(`/runs/${slug}/comments`), finished = r && r.done.length === r.stages.length;
  const f = sessionStorage.getItem("cFilter") || "all";
  const shown = cs.filter(c => f === "all" || c.status === f);
  el.innerHTML = `<div class="cols side-r"><section class="card">
      <div class="filter" role="group" aria-label="Lọc góp ý">${[["all", "Tất cả"], ["open", "Đang mở"], ["applied", "Đã xử lý"], ["rejected", "Bỏ qua"]].map(([k, l]) =>
        `<button data-c="${k}" class="${f === k ? "on" : ""}" aria-pressed="${f === k}">${l} <span>${k === "all" ? cs.length : cs.filter(c => c.status === k).length}</span></button>`).join("")}</div>
      ${shown.map(c => `<article class="cmt"><span class="avatar">${esc((c.email || "?")[0].toUpperCase())}</span><div>
        <div class="head"><b>${esc(c.email)}</b>${pill(c.kind, COMMENT_KIND[c.kind])}${pill(c.status)}<span class="muted">${ago(c.ts)}${c.path ? ` · <a href="#/run/${esc(slug)}/files/${encodeURIComponent(c.path)}"><code>${esc(c.path)}</code></a>` : " · chung"}</span></div>
        ${c.quote ? `<blockquote>${esc(c.quote)}</blockquote>` : ""}<p>${esc(c.body)}</p>${c.reply ? `<p class="muted small">${ic("bot", "sm")} ${esc(c.reply)}</p>` : ""}
        ${c.status === "open" ? `<div class="actions" style="margin-top:.5rem"><button class="btn sm ghost" data-s="${c.id}" data-v="applied">${ic("check", "sm")} Đã xử lý</button><button class="btn sm quiet" data-s="${c.id}" data-v="rejected">Bỏ qua</button></div>` : ""}</div></article>`).join("")
        || `<div class="empty"><span class="big">${ic("message-square", "lg")}</span><h2>Chưa có góp ý</h2><p>Bôi đen đoạn văn trong mục Tệp để góp ý, hoặc viết góp ý chung.</p></div>`}</section>
    <aside class="card" aria-label="Góp ý chung"><h2>${ic("message-square-plus")} Góp ý chung</h2><p class="muted small">${finished ? "Phiên đã xong: góp ý đang mở sẽ được dùng khi bạn bấm “Chạy lại…” từ bước Phản biện hoặc Bản thảo." : "Góp ý đang mở được giao cho agent ở vòng chỉnh sửa kế tiếp, rồi tổng hợp thành kinh nghiệm ở bước cuối."}</p>
      <button class="btn" style="width:100%" id="new">${ic("plus", "sm")} Viết góp ý</button></aside></div>`;
  $$("[data-c]", el).forEach(b => b.onclick = () => { sessionStorage.setItem("cFilter", b.dataset.c); tComments(el, slug, r); });
  $("#new").onclick = () => commentDialog(slug, "", "", () => tComments(el, slug, r));
  $$("[data-s]", el).forEach(a => a.onclick = async () => { await api(`/runs/${slug}/comments/${a.dataset.s}`, { method: "PATCH", json: { status: a.dataset.v } }); tComments(el, slug, r); });
}

function diffHtml(t) {
  if (!t.trim()) return `<p class="muted" style="padding:0 1rem">Không có khác biệt.</p>`;
  return t.split("\n").map(l => `<div class="${/^\+\+\+|^---|^diff /.test(l) ? "f" : l[0] === "+" ? "a" : l[0] === "-" ? "d" : l.startsWith("@@") ? "h" : ""}">${esc(l) || " "}</div>`).join("");
}
function commitLabel(c) {
  let m = c.msg.match(/^(\d\d_\w+) (?:cost=\$([\d.]+)|(.*))/);
  if (m && STAGE[m[1]]) return [ic(STAGE[m[1]][1], "sm"), "run", m[2] ? `Agent xong bước <b>${sv(m[1])}</b>` : `<b>${sv(m[1])}</b>: ${esc(m[3])}`, m[2] ? money(m[2]) : ""];
  if ((m = c.msg.match(/^user edit (.+)/))) return [ic("pencil", "sm"), "user", `Sửa <code>${esc(m[1])}</code>`, ""];
  if ((m = c.msg.match(/^upload (\d+)/))) return [ic("upload", "sm"), "user", `Tải lên ${m[1]} tệp`, ""];
  if (c.msg === "new run") return [ic("sparkles", "sm"), "", "Tạo phiên", ""];
  if (c.msg === "edit bonrs.yaml") return [ic("settings-2", "sm"), "user", "Sửa cấu hình phiên", ""];
  return [ic("git-commit-horizontal", "sm"), "", esc(c.msg), ""];
}
const EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"; // git's empty tree: "before the first commit"
const CHG = { A: ["Thêm mới", "file-plus", "ok"], M: ["Sửa", "file-pen", "run"], D: ["Xoá", "file-x", "bad"] };
function parseDiff(t) {
  const rows = []; let o = 0, n = 0;
  for (const l of t.replace(/\n$/, "").split("\n")) {
    if (/^Binary files/.test(l)) { rows.push({ k: "bin" }); continue; }
    if (/^(diff --git|index |--- |\+\+\+ |new file|deleted file|old mode|new mode|similarity|rename)/.test(l)) continue;
    const m = l.match(/^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@(.*)/);
    if (m) { o = +m[1]; n = +m[2]; rows.push({ k: "h", n, ctx: m[3] }); continue; }
    if (l[0] === "\\") continue;
    if (l[0] === "+") rows.push({ k: "a", n: n++, t: l.slice(1) }); else if (l[0] === "-") rows.push({ k: "d", o: o++, t: l.slice(1) }); else rows.push({ k: "c", o: o++, n: n++, t: l.slice(1) });
  }
  return rows;
}
function diffTable(rows) {
  if (rows.some(r => r.k === "bin")) return `<p class="muted small" style="padding:.6rem .9rem">Tệp nhị phân (PDF, ảnh…): mở tệp để xem.</p>`;
  if (!rows.length) return `<p class="muted small" style="padding:.6rem .9rem">Không có khác biệt về nội dung.</p>`;
  return `<table class="dtab"><tbody>${rows.slice(0, 4000).map(r => r.k === "h" ? `<tr class="h"><td colspan="3">Đoạn từ dòng ${r.n}${r.ctx.trim() ? ` · ${esc(r.ctx.trim().slice(0, 80))}` : ""}</td></tr>`
    : `<tr class="${r.k}"><td class="ln">${r.o ?? ""}</td><td class="ln">${r.n ?? ""}</td><td class="tx"><span class="mk" aria-hidden="true">${r.k === "a" ? "+" : r.k === "d" ? "−" : ""}</span>${esc(r.t) || " "}</td></tr>`).join("")}</tbody></table>
    ${rows.length > 4000 ? `<p class="muted small" style="padding:.4rem .9rem">Chỉ hiện 4000 dòng đầu; tải tệp để xem đủ.</p>` : ""}`;
}
async function tHistory(el, slug) {
  const h = await api(`/runs/${slug}/history`);
  if (!h.length) return (el.innerHTML = `<div class="empty card"><span class="big">${ic("history", "lg")}</span><h2>Chưa có mốc nào</h2></div>`);
  let mode = "one", sel = 0, A = h.length - 1, B = 0;
  const when = c => fmtTs(c.date.replace(" ", "T").replace(" ", ""));
  const who = c => c.author === "bonrs" ? "agent" : c.author.split("@")[0];
  el.innerHTML = `<div class="cols hist"><section class="card"><div class="card-head"><h2>${ic("history")} Các mốc (${h.length})</h2></div>
      <div class="seg" role="radiogroup" aria-label="Cách xem"><label><input type="radio" name="hm" value="one" checked><span>${ic("eye", "sm")} Xem từng mốc</span></label><label><input type="radio" name="hm" value="cmp"><span>${ic("git-compare", "sm")} So sánh hai mốc</span></label></div>
      <p class="muted small" id="hhint" style="margin:.7rem 0"></p><ol class="mlist" id="ml"></ol></section>
    <section class="card" id="hv" aria-live="polite"></section></div>`;
  const list = () => {
    $("#hhint").innerHTML = mode === "one" ? "Bấm một mốc để xem nó thay đổi những tệp nào. Bấm tên tệp để xem từng dòng: <span class='plus'>xanh là thêm</span>, <span class='minus'>đỏ là bớt</span>."
      : "Bấm mốc cũ hơn để đặt <span class='ab a'>A</span>, rồi bấm mốc mới hơn để đặt <span class='ab b'>B</span>. Bên phải là mọi thay đổi từ A đến B.";
    $("#ml").innerHTML = h.map((c, i) => { const [icon, cls, what, extra] = commitLabel(c), on = mode === "one" ? i === sel : i === A || i === B;
      return `<li><button type="button" class="mrow ${on ? "on" : ""}" data-i="${i}" aria-pressed="${on}"><span class="tic ${cls}">${icon}</span><span class="what">${what}<small>${esc(who(c))} · ${esc(when(c))}${extra ? " · " + extra : ""}</small></span>
        ${mode === "cmp" && i === A ? '<span class="ab a">A</span>' : ""}${mode === "cmp" && i === B ? '<span class="ab b">B</span>' : ""}</button></li>`; }).join("");
    $$(".mrow", el).forEach(b => b.onclick = () => { const i = +b.dataset.i;
      if (mode === "one") sel = i; else if (B !== null && A !== null) { A = i; B = null; } else if (i !== A) B = i;
      list(); show(); });
  };
  const show = async () => {
    const v = $("#hv");
    if (mode === "cmp" && (A === null || B === null)) return (v.innerHTML = `<div class="empty"><span class="big">${ic("git-compare", "lg")}</span><h2>Chọn mốc B</h2><p>Đã chọn A: ${commitLabel(h[A])[2]}. Bấm thêm một mốc nữa để so sánh.</p></div>`);
    const [old, neu] = mode === "one" ? [sel + 1 < h.length ? h[sel + 1].hash : EMPTY_TREE, h[sel].hash] : [h[Math.max(A, B)].hash, h[Math.min(A, B)].hash];
    const title = mode === "one" ? `${commitLabel(h[sel])[2]}<small>${esc(who(h[sel]))} · ${esc(when(h[sel]))}</small>`
      : `Từ <span class="ab a">A</span> ${commitLabel(h[Math.max(A, B)])[2]} đến <span class="ab b">B</span> ${commitLabel(h[Math.min(A, B)])[2]}<small>${esc(when(h[Math.max(A, B)]))} → ${esc(when(h[Math.min(A, B)]))}</small>`;
    v.innerHTML = `<div class="vtitle">${title}</div><p class="loading"><span class="spin"></span> Đang tải thay đổi…</p>`;
    const fs = await api(`/runs/${slug}/changes?a=${old}&b=${neu}`);
    const techF = p => /^(\.bonrs|logs|hitl|exp\/logs)\//.test(p) || ["events.jsonl", "state.json", ".gitignore"].includes(p);
    const main = fs.filter(f => !techF(f.path)), tech = fs.filter(f => techF(f.path));
    const add = main.reduce((s, f) => s + (f.add || 0), 0), del = main.reduce((s, f) => s + (f.del || 0), 0);
    const row = f => { const [l, i, c] = CHG[f.status] || CHG.M, top = f.path.includes("/") ? f.path.split("/")[0] : "", tot = (f.add || 0) + (f.del || 0);
        return `<details class="fchg" data-p="${esc(f.path)}"><summary><span class="pill ${c === "ok" ? "done" : c === "bad" ? "failed" : "running"}"><span class="dot"></span>${l}</span>
          <span class="fp"><b>${ic(fileIcon(f.path), "sm")}${esc(f.path.split("/").pop())}</b><small>${esc(FOLDER[top]?.[0] || (top ? top : FOLDER[""][0]))}${top ? " · " + esc(f.path) : ""}</small></span>
          <span class="cnt">${f.add == null ? "nhị phân" : `<span class="plus">+${f.add}</span> <span class="minus">−${f.del}</span>`}${tot ? `<span class="cbar"><i class="a" style="width:${(f.add / tot) * 100}%"></i><i class="d" style="width:${(f.del / tot) * 100}%"></i></span>` : ""}</span></summary>
          <div class="dbody"></div>${f.status !== "D" ? `<a class="small openf" href="#/run/${esc(slug)}/files/${encodeURIComponent(f.path)}">${ic("external-link", "sm")} Mở tệp</a>` : ""}</details>`; };
    v.innerHTML = `<div class="vtitle">${title}</div>
      <p class="chgsum">${main.length ? `${main.length} tệp nội dung thay đổi · <span class="plus">+${add} dòng</span> · <span class="minus">−${del} dòng</span>` : "Không có tệp nội dung nào thay đổi."}</p>
      ${main.map(row).join("")}
      ${tech.length ? `<details class="techgrp"><summary>${ic("terminal", "sm")} Tệp kỹ thuật của hệ thống (${tech.length}): nhật ký, trạng thái. Thường không cần xem.</summary>${tech.map(row).join("")}</details>` : ""}`;
    $$(".fchg", v).forEach(d => d.addEventListener("toggle", async () => { if (!d.open || d.dataset.loaded) return; d.dataset.loaded = 1; $(".dbody", d).innerHTML = `<p class="loading"><span class="spin"></span></p>`;
      $(".dbody", d).innerHTML = diffTable(parseDiff(await api(`/runs/${slug}/diff?a=${old}&b=${neu}&path=${encodeURIComponent(d.dataset.p)}`))); }));
    if (main.length === 1) $(".fchg", v).open = true;
  };
  $$("[name=hm]", el).forEach(r => r.onchange = () => { mode = r.value; if (mode === "cmp") { A = h.length - 1; B = 0; } list(); show(); });
  list(); show();
}

// ---------- one stage: everything that happened in it ----------
const STAGE_FILES = { "00_scope": ["scope.md", "hypotheses.json", "lit/base_notes.md", "lit/base/"], "01_literature": ["lit/review.md", "lit/gaps.md", "lit/key_papers.md", "lit/novelty.md", "lit/refs.bib", "lit/REQUEST", "lit/uploads/"],
  "02_journal": ["journal/"], "03_plan": ["plan.md", "plan/", "paper/outline.md", "exp/README.md"], "04_experiment": ["exp/"], "05_draft": ["paper/main", "paper/claims.yaml", "paper/refs.bib", "paper/wordcount.md"],
  "06_review": ["reviews/"], "07_revise": ["paper/response_letter.md"], "08_submission": ["submission/"], "09_retro": ["retro.md"] };
const ofStage = (s, p) => !!p && (STAGE_FILES[s] || []).some(x => p === x || p.startsWith(x));
const GATE_STAGE = Object.fromEntries(Object.entries(GATE_AFTER));
async function tStage(el, slug, r, stage) {
  if (!r.stages.includes(stage)) stage = nowStage(r) || r.stages[0];
  const [l, hist, files, cs] = await Promise.all([api(`/runs/${slug}/log?stage=${stage}`), api(`/runs/${slug}/history`), api(`/runs/${slug}/tree`), api(`/runs/${slug}/comments`)]);
  const st = stageState(r, stage), inf = r.stage_info?.[stage], live = isLive(r) && r.current === stage;
  const atts = []; let cur = null; // attempts are separated by markers; logs from before markers existed form one attempt
  for (const e of l.events) { if (e.t === "attempt") { cur = { ts: e.v, ev: [] }; atts.push(cur); continue; } if (!cur) { cur = { ts: null, ev: [] }; atts.push(cur); } cur.ev.push(e); }
  const mine = r.events.filter(e => e.actor === "agent:" + stage || (e.gate && (e.stage === stage || GATE_STAGE[e.gate] === stage)) || ofStage(stage, e.path));
  const ends = mine.filter(e => e.type === "stage_end"), nDone = atts.length - (live ? 1 : 0);
  atts.forEach((a, i) => { if (i < nDone) a.end = ends[ends.length - nDone + i]; if (!a.ts && a.end) a.ts = a.end.ts; });
  const commits = hist.filter(c => c.msg.startsWith(stage + " ") || ((m => m && ofStage(stage, m[1]))(c.msg.match(/^user edit (.+)/))));
  const mycs = cs.filter(c => ofStage(stage, c.path));
  const outs = files.filter(f => ofStage(stage, f) && !/(^|\/)\./.test(f) && !/\.(aux|log|out|txt)$/.test(f)).slice(0, 40);
  const timeline = [...mine.map(e => ({ ts: e.ts, html: evRow(e) })), ...mycs.map(c => ({ ts: c.ts, html: `<li><span class="tic user">${ic("message-square", "sm")}</span><span class="what">${esc(c.email)} góp ý <code>${esc(c.path)}</code><small>${esc(c.body.slice(0, 140))}</small></span><span class="when">${ago(c.ts)}</span></li>` }))]
    .sort((a, b) => toMs(b.ts) - toMs(a.ts));
  const steps = a => a.ev.filter(e => e.t === "tool").length;
  el.innerHTML = `<nav class="filter stagepick" aria-label="Chọn bước">${r.stages.map((s, i) => `<a href="#/run/${esc(slug)}/stage/${s}" class="${s === stage ? "on" : ""} ${stageState(r, s)}" ${s === stage ? 'aria-current="page"' : ""}>${i}. ${sv(s)}</a>`).join("")}</nav>
    <section class="card"><div class="card-head"><div style="display:flex;gap:.8rem;align-items:center"><span class="hicon">${ic(STAGE[stage][1])}</span>
        <div><h2 style="margin:0">Bước ${r.stages.indexOf(stage)}: ${sv(stage)}</h2><span class="muted small">${esc(STAGE[stage][2])}</span></div></div>
        ${pill({ done: "done", running: "running", gate: "waiting", failed: "failed" }[st] || "", { done: "Đã xong", running: "Đang chạy", gate: "Chờ bạn duyệt", failed: "Lỗi", next: "Bước kế tiếp", todo: "Chưa chạy" }[st])}</div>
      <div class="kpis k4" style="margin:.8rem 0 .4rem"><div class="kpi"><span class="kic">${ic("rotate-cw")}</span><span><b>${atts.length || inf?.runs || 0}</b><small>Số lần chạy</small></span></div>
        <div class="kpi"><span class="kic o">${ic("wallet")}</span><span><b>${money(inf?.cost)}</b><small>Chi phí cộng dồn</small></span></div>
        <div class="kpi"><span class="kic b">${ic("timer")}</span><span><b>${inf?.seconds ? dur(inf.seconds) : "—"}</b><small>Thời gian agent làm</small></span></div>
        <div class="kpi"><span class="kic">${ic("git-commit-horizontal")}</span><span><b>${commits.length}</b><small>Mốc lưu</small></span></div></div>
      ${outs.length ? `<div class="small" style="font-weight:600;margin-top:.4rem">Kết quả của bước</div><div class="linkrow">${outs.map(f => fileLink(slug, f)).join("")}</div>` : ""}</section>
    <div class="cols side-r" style="margin-top:1rem"><section class="card"><div class="card-head"><h2>${ic("route")} Lưu trình thực hiện</h2>${live ? `<span class="live">Đang chạy, tự cập nhật</span>` : ""}</div>
        ${atts.length ? atts.map((a, i) => `<details class="att" data-i="${i}" ${i === atts.length - 1 ? "open" : ""}><summary><b>Lần ${i + 1}</b><span class="muted">${a.ts ? fmtTs(a.ts) : ""}</span>
            <span class="muted">${steps(a)} thao tác${a.end ? ` · ${money(a.end.cost)} · ${dur(a.end.seconds)}` : ""}</span>${a.end ? (a.end.error ? pill("failed", "Lỗi") : pill("done", "Xong")) : live && i === atts.length - 1 ? pill("running", "Đang chạy") : ""}</summary>
            <div class="feed">${a.ev.map(feedItem).join("") || '<p class="muted">Không có nội dung.</p>'}</div></details>`).join("")
          : `<p class="muted">Bước này chưa chạy lần nào.</p>`}</section>
      <aside class="stack"><section class="card"><h2>${ic("history")} Diễn biến</h2>${timeline.length ? `<ol class="tl">${timeline.map(x => x.html).join("")}</ol>` : '<p class="muted">Chưa có hoạt động.</p>'}</section>
        <section class="card"><h2>${ic("git-commit-horizontal")} Các mốc lưu</h2>${commits.length ? `<ol class="tl">${commits.map(c => { const [icon, cls, what, extra] = commitLabel(c);
          return `<li><span class="tic ${cls}">${icon}</span><span class="what">${what}<small>${extra ? extra + " · " : ""}${esc(c.date.slice(0, 16))}</small></span><span class="when"><button class="btn sm quiet" data-c="${c.hash}" aria-label="Xem thay đổi">${ic("eye", "sm")}</button></span></li>`; }).join("")}</ol>`
          : '<p class="muted small">Mỗi lần bước này chạy xong, hoặc bạn sửa tệp của bước, hệ thống lưu một mốc để so sánh.</p>'}</section></aside></div>`;
  $$("[data-c]", el).forEach(b => b.onclick = async () => { const d = await api(`/runs/${slug}/diff?a=${b.dataset.c}~1&b=${b.dataset.c}`);
    dialog(`<h2>${ic("git-compare")} Thay đổi của mốc này</h2><div class="diff" style="max-height:65vh;overflow:auto">${diffHtml(d)}</div><div class="dfoot"><button type="button" class="btn" data-close>Đóng</button></div>`, async () => {}); });
  const f = $(".att[open] .feed", el); if (f) f.scrollTop = f.scrollHeight;
  if (live) autoRefresh(async () => { const n = await api(`/runs/${slug}`); const open = $$(".att", el).filter(d => d.open).map(d => d.dataset.i); await tStage(el, slug, n, stage);
    $$(".att", el).forEach(d => d.open = open.includes(d.dataset.i) || d.dataset.i == $$(".att", el).length - 1); }, 5000);
}

// ---------- run settings: a form; YAML stays available for experts ----------
const GATE_HINT = { after_scope: "Bạn chọn giả thuyết để làm, hoặc dừng phiên", after_literature: "Xem khoảng trống và tính mới; tải PDF trả phí nếu agent cần",
  after_plan: "Duyệt kế hoạch thí nghiệm trước khi agent dùng máy chạy", after_results: "Xem phản biện và thư trả lời sau mỗi vòng chỉnh sửa", before_submission: "Duyệt hồ sơ nộp trước bước rút kinh nghiệm" };
const CFG_SECS = [["s-idea", "lightbulb", "Ý tưởng & tạp chí"], ["s-paper", "file-text", "Bài viết"], ["s-review", "scale", "Phản biện nội bộ"], ["s-gates", "hand", "Cổng duyệt"],
  ["s-hosts", "server", "Máy chạy"], ["s-cost", "wallet", "Model & chi phí"], ["s-yaml", "file-code", "Nâng cao"]];
async function tConfig(el, slug, r) {
  const [y, hs] = await Promise.all([api(`/runs/${slug}/file?path=bonrs.yaml`), api("/hosts")]);
  const c = r.config || {}, g = c.gates || {}, cur = c.remote?.hosts || [];
  const opts = [{ key: "local", label: "Máy chủ bonrs", sub: "Có sẵn, không cần cài", cfg: { name: "local", type: "local", setup: "auto" } },
    ...hs.filter(h => h.type !== "local").map(h => ({ key: "h" + h.id, label: h.name, sub: h.config.ssh || h.type, cfg: { name: h.name, type: h.type, ...h.config } }))];
  cur.filter(h => !opts.some(o => o.cfg.name === h.name)).forEach((h, i) => opts.push({ key: "x" + i, label: h.name, sub: "chỉ khai báo trong phiên này", cfg: h }));
  const sel = (n, v, o) => `<select name="${n}">${Object.entries(o).map(([k, l]) => `<option value="${esc(k)}" ${String(v) === k ? "selected" : ""}>${esc(l)}</option>`).join("")}</select>`;
  const sec = (id, title, desc, body) => { const [, i] = CFG_SECS.find(x => x[0] === id);
    return `<section class="card set" id="${id}"><div class="set-head"><span class="hicon">${ic(i)}</span><div><h2>${title}</h2><p>${desc}</p></div></div>${body}</section>`; };
  el.innerHTML = `${isLive(r) ? `<div class="banner req" style="padding:.7rem .9rem">${ic("info", "sm")}<div class="small">Phiên đang chạy: thay đổi có hiệu lực từ lượt chạy tiếp theo.</div></div>` : ""}
    <div class="setwrap"><nav class="setnav" aria-label="Các mục cấu hình">${CFG_SECS.map(([id, i, t], k) => `<button type="button" data-go="${id}" class="${k ? "" : "on"}">${ic(i, "sm")}${t}</button>`).join("")}</nav>
    <div><form id="cf">
    ${sec("s-idea", "Ý tưởng & tạp chí", "Mục tiêu agent luôn bám theo trong suốt phiên.", `
      <label>Ý tưởng<textarea name="idea" rows="5" required>${esc(c.idea)}</textarea></label>
      <div class="grid2"><label>Tạp chí đích<input name="target_journal" required value="${esc(c.target_journal)}"></label>
        <label>Tạp chí dự phòng<input name="backup_journals" value="${esc((c.backup_journals || []).join(", "))}" placeholder="Cách nhau bằng dấu phẩy"><span class="hint">Để trống thì bước Giả thuyết tự đề xuất.</span></label></div>
      <label>Bài báo nền<textarea name="base_papers" rows="3" placeholder="Mỗi dòng một DOI, đường dẫn hoặc tên bài">${esc((c.base_papers || []).join("\n"))}</textarea><span class="hint">Tệp PDF bài nền tải lên ở tab Tệp, thư mục lit/base.</span></label>`)}
    ${sec("s-paper", "Bài viết", "Mặc định theo tạp chí đích; chỉ đổi khi bạn muốn ép một lựa chọn.", `
      <div class="grid2"><label>Lĩnh vực${sel("domain", c.domain, DOMAIN_VI)}</label><label>Loại bài${sel("article_type", c.article_type || "auto", TYPE_VI)}</label>
        <label>Định dạng bản thảo${sel("paper_format", c.paper_format || "auto", { auto: "Theo tạp chí", latex: "LaTeX", docx: "Word (.docx)" })}</label><label>Ngôn ngữ bài${sel("language", c.language || "en", { en: "Tiếng Anh", vi: "Tiếng Việt" })}</label></div>`)}
    ${sec("s-review", "Phản biện nội bộ", "Agent tự phản biện và sửa bài đến khi đạt điểm hoặc hết số vòng.", `
      <div class="grid2"><label>Số vòng tối đa<select name="max_rounds">${[1, 2, 3, 4, 5, 6].map(n => `<option value="${n}" ${+(c.review?.max_rounds ?? 3) === n ? "selected" : ""}>${n} vòng${n === 3 ? " (khuyên dùng)" : ""}</option>`).join("")}</select></label>
        <label>Điểm đạt (trên 10)<input name="accept_score" type="number" min="0" max="10" step="0.5" value="${esc(c.review?.accept_score ?? 7.5)}"><span class="hint">Dừng sửa khi đạt điểm này và không còn vấn đề lớn.</span></label></div>`)}
    ${sec("s-gates", "Cổng duyệt", "Những chỗ agent dừng lại chờ bạn xem kết quả trước khi đi tiếp.", `
      <div class="gatelist">${Object.entries(GATE).map(([k, [t]]) => `<label class="grow"><span class="t"><b>${esc(t)}</b><small>${esc(GATE_HINT[k] || "")}</small></span>
        ${k === "after_scope" ? `<span class="chip">${ic("lock", "sm")} Luôn bật</span>` : `<span class="switch"><input type="checkbox" name="g_${k}" ${g[k] ? "checked" : ""} aria-label="${esc(t)}"></span>`}</label>`).join("")}</div>
      <div class="subblock"><h3>Khi không ai duyệt</h3>${waitCtl("gate_timeout_hours", c.gate_timeout_hours ?? 12)}</div>`)}
    ${sec("s-hosts", "Máy chạy", "Nơi agent chạy thí nghiệm. Chọn nhiều máy thì mỗi lần chạy được gửi sang máy đang rảnh nhất.", `
      <div class="opts compact">${opts.map(o => `<label class="opt"><input type="checkbox" name="host" value="${o.key}" ${cur.some(h => h.name === o.cfg.name) ? "checked" : ""}><span>${ic(o.cfg.type === "local" ? "container" : "server")}<span class="ot"><b>${esc(o.label)}</b><small>${esc(o.sub)}</small></span></span></label>`).join("")}</div>
      <a class="small" href="#/hosts">${ic("plus", "sm")} Thêm máy GPU riêng</a>`)}
    ${sec("s-cost", "Model & chi phí", "Model dùng cho mọi bước và trần chi phí cho mỗi bước.", `
      <div class="grid2"><label>Model${modelSel("model", c.model)}</label><label>Trần chi phí mỗi bước (USD)<input name="max_budget_usd" type="number" min="1" max="1000" step="1" value="${esc(c.max_budget_usd ?? 30)}" data-budget></label></div>
      <div class="bh budget" aria-live="polite"></div>`)}
    <div class="savebar sticky" id="sb"><span class="muted small" id="sbt">Chưa có thay đổi.</span><span class="grow1"></span>
      <button type="button" class="btn ghost" id="cx" hidden>Huỷ thay đổi</button><button class="btn" id="sv" disabled>${ic("save", "sm")} Lưu cấu hình</button></div></form>
    ${sec("s-yaml", "Nâng cao", "Cùng nội dung ở dạng văn bản bonrs.yaml. Chỉ cần khi muốn chỉnh mục mà form chưa có.", `
      <details class="more"><summary class="linkbtn">Mở trình sửa bonrs.yaml</summary>
        <textarea class="code" id="y" aria-label="Cấu hình YAML" spellcheck="false" style="margin-top:.8rem">${esc(y)}</textarea><button class="btn ghost" id="s" style="margin-top:.6rem">${ic("save", "sm")} Lưu YAML</button></details>`)}
    </div></div>`;
  const f0 = $("#cf"), costSec = $("#s-cost");
  bindWait(f0); budgetHint(costSec, false); $("[data-model]", costSec).onchange = () => budgetHint(costSec, false);
  const snap = () => JSON.stringify([...new FormData(f0)]), base = snap();
  const dirty = () => { const d = snap() !== base; $("#sv").disabled = !d; $("#cx").hidden = !d; $("#sb").classList.toggle("dirty", d); $("#sbt").textContent = d ? "Có thay đổi chưa lưu." : "Chưa có thay đổi."; };
  f0.addEventListener("input", dirty); f0.addEventListener("change", dirty);
  $("#cx").onclick = () => tConfig(el, slug, r);
  $$("[data-go]", el).forEach(b => b.onclick = () => $("#" + b.dataset.go).scrollIntoView({ behavior: "smooth", block: "start" }));
  const io = new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting) $$("[data-go]", el).forEach(b => b.classList.toggle("on", b.dataset.go === e.target.id)); }), { rootMargin: "-20% 0px -70% 0px" });
  $$(".set", el).forEach(x => io.observe(x));
  f0.onsubmit = async e => { e.preventDefault(); const f = new FormData(f0), n = k => Number(f.get(k));
    const next = { ...c, idea: f.get("idea").trim(), target_journal: f.get("target_journal").trim(),
      backup_journals: f.get("backup_journals").split(",").map(x => x.trim()).filter(Boolean), base_papers: f.get("base_papers").split("\n").map(x => x.trim()).filter(Boolean),
      domain: f.get("domain"), article_type: f.get("article_type"), paper_format: f.get("paper_format"), language: f.get("language"), model: f.get("model") || c.model,
      max_budget_usd: n("max_budget_usd"), review: { max_rounds: n("max_rounds"), accept_score: n("accept_score") }, gate_timeout_hours: readWait(f, "gate_timeout_hours"),
      gates: Object.fromEntries(Object.keys(GATE).map(k => [k, k === "after_scope" || f.has("g_" + k)])),
      remote: { hosts: opts.filter(o => f.getAll("host").includes(o.key)).map(o => o.cfg) } };
    if (!next.remote.hosts.length) return toast("Chọn ít nhất một máy chạy", true);
    await api(`/runs/${slug}/config`, { method: "PUT", body: JSON.stringify(next) }); toast("Đã lưu cấu hình"); route(); };
  $("#s").onclick = async () => { await api(`/runs/${slug}/config`, { method: "PUT", body: $("#y").value }); toast("Đã lưu cấu hình"); route(); };
}

// ---------- hosts ----------
const RUNNAME = LANG === "en" ? "&lt;run name&gt;" : "&lt;tên phiên&gt;";
const HOST_TYPES = { local: ["Máy chủ bonrs", "container"], ssh: ["Máy riêng qua SSH", "server"], slurm: ["Cụm Slurm", "network"] };
const sshHint = out => /Permission denied/i.test(out) ? "Máy từ chối đăng nhập: lệnh ở bước 2 chưa được chạy trên máy đó, hoặc chạy bằng tài khoản khác với tài khoản ở bước 1."
  : /Could not resolve|Name or service not known/i.test(out) ? "Không tìm thấy địa chỉ máy: kiểm tra lại tên hoặc IP ở bước 1."
  : /timed out|No route|Connection refused|timeout/i.test(out) ? "Không với tới máy: kiểm tra máy đang bật, cổng SSH đúng, và server bonrs cùng mạng/VPN với máy đó."
  : /Host key verification|REMOTE HOST IDENTIFICATION/i.test(out) ? "Máy này đã đổi khoá nhận dạng (cài lại hệ điều hành?). Nhờ quản trị viên xoá khoá cũ." : "";
const gb = mb => Math.round(num(mb) / 1024) + " GB";
function specHtml(i, local) {
  if (!i || !i.host) return "";
  const g = i.gpus || [];
  return `<dl class="kv small" style="margin-top:.6rem"><dt>Máy</dt><dd>${esc(i.host)}${i.os ? " · " + esc(i.os) : ""}</dd>
    <dt>CPU / RAM</dt><dd>${esc(i.cpu || "?")} nhân${i.mem ? " · " + esc(i.mem) + " GB RAM" : ""}${i.load ? " · tải hiện tại " + esc(i.load) : ""}</dd>
    <dt>GPU</dt><dd>${g.length ? g.map(x => `#${esc(x.index)} ${esc(x.name)} · ${gb(x.mem_total_mb)} · đang bận ${num(x.util)}%`).join("<br>") : "Không có"}</dd>
    <dt>Python</dt><dd>${esc(i.py || "chưa cài")}${i.venv === "no" ? " · thiếu gói venv (cài <code>python3-venv</code> hoặc dùng conda)" : ""}${i.conda ? " · có conda" : ""}</dd>
    <dt>Ổ đĩa</dt><dd>${local ? "" : `<code>${esc(i.home || "~")}</code> · `}còn trống ${esc(i.disk || "?")}</dd></dl>`;
}
const setupLabel = s => !s || s === "auto" ? "Tự động: tạo .venv riêng cho phiên, cài requirements.txt" : s === "true" ? "Không chuẩn bị gì" : s;
const condaBase = c => !c ? "" : c.replace(/\/(condabin|bin)\/conda$/, "");
const testBanner = (r, local) => `<div class="banner ${r.ok ? "ok" : "bad"}" style="margin:.8rem 0 0"><span class="bic">${ic(r.ok ? "plug-zap" : "unplug")}</span><div><h2>${r.ok ? "Kết nối được" : "Chưa kết nối được"}</h2>
  ${r.ok ? specHtml(r.info, local) : `<p>${sshHint(r.output) || "Xem chi tiết kỹ thuật bên dưới."}</p>`}<details><summary class="muted small" style="cursor:pointer">Chi tiết kỹ thuật</summary><pre class="code" style="max-height:200px">${esc(r.output)}</pre></details></div></div>`;
async function vHosts(app) {
  const [hosts, key] = await Promise.all([api("/hosts"), api("/sshkey")]);
  const cmd = `mkdir -p ~/.ssh && chmod 700 ~/.ssh && echo '${key.public_key}' >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys`;
  const all = [{ id: "local", name: "Máy chủ bonrs", type: "local", owner: 0, config: { setup: "auto" } }, ...hosts.filter(h => h.type !== "local")];
  app.innerHTML = `<div class="wrap">${head("Máy chạy thí nghiệm", "Agent chạy code thí nghiệm ở đây. Không cần cài gì: mặc định chạy ngay trên server bonrs. Thêm máy GPU riêng khi cần.")}
    <div class="rgrid">${all.map(h => `<article class="card"><div class="card-head"><div style="display:flex;gap:.7rem;align-items:center"><span class="hicon">${ic(HOST_TYPES[h.type]?.[1] || "server")}</span>
        <div><h2 style="margin:0">${esc(h.name)}</h2><span class="muted small">${h.id === "local" ? "Có sẵn, không cần cài đặt" : esc(h.config.ssh + (h.config.port ? ":" + h.config.port : ""))}${h.owner === 0 && h.id !== "local" ? " · dùng chung" : ""}</span></div></div></div>
      <dl class="kv"><dt>Thư mục</dt><dd>${h.type === "local" ? "Thư mục <code>exp/</code> riêng của từng phiên, trên server bonrs" : `<code>${esc(h.config.workdir || "~/bonrs-runs")}/${RUNNAME}</code>, mỗi phiên một thư mục`}</dd>
        <dt>Môi trường</dt><dd>${esc(setupLabel(h.config.setup))}</dd>${h.config.gpus ? `<dt>GPU dùng</dt><dd>${esc(h.config.gpus)}</dd>` : ""}</dl>
      <div class="actions"><button class="btn sm" data-t="${h.id}">${ic(h.type === "local" ? "cpu" : "plug-zap", "sm")} ${h.type === "local" ? "Xem cấu hình máy" : "Kiểm tra kết nối"}</button>
        ${h.id !== "local" && (h.owner === ME.id || ME.role === "admin") ? `<button class="btn sm danger" data-d="${h.id}">${ic("trash-2", "sm")} Xoá</button>` : ""}</div><div id="t${h.id}"></div></article>`).join("")}</div>
    <div class="cols side-r" style="margin-top:1.5rem">
    <section class="card"><h2>${ic("plus")} Thêm máy riêng (máy GPU, máy phòng lab…)</h2><ol class="steps wiz">
      <li><h3>Địa chỉ máy</h3><p class="muted small">Chính là thông tin bạn vẫn gõ khi <code>ssh</code> vào máy đó.</p>
        <div class="grid2 hostaddr"><label>Tài khoản@địa chỉ<input id="w-ssh" placeholder="ubuntu@192.168.1.20" autocomplete="off" spellcheck="false"></label><label>Cổng SSH<input id="w-port" type="number" min="1" max="65535" value="22"></label></div></li>
      <li><h3>Cho phép bonrs đăng nhập</h3><p class="muted small">Đăng nhập vào máy đó như bình thường, dán lệnh dưới đây vào terminal và chạy <b>một lần</b>. Không cần mật khẩu; muốn thu hồi thì xoá dòng <code>bonrs-user-${ME.id}</code> trong <code>~/.ssh/authorized_keys</code>.</p>
        <pre class="code cmd">${esc(cmd)}</pre><button type="button" class="btn ghost sm" id="w-cp">${ic("copy", "sm")} Sao chép lệnh</button></li>
      <li><h3>Kiểm tra</h3><p class="muted small">bonrs thử đăng nhập và đọc cấu hình máy: CPU, RAM, GPU, Python, ổ đĩa.</p><button type="button" class="btn" id="w-test">${ic("plug-zap", "sm")} Kiểm tra kết nối</button><div id="w-out"></div></li>
      <li id="w-last"><h3>Đặt tên và lưu</h3><form id="w-save" hidden>
        <div class="grid2"><label>Tên máy<input name="name" required pattern="[a-z0-9_\\-]+" maxlength="40"><span class="hint">Chữ thường, số, gạch ngang.</span></label>
          <label>Thư mục làm việc<input name="workdir" value="~/bonrs-runs"><span class="hint">Mỗi phiên một thư mục con bên trong, tự tạo.</span></label></div>
        <div id="w-gpus"></div>
        <fieldset class="bare"><legend>Chuẩn bị môi trường trước mỗi lần chạy</legend><div class="opts" id="w-env"></div></fieldset>
        <label id="w-custom" hidden>Lệnh riêng<input name="custom" placeholder="vd. source ~/miniconda3/bin/activate myenv"></label>
        ${ME.role === "admin" ? '<label class="switch" style="margin-bottom:1rem"><input type="checkbox" name="shared"> Cho mọi người dùng (mỗi người vẫn phải chạy lệnh ở bước 2 với khoá của mình)</label>' : ""}
        <button class="btn">${ic("save", "sm")} Lưu máy</button></form><p class="muted small" id="w-hint">Hiện ra sau khi kiểm tra kết nối.</p></li></ol></section>
    <aside class="card faq"><h2>${ic("circle-help")} Câu hỏi thường gặp</h2>
      <details open><summary>Khoá SSH ở bước 2 là gì? Có gắn với máy nào không?</summary><p>Đó là “chìa khoá” của <b>tài khoản bonrs của bạn</b>, không gắn với máy cụ thể nào. Một khoá dùng cho mọi máy bạn thêm: máy nào chạy lệnh ở bước 2 thì máy đó cho agent của bạn vào. Người khác trong nhóm có khoá riêng, không dùng được máy của bạn nếu bạn không thêm khoá của họ.</p></details>
      <details><summary>Có nhiều máy thì có chia tải được không?</summary><p>Có, ở mức từng lần chạy. Chọn nhiều máy cho một phiên (lúc tạo phiên hoặc ở tab Cấu hình), agent gửi mỗi lần chạy độc lập (seed, fold, ablation, baseline) sang máy đang rảnh nhất, đo theo GPU/CPU ngay lúc gửi. Một lần huấn luyện không bị chia nhỏ sang nhiều máy.</p></details>
      <details><summary>Thí nghiệm chạy ở thư mục nào, môi trường cài thế nào?</summary><p>Mỗi phiên có thư mục riêng: <code>~/bonrs-runs/${RUNNAME}</code> trên máy SSH, hoặc <code>exp/</code> của phiên trên server bonrs. Chế độ “Tự động” tạo môi trường Python riêng (<code>.venv</code>) trong thư mục đó và cài các gói trong <code>requirements.txt</code> agent viết, nên không đụng tới môi trường có sẵn của bạn.</p></details>
      <details><summary>Máy ở mạng nội bộ hoặc sau VPN?</summary><p>Server cài bonrs phải SSH tới được máy đó: cùng mạng LAN, cùng VPN (WireGuard, Tailscale…) hoặc máy mở cổng SSH ra ngoài.</p></details>
      <details><summary>Xem khoá công khai của bạn</summary><textarea readonly rows="3" class="mono" style="font-size:.75rem" aria-label="Khoá công khai">${esc(key.public_key)}</textarea></details></aside></div></div>`;
  $("#w-cp").onclick = async () => { try { await navigator.clipboard.writeText(cmd); toast("Đã sao chép lệnh"); } catch { toast("Không sao chép được, hãy bôi đen và copy", true); } };
  const addr = () => ({ type: "ssh", ssh: $("#w-ssh").value.trim(), port: $("#w-port").value || 22 });
  const showForm = info => {
    const f = $("#w-save"); f.hidden = false; $("#w-hint").hidden = true;
    f.name.value = (info?.host || addr().ssh.split("@").pop()).toLowerCase().replace(/[^a-z0-9_-]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 40) || "may-gpu";
    const gs = info?.gpus || [];
    $("#w-gpus").innerHTML = gs.length > 1 ? `<fieldset class="bare"><legend>GPU được dùng</legend><div class="opts">${gs.map(g => `<label class="opt"><input type="checkbox" name="gpu" value="${esc(g.index)}" checked><span>${ic("cpu")}#${esc(g.index)} ${esc(g.name)}<small>${gb(g.mem_total_mb)}</small></span></label>`).join("")}</div></fieldset>` : "";
    const cb = condaBase(info?.conda), envs = [["auto", "Tự động (khuyên dùng)", "Tạo .venv riêng, cài requirements.txt", info?.venv !== "no"],
      ...(cb ? [[`source ${cb}/bin/activate base && { [ ! -f requirements.txt ] || pip install -q -r requirements.txt; }`, "Dùng conda có sẵn", `${cb}, môi trường base`, info?.venv === "no"]] : []),
      ["custom", "Lệnh riêng", "Tự nhập lệnh kích hoạt môi trường", false]];
    if (!envs.some(e => e[3])) envs[0][3] = true;
    $("#w-env").innerHTML = envs.map(([v, l, d, on]) => `<label class="opt"><input type="radio" name="env" value="${esc(v)}" ${on ? "checked" : ""}><span>${l}<small>${esc(d)}</small></span></label>`).join("");
    $$("[name=env]").forEach(x => x.onchange = () => $("#w-custom").hidden = $("[name=env]:checked").value !== "custom");
  };
  $("#w-test").onclick = async () => { const a = addr(); if (!a.ssh) { $("#w-ssh").focus(); return toast("Nhập tài khoản@địa chỉ ở bước 1", true); }
    const b = $("#w-test"); b.disabled = true; $("#w-out").innerHTML = `<p class="loading"><span class="spin"></span> Đang thử đăng nhập (tối đa khoảng 10 giây)…</p>`;
    try { const r = await api("/hosts/probe", { method: "POST", json: a }); $("#w-out").innerHTML = testBanner(r);
      if (r.ok) showForm(r.info); else $("#w-out").insertAdjacentHTML("beforeend", `<button type="button" class="btn quiet sm" id="w-anyway">Vẫn lưu máy, kiểm tra lại sau</button>`);
      $("#w-anyway") && ($("#w-anyway").onclick = () => showForm(null)); } catch { $("#w-out").innerHTML = ""; } finally { b.disabled = false; } };
  $("#w-save").onsubmit = async e => { e.preventDefault(); const f = new FormData(e.target), env = f.get("env");
    const b = { ...addr(), name: f.get("name"), workdir: f.get("workdir") || "~/bonrs-runs", setup: env === "custom" ? f.get("custom") || "auto" : env, shared: f.has("shared") };
    const all = $$("[name=gpu]"), on = f.getAll("gpu"); if (all.length && on.length && on.length < all.length) b.gpus = on.join(",");
    await api("/hosts", { method: "POST", json: b }); toast("Đã lưu máy"); vHosts(app); };
  $$("[data-t]", app).forEach(x => x.onclick = async () => { const o = $("#t" + x.dataset.t); o.innerHTML = `<p class="loading"><span class="spin"></span> Đang kiểm tra…</p>`;
    const r = x.dataset.t === "local" ? await api("/hosts/probe", { method: "POST", json: { type: "local" } }) : await api(`/hosts/${x.dataset.t}/test`, { method: "POST" }); o.innerHTML = testBanner(r, x.dataset.t === "local"); });
  $$("[data-d]", app).forEach(x => x.onclick = async () => { if (confirm("Xoá máy này? Các phiên đang dùng máy này cần chọn lại máy ở tab Cấu hình.")) { await api(`/hosts/${x.dataset.d}`, { method: "DELETE" }); toast("Đã xoá"); vHosts(app); } });
}

// ---------- knowledge ----------
const TIER = { "00-general": ["Chung (mọi lĩnh vực)", "#134E4A"], "10-domain": ["Theo lĩnh vực", "#115E59"], "20-article-type": ["Theo loại bài", "#0F766E"],
  "30-journal": ["Theo tạp chí", "#0D7C72"], "40-experience": ["Kinh nghiệm tích luỹ", "#C2410C"], "50-user": ["Cá nhân", "#475569"] };
const LEVEL_VI = { general: "Chung (mọi lĩnh vực)", domain: "Theo lĩnh vực", article_type: "Theo loại bài", journal: "Theo tạp chí", experience: "Kinh nghiệm", user: "Cá nhân" };
const FM_VI = { level: "Tầng", domain: "Lĩnh vực", article_type: "Loại bài", journal: "Tạp chí", tags: "Thẻ", source: "Nguồn", source_date: "Ngày nguồn", added: "Ngày thêm",
  severity: "Mức độ", confidence: "Độ tin cậy", status: "Trạng thái", supersedes: "Thay thế", user_id: "Người dùng", submitted_by: "Người gửi" };
async function vKB(app, sub = "browse", tierSel) {
  const isA = ME.role === "admin";
  const [idx, drafts] = await Promise.all([api("/kb"), api("/kb/drafts")]);
  const groups = {}; idx.forEach(s => (groups[s.tier || "khác"] ||= []).push(s));
  app.innerHTML = `<div class="wrap">${head("Kho tri thức", "Quy tắc, kỹ năng viết và kinh nghiệm agent nạp vào mỗi phiên, xếp từ chung đến cụ thể.")}
    <nav class="tabs">${[["browse", "Duyệt & sửa", "library-big"], ["add", "Đóng góp tài liệu", "upload"], ["drafts", "Chờ duyệt", "inbox"], ["sources", "Nguồn tự động", "rss"]]
      .map(([k, v, i]) => `<a href="#/kb/${k}" class="${k === sub ? "on" : ""}" ${k === sub ? 'aria-current="page"' : ""}>${ic(i, "sm")}${v}${k === "drafts" && drafts.length ? `<span class="count">${drafts.length}</span>` : ""}</a>`).join("")}</nav><div id="kb"></div></div>`;
  const el = $("#kb");
  if (sub === "browse") {
    const tiers = Object.keys(TIER);
    el.innerHTML = `<div class="split"><aside class="stack" aria-label="Lọc theo tầng"><section class="card"><h2>${ic("layers")} Các tầng</h2><p class="muted small">Agent nạp từ trên xuống; tầng dưới cụ thể hơn và được ưu tiên khi mâu thuẫn. Bấm để lọc.</p>
        <div class="layers">${tiers.map((t, i) => `<button class="layer ${tierSel === t ? "on" : ""}" data-t="${t}" aria-pressed="${tierSel === t}" style="width:${100 - i * 7}%;background:${TIER[t][1]}">${TIER[t][0]}<b>${(groups[t] || []).length}</b></button>`).join("")}</div></section>
      <section class="card tree"><input id="q" type="search" placeholder="Tìm theo tên hoặc tag…" aria-label="Tìm skill" style="margin:0 0 .5rem">
        ${tiers.filter(t => !tierSel || t === tierSel).map(t => `<details open><summary><span style="width:10px;height:10px;border-radius:3px;background:${TIER[t][1]};display:inline-block"></span>${TIER[t][0]}<span class="n">${(groups[t] || []).length}</span></summary>
          ${(groups[t] || []).map(s => `<a href="#" data-p="${esc(s.path)}" data-k="${esc((s.name + " " + [].concat(s.tags || []).join(" ")).toLowerCase())}">${ic("file-text", "sm")}<span>${esc(s.name || s.path)}</span>${s.status !== "active" ? pill("waiting", s.status) : ""}</a>`).join("") || '<p class="muted small" style="padding-left:1.6rem">Trống</p>'}</details>`).join("")}
        <button class="btn ghost sm" id="newp" style="width:100%;margin-top:.5rem">${ic("plus", "sm")} Skill cá nhân mới</button></section></aside>
      <section class="card viewer" id="v"><div class="empty"><span class="big">${ic("book-open", "lg")}</span><h2>Chọn một skill để xem</h2>
        <p>${isA ? "Bạn là quản trị viên: sửa được mọi skill." : `Bạn sửa được skill cá nhân (50-user/${ME.id}/). Skill chung do quản trị viên duyệt.`}</p></div></section></div>`;
    $$("[data-t]", el).forEach(b => b.onclick = () => vKB(app, "browse", tierSel === b.dataset.t ? undefined : b.dataset.t));
    $("#q").oninput = e => $$("[data-k]", el).forEach(a => a.style.display = a.dataset.k.includes(e.target.value.toLowerCase()) ? "" : "none");
    const open = async p => { $$("[data-p]", el).forEach(a => a.classList.toggle("on", a.dataset.p === p));
      const t = await api(`/kb/file?path=${encodeURIComponent(p)}`); const can = isA || p.startsWith(`50-user/${ME.id}/`);
      const m = t.match(/^---\n([\s\S]*?)\n---\n?/), meta = m ? Object.fromEntries(m[1].split("\n").map(l => l.split(/:\s*/)).filter(x => x[0] && x[1] && !/^\s/.test(x[0])).map(([k, ...v]) => [k, v.join(": ")])) : {};
      $("#v").innerHTML = `<div class="vhead"><span class="path">${ic("file-text", "sm")}${esc(p)}</span><div class="actions">${can ? `<button class="btn ghost sm" id="e">${ic("pencil", "sm")} Sửa</button>` : ""}
        ${p.startsWith("50-user/") ? `<button class="btn ghost sm" id="pp">${ic("share", "sm")} Đề xuất vào kho chung</button>` : ""}</div></div>
        <div class="fm">${Object.entries(meta).filter(([k]) => k !== "name").map(([k, v]) => `<span class="chip"><span class="muted">${esc(FM_VI[k] || k)}</span> ${esc(v)}</span>`).join("")}</div>
        <div id="b" class="prose">${md(m ? t.slice(m[0].length) : t)}</div>`;
      if (can) $("#e").onclick = () => { $("#b").outerHTML = `<div id="b"><textarea class="code" id="ta" spellcheck="false">${esc(t)}</textarea><div class="actions" style="margin-top:.6rem"><button class="btn" id="s">${ic("save", "sm")} Lưu</button><button class="btn ghost" id="cx">Huỷ</button></div></div>`;
        $("#cx").onclick = () => open(p); $("#s").onclick = async () => { await api(`/kb/file?path=${encodeURIComponent(p)}`, { method: "PUT", body: $("#ta").value }); toast("Đã lưu"); open(p); }; };
      if ($("#pp")) $("#pp").onclick = async () => { await api("/kb/promote", { method: "POST", json: { path: p } }); toast("Đã gửi quản trị viên duyệt"); }; };
    $$("[data-p]", el).forEach(a => a.onclick = e => { e.preventDefault(); open(a.dataset.p); });
    $("#newp").onclick = () => dialog(`<h2>${ic("plus")} Skill cá nhân mới</h2><label>Tên skill<input name="n" required pattern="[a-z0-9\\-]+" placeholder="vd. my-discussion-style"><span class="hint">Chữ thường, số, gạch ngang.</span></label>
      <div class="dfoot"><button type="button" class="btn ghost" data-close>Huỷ</button><button class="btn">Tạo</button></div>`, async f => { const n = f.get("n"), p = `50-user/${ME.id}/${n}.md`;
      await api(`/kb/file?path=${encodeURIComponent(p)}`, { method: "PUT", body: `---\nname: ${n}\nlevel: user\nuser_id: "${ME.id}"\nstatus: active\n---\n# ${n}\n- \n` }); vKB(app, "browse", "50-user"); });
  } else if (sub === "add") {
    el.innerHTML = `<div class="cols side-r"><section class="card"><h2>${ic("upload")} Đóng góp tài liệu</h2>
      <p class="muted">Bài viết, hướng dẫn, kinh nghiệm viết báo, guideline tạp chí… Agent đọc, chuẩn hoá thành skill markdown và đưa vào hàng chờ duyệt.</p>
      <form id="f"><div class="drop" id="drop">${ic("cloud-upload", "lg")}<div>Kéo thả PDF, DOCX, MD, HTML vào đây hoặc chọn tệp</div><input type="file" name="files" multiple aria-label="Chọn tệp"></div>
      <label style="margin-top:1rem">Hoặc dán đường dẫn<input name="url" type="url" placeholder="https://…"></label>
      <label>Gợi ý cho agent (tuỳ chọn)<input name="hint" placeholder="Lĩnh vực, tạp chí, loại bài…"></label><button class="btn">${ic("send", "sm")} Gửi</button></form></section>
      <aside class="card"><h2>${ic("workflow")} Điều gì xảy ra tiếp theo</h2><ol class="steps"><li>Agent trích nội dung và so với các skill đã có.</li><li>Tạo 1 hoặc vài skill nháp có nguồn và độ tin cậy.</li>
        <li>Quản trị viên đọc, sửa, duyệt hoặc từ chối ở mục <b>Chờ duyệt</b>.</li><li>Skill đã duyệt được nạp vào các phiên phù hợp.</li></ol></aside></div>`;
    dropZone($("#drop"));
    $("#f").onsubmit = async e => { e.preventDefault(); const f = new FormData(e.target); if (!f.get("url") && !f.get("files")?.size) return toast("Chọn tệp hoặc nhập đường dẫn", true);
      if (!f.get("files")?.size) f.delete("files"); const r = await api("/kb/ingest", { method: "POST", body: f }); toast(`Đã gửi, agent đang chuyển thành ${r.jobs.length} skill nháp`); e.target.reset(); };
  } else if (sub === "drafts") {
    el.innerHTML = drafts.length ? `<div class="stack">${drafts.map(d => `<article class="card"><div class="card-head"><div><h2 style="margin:0">${esc(d.name)}</h2>
        <span class="muted small">${esc(d.source || "")}${d.submitted_by ? " · " + esc(d.submitted_by) : ""}${d.origin ? " · " + esc(d.origin) : ""}</span>
        <div class="small" style="margin-top:.3rem">${d.target ? `${ic("folder-input", "sm")} Sẽ ghi vào <code>${esc(d.target)}</code>` : pill("failed", "Đường dẫn đích không hợp lệ: hãy từ chối")}</div></div><div class="chips">${pill("suggest", d.level)}
        ${d.confidence != null ? `<span class="chip">tin cậy ${esc(d.confidence)}</span>` : ""}</div></div><div class="prose">${md(d.body)}</div>
      ${isA ? `<details style="margin:.8rem 0"><summary class="muted small" style="cursor:pointer;font-weight:600">Sửa trước khi duyệt</summary><textarea class="code" data-b="${esc(d.file)}" style="min-height:30vh">${esc(d.body)}</textarea></details>
        <div class="actions"><button class="btn" data-a="${esc(d.file)}">${ic("check", "sm")} Duyệt vào kho</button><button class="btn danger" data-r="${esc(d.file)}">${ic("x", "sm")} Từ chối</button></div>` : '<p class="muted small">Chờ quản trị viên duyệt.</p>'}</article>`).join("")}</div>`
      : `<div class="empty card"><span class="big">${ic("inbox", "lg")}</span><h2>Không có skill nào chờ duyệt</h2><p>Skill nháp xuất hiện ở đây sau khi có người đóng góp tài liệu hoặc hệ thống cào được nguồn mới.</p></div>`;
    $$("[data-a]", el).forEach(b => b.onclick = async () => { const ta = el.querySelector(`[data-b="${CSS.escape(b.dataset.a)}"]`);
      const r = await api(`/kb/drafts/${encodeURIComponent(b.dataset.a)}/approve`, { method: "POST", json: { body: ta?.value } }); toast("Đã thêm: " + r.path); vKB(app, "drafts"); });
    $$("[data-r]", el).forEach(b => b.onclick = () => dialog(`<h2>Từ chối skill</h2><label>Lý do<textarea name="reason" rows="3"></textarea></label><div class="dfoot"><button type="button" class="btn ghost" data-close>Huỷ</button><button class="btn danger">Từ chối</button></div>`,
      async f => { await api(`/kb/drafts/${encodeURIComponent(b.dataset.r)}/reject`, { method: "POST", json: { reason: f.get("reason") } }); vKB(app, "drafts"); }));
  } else {
    const d = await api("/kb/sources"), list = d.sources.map(x => ({ ...x }));
    const save = async () => { await api("/kb/sources", { method: "PUT", json: { sources: list } }); toast("Đã lưu"); vKB(app, "sources"); };
    const state = x => { const s = d.state[x.url]; if (x.enabled === false) return pill("", "Đã tắt"); if (!s) return pill("queued", "Chưa cập nhật");
      return s.error ? pill("failed", "Lỗi lần trước") : pill("done", "Đã đọc " + ago(s.at)); };
    const every = [[0, "Tắt"], [24, "Mỗi ngày"], [168, "Mỗi tuần"], [720, "Mỗi tháng"]];
    if (!every.some(([h]) => h === d.every_hours)) every.push([d.every_hours, `Mỗi ${d.every_hours} giờ`]);
    el.innerHTML = `<div class="cols side-r"><section class="card"><div class="card-head"><h2>${ic("rss")} Nguồn tự động (${list.length})</h2>
        ${isA ? `<button class="btn ghost sm" id="all">${ic("refresh-cw", "sm")} Cập nhật tất cả ngay</button>` : ""}</div>
      <div class="tblwrap"><table class="tbl"><thead><tr><th>Nguồn</th><th>Đưa vào tầng</th><th>Trạng thái</th>${isA ? '<th>Bật</th><th><span class="sr">Thao tác</span></th>' : ""}</tr></thead><tbody>
        ${list.map((x, i) => `<tr><td><a href="${esc(safeUrl(x.url))}" target="_blank" rel="noopener noreferrer">${esc(x.name)}</a><div class="muted small">${esc((() => { try { return new URL(x.url).host; } catch { return x.url; } })())}</div></td>
          <td>${esc(LEVEL_VI[x.level] || x.level || "Chung")}${x.domain ? ` · ${esc(DOMAIN_VI[x.domain] || x.domain)}` : ""}</td><td>${state(x)}</td>
          ${isA ? `<td><label class="switch"><input type="checkbox" data-en="${i}" ${x.enabled === false ? "" : "checked"} aria-label="Bật ${esc(x.name)}"></label></td>
          <td class="nowrap" style="text-align:right"><button class="btn sm quiet" data-one="${i}" title="Đọc nguồn này ngay" aria-label="Đọc ${esc(x.name)} ngay">${ic("refresh-cw", "sm")}</button><button class="btn sm danger" data-del="${i}" aria-label="Xoá ${esc(x.name)}">${ic("trash-2", "sm")}</button></td>` : ""}</tr>`).join("")
          || `<tr><td colspan="5" class="muted">Chưa có nguồn nào.</td></tr>`}</tbody></table></div>
      ${isA ? `<h3 style="margin:1.2rem 0 .5rem">${ic("plus", "sm")} Thêm nguồn</h3><form id="add"><div class="grid2"><label>Tên nguồn<input name="name" required placeholder="vd. Hướng dẫn tác giả của Elsevier"></label>
          <label>Đường dẫn trang<input name="url" type="url" required placeholder="https://…"></label>
          <label>Đưa vào tầng<select name="level">${Object.entries(LEVEL_VI).filter(([k]) => k !== "user").map(([k, v]) => `<option value="${k}">${v}</option>`).join("")}</select></label>
          <label>Lĩnh vực<select name="domain"><option value="">Mọi lĩnh vực</option>${Object.entries(DOMAIN_VI).filter(([k]) => k !== "other").map(([k, v]) => `<option value="${k}">${v}</option>`).join("")}</select></label></div>
        <button class="btn">${ic("plus", "sm")} Thêm nguồn</button></form>` : ""}</section>
      <aside class="stack"><section class="card"><h2>${ic("calendar-clock")} Lịch tự cập nhật</h2>
        ${d.has_key ? "" : `<p class="banner req small" style="padding:.6rem .8rem">${ic("key", "sm")} Cần Anthropic API key chung (Quản trị → Khoá API) thì lịch mới chạy.</p>`}
        ${isA ? `<form id="sched"><label>Tự đọc lại các nguồn<select name="crawl_every_hours">${every.map(([h, l]) => `<option value="${h}" ${h === d.every_hours ? "selected" : ""}>${l}</option>`).join("")}</select></label>
          <label>Skill mới từ nguồn tự động<select name="auto_approve_confidence">${[["", "Luôn chờ quản trị viên duyệt"], ["0.8", "Tự duyệt khi agent tin cậy ≥ 0,8"], ["0.9", "Tự duyệt khi agent tin cậy ≥ 0,9"]]
            .map(([v, l]) => `<option value="${v}" ${String(d.auto_approve ?? "") === v ? "selected" : ""}>${l}</option>`).join("")}</select></label><button class="btn sm">${ic("save", "sm")} Lưu lịch</button></form>`
          : `<p>${(every.find(([h]) => h === d.every_hours) || [0, "Tắt"])[1]}</p>`}
        <p class="muted small" style="margin:.6rem 0 0">Lần gần nhất: ${d.last ? ago(d.last) : "chưa"}${d.next ? ` · Lần tới: ${esc(fmtTs(d.next))}` : ""}</p></section>
      <section class="card"><h2>${ic("workflow")} Hoạt động thế nào</h2><ol class="steps"><li>Đến lịch, hệ thống mở từng nguồn đang bật.</li><li>Trang không đổi so với lần trước thì bỏ qua, không tốn phí.</li>
        <li>Trang mới hoặc đã đổi được agent chuẩn hoá thành skill nháp, so với skill đã có để không trùng.</li><li>Skill nháp nằm ở <a href="#/kb/drafts">Chờ duyệt</a>; chỉ skill đã duyệt mới được nạp vào phiên.</li></ol>
        <p class="muted small">Nên chọn trang hướng dẫn viết bài, hướng dẫn tác giả của tạp chí, trang về phương pháp. Thành viên muốn thêm nguồn thì gửi tài liệu ở mục Đóng góp tài liệu.</p></section></aside></div>`;
    if (isA) {
      $("#all").onclick = async () => { const r = await api("/kb/crawl", { method: "POST" }); toast(`Đã xếp ${r.jobs.length} nguồn vào hàng đợi`); };
      $$("[data-one]", el).forEach(b => b.onclick = async () => { const r = await api("/kb/crawl", { method: "POST", json: { url: list[b.dataset.one].url } }); toast(r.jobs.length ? "Đã xếp vào hàng đợi" : "Nguồn đang tắt", !r.jobs.length); });
      $$("[data-en]", el).forEach(b => b.onchange = () => { const x = list[b.dataset.en]; if (b.checked) delete x.enabled; else x.enabled = false; save(); });
      $$("[data-del]", el).forEach(b => b.onclick = () => { if (confirm(`Xoá nguồn “${list[b.dataset.del].name}”?`)) { list.splice(+b.dataset.del, 1); save(); } });
      $("#add").onsubmit = e => { e.preventDefault(); const f = Object.fromEntries(new FormData(e.target)); if (!f.domain) delete f.domain; list.push(f); save(); };
      $("#sched").onsubmit = async e => { e.preventDefault(); await api("/admin/settings", { method: "PUT", json: Object.fromEntries(new FormData(e.target)) }); toast("Đã lưu lịch"); vKB(app, "sources"); };
    }
  }
}

// ---------- admin / me ----------
const ADMIN_TABS = [["users", "Người dùng", "users"], ["keys", "Khoá API & nguồn dữ liệu", "key-round"], ["ops", "Vận hành", "gauge"], ["jobs", "Hàng đợi việc", "list-todo"]];
const JOB_KIND_VI = { run: "Chạy phiên", ingest: "Chuẩn hoá tài liệu", crawl: "Cập nhật nguồn" };
async function vAdmin(app, sub = "users") {
  if (!ADMIN_TABS.some(([k]) => k === sub)) sub = "users";
  const [users, st, jobs] = await Promise.all([api("/admin/users"), api("/admin/settings"), api("/admin/jobs")]);
  const counts = jobs.reduce((a, j) => (a[j.status] = (a[j.status] || 0) + 1, a), {});
  const D = st._defaults || {};
  const field = ([k, l, ph, type, hint]) => `<label>${l}<input name="${k}" type="${type || "text"}" value="${esc(st[k] ?? D[k] ?? "")}" placeholder="${esc(ph || "")}" autocomplete="off" ${type === "number" ? 'step="any"' : ""} ${k === "default_model" ? 'list="models"' : ""}>${hint || D[k] != null ? `<span class="hint">${hint || ""}${D[k] != null ? `${hint ? " " : ""}Mặc định: ${esc(D[k])}.` : ""}</span>` : ""}</label>`;
  const form = groups => `<form id="s" class="cols">${groups.map(([t, i, fs, note]) => `<section class="card"><h2>${ic(i)} ${t}</h2>${note ? `<p class="muted small">${note}</p>` : ""}${fs.map(field).join("")}</section>`).join("")}
    <div style="grid-column:1/-1"><button class="btn">${ic("save", "sm")} Lưu cài đặt</button></div></form>`;
  const body = {
    users: () => `<div class="cols side-r"><section class="card"><h2>${ic("users")} Người dùng (${users.length})</h2><div class="tblwrap"><table class="tbl"><thead><tr><th>Email</th><th>Vai trò</th><th><span class="sr">Thao tác</span></th></tr></thead><tbody>
      ${users.map(u => `<tr><td>${esc(u.email)}</td><td>${pill(u.role === "admin" ? "suggest" : "", u.role === "admin" ? "Quản trị" : "Thành viên")}</td><td style="text-align:right;white-space:nowrap">
        <button class="btn sm ghost" data-pw="${u.id}" data-e="${esc(u.email)}">${ic("key-round", "sm")} Đặt lại mật khẩu</button>
        ${u.id !== ME.id ? `<button class="btn sm danger" data-d="${u.id}" aria-label="Vô hiệu hoá ${esc(u.email)}">${ic("user-x", "sm")}</button>` : ""}</td></tr>`).join("")}</tbody></table></div></section>
      <section class="card"><h2>${ic("user-plus")} Thêm người dùng</h2><form id="u"><label>Email<input name="email" type="email" required></label>
        <label>Mật khẩu tạm<input name="password" required minlength="8" autocomplete="new-password"><span class="hint">Ít nhất 8 ký tự. Người dùng tự đổi ở trang Tài khoản.</span></label>
        <label>Vai trò<select name="role"><option value="member">Thành viên</option><option value="admin">Quản trị</option></select></label><button class="btn">${ic("user-plus", "sm")} Thêm</button></form>
        <p class="muted small" style="margin-top:1rem">Vô hiệu hoá một người dùng sẽ đăng xuất họ ở mọi nơi và dừng các việc đang chạy; phiên của họ vẫn được giữ để bạn xem lại.</p></section></div>`,
    keys: () => form([["Key chung của server (Anthropic API)", "bot", [["anthropic_api_key", "Anthropic API key", "sk-ant-api…", "password", "Lấy ở console.anthropic.com → API Keys. Agent không bao giờ nhìn thấy key: server tự gắn key khi chuyển tiếp yêu cầu."]],
        "Dùng cho thành viên chưa có kết nối riêng và cho việc tự cập nhật kho tri thức. Mỗi người cũng có thể dùng gói Claude Pro/Max của chính mình ở trang <a href=\"#/me\">Tài khoản</a>: khi đó phiên của họ không tính vào key chung. Không nhập mã gói Pro/Max của bạn vào đây: gói là cá nhân, không được dùng chung."],
      ["Nguồn dữ liệu học thuật", "database", [["openalex_api_key", "OpenAlex API key", "", "password"], ["s2_api_key", "Semantic Scholar API key", "", "password"], ["contact_email", "Email liên hệ Crossref/Unpaywall", "you@lab.org"]]]]),
    ops: () => { const v = k => st[k] ?? D[k], isDef = k => st[k] == null || String(st[k]) === String(D[k]);
      const tag = k => isDef(k) ? `<span class="chip sm">mặc định</span>` : `<span class="chip sm warn">đã đổi</span>`;
      return `<form id="ops"><div class="cols">
      <section class="card"><div class="card-head"><h2>${ic("sliders-horizontal")} Mặc định cho phiên mới</h2></div><p class="muted small">Mỗi người tạo phiên vẫn đổi được cho phiên của mình.</p>
        <label><span class="lblrow">Model ${tag("default_model")}</span>${modelSel("default_model", v("default_model"))}</label>
        ${budgetField("max_budget_usd", v("max_budget_usd"), tag("max_budget_usd"))}
        <fieldset class="bare"><legend><span class="lblrow">Khi agent dừng ở cổng duyệt ${tag("default_gate_timeout_hours")}</span></legend>${waitCtl("default_gate_timeout_hours", v("default_gate_timeout_hours"))}</fieldset></section>
      <section class="card"><div class="card-head"><h2>${ic("gauge")} Hàng đợi</h2></div><p class="muted small">Mỗi người dùng không chiếm hết các suất khi người khác đang chờ.</p>
        <label><span class="lblrow">Số phiên chạy cùng lúc ${tag("max_parallel_jobs")}</span><select name="max_parallel_jobs">${[1, 2, 3, 4, 6, 8].map(n => `<option value="${n}" ${+v("max_parallel_jobs") === n ? "selected" : ""}>${n} phiên${n === 2 ? " (khuyên dùng cho server 8–16 GB RAM)" : ""}</option>`).join("")}</select></label>
        ${hmCtl("job_timeout_hours", v("job_timeout_hours"), "Mỗi lượt chạy tối đa", tag("job_timeout_hours"))}
        <p class="hint">Quá thời gian này lượt chạy bị dừng; bấm Tiếp tục để chạy tiếp từ bước dở dang.</p></section></div>
      <div class="savebar"><button class="btn">${ic("save", "sm")} Lưu thay đổi</button><button type="button" class="btn ghost" id="reset">${ic("rotate-ccw", "sm")} Đưa tất cả về mặc định</button></div></form>
      <a class="card linkcard" href="#/kb/sources"><span class="hicon">${ic("calendar-clock")}</span><span><b>Lịch tự cập nhật kho tri thức</b><small>Bật/tắt, chọn chu kỳ và nguồn ở Kho tri thức → Nguồn tự động</small></span>${ic("chevron-right")}</a>`; },
    jobs: () => `<section class="card"><div class="card-head"><h2>${ic("list-todo")} Việc gần đây</h2><div class="filter" role="group" aria-label="Lọc việc">${["all", "running", "queued", "failed"].map(f => `<button data-jf="${f}" class="${f === "all" ? "on" : ""}">${{ all: "Tất cả", running: "Đang chạy", queued: "Đang chờ", failed: "Lỗi" }[f]}</button>`).join("")}</div></div>
      <div class="tblwrap"><table class="tbl"><thead><tr><th>#</th><th>Loại</th><th>Người dùng</th><th>Phiên</th><th>Trạng thái</th><th>Lúc</th></tr></thead><tbody id="jt"></tbody></table></div></section>`,
  }[sub]();
  app.innerHTML = `<div class="wrap">${head("Quản trị", "Người dùng, khoá API, vận hành và hàng đợi việc của toàn server.")}
    <div class="kpis"><div class="kpi"><span class="kic">${ic("users")}</span><span><b>${users.length}</b><small>Người dùng</small></span></div>
      <div class="kpi"><span class="kic b">${ic("activity")}</span><span><b>${(counts.running || 0) + (counts.queued || 0)}</b><small>Việc đang chạy / chờ</small></span></div>
      <div class="kpi"><span class="kic w">${ic("circle-alert")}</span><span><b>${(counts.failed || 0) + (counts.interrupted || 0)}</b><small>Việc lỗi / bị ngắt</small></span></div>
      <div class="kpi ${st.anthropic_api_key ? "" : "warnbox"}"><span class="kic ${st.anthropic_api_key ? "" : "w"}">${ic(st.anthropic_api_key ? "key-round" : "key")}</span><span><b>${st.anthropic_api_key ? "Đã có" : "Chưa có"}</b><small>${st.anthropic_api_key ? "Key chung Anthropic" : "Key chung: cần cho người chưa có kết nối riêng"}</small></span></div></div>
    <nav class="tabs">${ADMIN_TABS.map(([k, v, i]) => `<a href="#/admin/${k}" class="${k === sub ? "on" : ""}" ${k === sub ? 'aria-current="page"' : ""}>${ic(i, "sm")}${v}</a>`).join("")}</nav>${body}</div>`;
  if ($("#s")) $("#s").onsubmit = async e => { e.preventDefault(); const b = Object.fromEntries([...new FormData(e.target)].filter(([, v]) => !String(v).startsWith("••••"))); await api("/admin/settings", { method: "PUT", json: b }); toast("Đã lưu cài đặt"); vAdmin(app, sub); };
  if ($("#reset")) $("#reset").onclick = async () => { if (!confirm("Đưa các cài đặt vận hành về mặc định?")) return;
    await api("/admin/settings", { method: "PUT", json: { default_model: "", max_budget_usd: "", max_parallel_jobs: "", job_timeout_hours: "", default_gate_timeout_hours: "" } }); toast("Đã khôi phục mặc định"); vAdmin(app, sub); };
  if ($("#ops")) { const o = $("#ops"); bindWait(o); budgetHint(o, false); $("[data-model]", o).onchange = () => budgetHint(o, false);
    o.onsubmit = async e => { e.preventDefault(); const f = new FormData(o);
      await api("/admin/settings", { method: "PUT", json: { default_model: f.get("default_model"), max_budget_usd: f.get("max_budget_usd"), max_parallel_jobs: f.get("max_parallel_jobs"),
        job_timeout_hours: Math.max(0.1, readHM(f, "job_timeout_hours")), default_gate_timeout_hours: readWait(f, "default_gate_timeout_hours") } }); toast("Đã lưu"); vAdmin(app, sub); }; }
  if ($("#u")) $("#u").onsubmit = async e => { e.preventDefault(); await api("/admin/users", { method: "POST", json: Object.fromEntries(new FormData(e.target)) }); toast("Đã thêm người dùng"); vAdmin(app, sub); };
  $$("[data-d]", app).forEach(a => a.onclick = async () => { if (confirm("Vô hiệu hoá người dùng này? Họ bị đăng xuất và các việc đang chạy dừng lại.")) { await api(`/admin/users/${a.dataset.d}`, { method: "DELETE" }); vAdmin(app, sub); } });
  $$("[data-pw]", app).forEach(a => a.onclick = () => dialog(`<h2>${ic("key-round")} Đặt lại mật khẩu</h2><p class="muted">${esc(a.dataset.e)} sẽ bị đăng xuất ở mọi thiết bị.</p>
    <label>Mật khẩu mới<input name="password" required minlength="8" autocomplete="new-password"></label><div class="dfoot"><button type="button" class="btn ghost" data-close>Huỷ</button><button class="btn">Đặt lại</button></div>`,
    async f => { await api(`/admin/users/${a.dataset.pw}/password`, { method: "PUT", json: { password: f.get("password") } }); toast("Đã đặt lại mật khẩu"); }));
  if ($("#jt")) { const draw = f => { $("#jt").innerHTML = jobs.filter(j => f === "all" || j.status === f || (f === "failed" && j.status === "interrupted")).slice(0, 100).map(j => `<tr><td class="muted">${j.id}</td><td>${esc(JOB_KIND_VI[j.kind] || j.kind)}</td><td>${esc((j.email || (j.owner ? "#" + j.owner : "hệ thống")).split("@")[0])}</td>
      <td>${j.slug ? `<a href="#/run/${esc(j.slug)}">${esc(j.slug.slice(0, 28))}</a>` : "—"}</td><td>${pill(j.status)}</td><td class="muted nowrap">${ago(j.created)}</td></tr>`).join("") || `<tr><td colspan="6" class="muted">Không có việc nào</td></tr>`;
      $$("[data-jf]", app).forEach(b => b.classList.toggle("on", b.dataset.jf === f)); };
    $$("[data-jf]", app).forEach(b => b.onclick = () => draw(b.dataset.jf)); draw("all"); }
}

function vMe(app) {
  const mode = ME.has_oauth ? "oauth" : ME.has_key ? "key" : "shared";
  const MODE = { oauth: ["Gói Claude Pro/Max của tôi", "badge-check"], key: ["API key của tôi", "key-round"], shared: ["Key chung của server", "users"] };
  app.innerHTML = `<div class="wrap" style="max-width:760px">${head("Tài khoản")}
    <section class="card"><div style="display:flex;gap:1rem;align-items:center;flex-wrap:wrap"><span class="avatar" style="width:56px;height:56px;font-size:1.4rem">${esc(ME.email[0].toUpperCase())}</span>
      <div><h2 style="margin:0">${esc(ME.email)}</h2><span class="muted">${ME.role === "admin" ? "Quản trị viên" : "Thành viên"}</span></div>
      <button class="btn ghost" id="lo" style="margin-left:auto">${ic("log-out", "sm")} Đăng xuất mọi nơi</button></div></section>
    <section class="card"><h2>${ic("bot")} Kết nối Claude</h2><p>Phiên của bạn đang dùng: <b>${MODE[mode][0]}</b></p>
      <div class="seg" role="radiogroup" aria-label="Cách kết nối Claude">${Object.entries(MODE).map(([k, [l, i]]) => `<label><input type="radio" name="cm" value="${k}" ${k === mode ? "checked" : ""}><span>${ic(i, "sm")}${l}</span></label>`).join("")}</div>
      <div data-p="oauth" style="margin-top:1rem"><p class="muted small">Dùng hạn mức gói Claude Pro hoặc Max bạn đang trả hằng tháng, không tính tiền theo lượt.</p>
        <ol class="steps"><li>Trên máy tính của bạn, cài Claude Code nếu chưa có: <code>npm install -g @anthropic-ai/claude-code</code>.</li><li>Mở Terminal, chạy <code>claude setup-token</code>, đăng nhập bằng tài khoản Claude của bạn trong trình duyệt.</li>
          <li>Terminal in ra một mã bắt đầu bằng <code>sk-ant-oat</code>. Dán mã đó vào ô dưới rồi bấm Lưu.</li></ol>
        <form id="oa" class="actions"><input name="token" type="password" placeholder="sk-ant-oat01-…" style="flex:1;margin:0" aria-label="Mã từ claude setup-token" autocomplete="off"><button class="btn">${ic("save", "sm")} Lưu</button></form>
        <p class="muted small" style="margin-top:.6rem">Mã chỉ dùng cho phiên của bạn, nằm trong vùng chạy riêng của bạn trên server. Đừng đưa mã cho người khác hoặc nhập vào chỗ dùng chung: gói Claude là cá nhân, điều khoản của Anthropic không cho dùng chung. Mã có hạn khoảng 1 năm; hết hạn thì chạy lại lệnh trên. Lượng dùng tính vào hạn mức 5 giờ/tuần của gói, nên phiên dài có thể phải chờ hạn mức hồi lại.</p></div>
      <div data-p="key" style="margin-top:1rem"><p class="muted small">Trả theo lượng dùng bằng API key của bạn (lấy ở console.anthropic.com → API Keys). Agent không đọc được key: server tự gắn key khi gửi yêu cầu.</p>
        <form id="k" class="actions"><input name="api_key" type="password" placeholder="sk-ant-api03-…" style="flex:1;margin:0" aria-label="API key" autocomplete="off"><button class="btn">${ic("save", "sm")} Lưu</button></form></div>
      <div data-p="shared" style="margin-top:1rem"><p class="muted small">Không cần làm gì: chi phí tính vào key chung do quản trị viên quản lý.</p>
        ${mode !== "shared" ? `<button class="btn ghost" id="sh">${ic("users", "sm")} Chuyển về key chung</button>` : ""}</div></section>
    <section class="card"><h2>${ic("palette")} Giao diện</h2><p class="muted small">Ngôn ngữ và chế độ sáng/tối được lưu trên trình duyệt này.</p>${prefsHtml()}</section>
    <section class="card"><h2>${ic("lock")} Đổi mật khẩu</h2><form id="pw"><input type="email" name="username" value="${esc(ME.email)}" autocomplete="username" hidden>
      <label>Mật khẩu hiện tại<input name="old" type="password" required autocomplete="current-password"></label>
      <label>Mật khẩu mới<input name="new" type="password" required minlength="8" autocomplete="new-password"><span class="hint">Ít nhất 8 ký tự. Các thiết bị khác sẽ bị đăng xuất.</span></label>
      <button class="btn">${ic("save", "sm")} Đổi mật khẩu</button></form></section></div>`;
  const show = () => { const m = $("[name=cm]:checked").value; $$("[data-p]", app).forEach(d => d.hidden = d.dataset.p !== m); };
  $$("[name=cm]", app).forEach(x => x.onchange = show); show();
  const setMode = async (token, key) => { await api("/me/oauth", { method: "PUT", json: { token } }); await api("/me/key", { method: "PUT", json: { api_key: key } }); ME = null; await route(); };
  $("#oa").onsubmit = async e => { e.preventDefault(); const t = new FormData(e.target).get("token").trim(); if (!t) return; await setMode(t, ""); toast("Phiên của bạn sẽ dùng gói Claude của bạn"); };
  $("#k").onsubmit = async e => { e.preventDefault(); const k = new FormData(e.target).get("api_key").trim(); if (!k) return; await setMode("", k); toast("Phiên của bạn sẽ dùng API key của bạn"); };
  $("#sh") && ($("#sh").onclick = async () => { await setMode("", ""); toast("Đã chuyển về key chung"); });
  $("#pw").onsubmit = async e => { e.preventDefault(); const f = new FormData(e.target); await api("/me/password", { method: "PUT", json: { old: f.get("old"), new: f.get("new") } }); toast("Đã đổi mật khẩu"); e.target.reset(); };
  $("#lo").onclick = async () => { await api("/logout", { method: "POST" }); ME = null; RUNS_CACHE = []; location.hash = "#/login"; };
}
