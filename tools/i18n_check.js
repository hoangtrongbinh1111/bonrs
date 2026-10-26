// Self-check of the translator outside the browser: exact phrases, composed phrases, user text left alone.
global.window = {}; global.document = { documentElement: { lang: "en" }, addEventListener() {} };
global.MutationObserver = class { observe() {} }; window.confirm = () => true;
const fs = require("fs"), dir = process.argv[2];
eval(fs.readFileSync(dir + "/i18n-en.js", "utf8"));
eval(fs.readFileSync(dir + "/i18n.js", "utf8").replace('"use strict";', "") + "; global.T = T;");
const cases = [["Đăng nhập", "Sign in"], ["5 phút trước", null], ["Mở cửa sổ", "Mở cửa sổ"], ["Tôi muốn nghiên cứu pin", "Tôi muốn nghiên cứu pin"],
  ["Vô hiệu hoá member@local", "Deactivate member@local"], ["Tệp kỹ thuật của hệ thống (1): nhật ký, trạng thái. Thường không cần xem.", null]];
let bad = 0;
for (const [i, want] of cases) { const got = T(i); const ok = want === null ? !/[ạảãâầấậẩẫăằắặẳẵẹẻẽêềếệểễịỉĩọỏõôồốộổỗơờớợởỡụủũưừứựửữỳýỵỷỹđ]/i.test(got) : got === want; if (!ok) bad++; console.log(ok ? "ok " : "BAD", JSON.stringify(i), "->", JSON.stringify(got)); }
process.exit(bad ? 1 : 0);
