"use strict";
// English mode. The UI is written in Vietnamese; i18n-en.js maps every UI phrase to English. Text nodes, a few attributes,
// confirm() and the page title are translated as they appear. Text written by people or the agent is left alone: a node is
// changed only if it consists entirely of known UI phrases plus numbers, symbols or ASCII names (emails, file names).
const LANG = document.documentElement.lang === "en" ? "en" : "vi";
const LOCALE = LANG === "en" ? "en-GB" : "vi-VN";
let T = s => s;
(() => {
  if (LANG !== "en" || !window.I18N_EN) return;
  const VI = /[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ]/i;
  const dict = new Map(Object.entries(window.I18N_EN));
  // a phrase that starts or ends with a letter must not touch other letters (so "ở" never matches inside "mở")
  const esc = k => (/^[\p{L}\p{N}]/u.test(k) ? "(?<![\\p{L}\\p{N}])" : "") + k.replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace(/ /g, "\\s+") + (/\p{L}$/u.test(k) ? "(?![\\p{L}])" : "");
  const re = new RegExp([...dict.keys()].sort((a, b) => b.length - a.length).map(esc).join("|"), "gu");
  T = s => {
    if (!s || !VI.test(s)) return s;
    const core = s.replace(/\s+/g, " ").trim();  // whitespace around and inside (line breaks) is kept as written
    if (dict.has(core)) return s.match(/^\s*/)[0] + dict.get(core) + s.match(/\s*$/)[0];
    const out = s.replace(re, m => dict.get(m.replace(/\s+/g, " ")) ?? m);
    return VI.test(out) ? s : out; // leftover Vietnamese: someone's own text, keep it as written
  };
  const SKIP = "textarea, pre, code, .prose, .bub, .say, script, style, [data-raw]";
  const ATTRS = ["placeholder", "title", "aria-label"];
  const fix = root => {
    if (root.nodeType === 3) { const p = root.parentElement; if (p && !p.closest(SKIP)) { const v = T(root.nodeValue); if (v !== root.nodeValue) root.nodeValue = v; } return; }
    if (root.nodeType !== 1 || root.closest?.(SKIP)) return;
    const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    for (let t; (t = w.nextNode());) { if (t.parentElement?.closest(SKIP)) continue; const v = T(t.nodeValue); if (v !== t.nodeValue) t.nodeValue = v; }
    for (const el of [root, ...root.querySelectorAll("[placeholder],[title],[aria-label]")])
      for (const a of ATTRS) { const v = el.getAttribute?.(a); if (v) { const x = T(v); if (x !== v) el.setAttribute(a, x); } }
  };
  new MutationObserver(ms => { for (const m of ms) { if (m.type === "characterData") fix(m.target); else m.addedNodes.forEach(fix); } })
    .observe(document.documentElement, { childList: true, subtree: true, characterData: true });
  document.addEventListener("DOMContentLoaded", () => { fix(document.body); document.title = T(document.title); });
  const c = window.confirm.bind(window); window.confirm = m => c(T(m));
})();
