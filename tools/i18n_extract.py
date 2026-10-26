"""Collect every Vietnamese UI text fragment from web/app.js and web/index.html (text between tags and attribute values).

    python3 tools/i18n_extract.py /tmp/vi.json    # then add an English entry to web/i18n-en.js for each new fragment
    node tools/i18n_check.js web                  # translator self-check
"""
import html, json, re, sys
VI = re.compile(r'[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđÀÁẠẢÃÂẦẤẬẨẪĂẰẮẶẲẴÈÉẸẺẼÊỀẾỆỂỄÌÍỊỈĨÒÓỌỎÕÔỒỐỘỔỖƠỜỚỢỞỠÙÚỤỦŨƯỪỨỰỬỮỲÝỴỶỸĐ]')

def js_strings(src):
    """Contents of string literals and template text chunks (a small lexer: nested templates, comments, regex literals)."""
    out, i, n, stack = [], 0, len(src), []  # stack of brace depths for ${ } inside templates
    prev = "("
    def read_template(i):
        buf = ""
        while i < n:
            c = src[i]
            if c == "\\": buf += src[i:i+2]; i += 2; continue
            if c == "`": out.append(buf); return i + 1, None
            if c == "$" and src[i+1:i+2] == "{": out.append(buf); return i + 2, "expr"
            buf += c; i += 1
        return i, None
    mode_stack = []  # 'tpl' entries: when an expr closes, go back to template
    depth = 0
    while i < n:
        c = src[i]
        if c in " \t\r\n": i += 1; continue
        if src.startswith("//", i): i = src.find("\n", i); i = n if i < 0 else i; continue
        if src.startswith("/*", i): i = src.find("*/", i) + 2; continue
        if c in "\"'":
            j, buf = i + 1, ""
            while j < n and src[j] != c:
                if src[j] == "\\": buf += src[j:j+2]; j += 2; continue
                buf += src[j]; j += 1
            out.append(buf); i = j + 1; prev = "a"; continue
        if c == "`":
            i, st = read_template(i + 1)
            if st == "expr": mode_stack.append(depth); depth = 0
            prev = "a"; continue
        if c == "/" and prev in "(,=:[!&|?{};+-*%<>~^" :
            j, cls = i + 1, False
            while j < n:
                if src[j] == "\\": j += 2; continue
                if src[j] == "[": cls = True
                elif src[j] == "]": cls = False
                elif src[j] == "/" and not cls: break
                j += 1
            i = j + 1; prev = "a"; continue
        if c == "{": depth += 1
        elif c == "}":
            if depth == 0 and mode_stack:
                depth = mode_stack.pop()
                i, st = read_template(i + 1)
                if st == "expr": mode_stack.append(depth); depth = 0
                prev = "a"; continue
            depth -= 1
        prev = c if not (c.isalnum() or c in "_$") else "a"
        i += 1
    return out

def unescape_js(s): return re.sub(r"\\(.)", lambda m: {"n": "\n", "t": "\t"}.get(m.group(1), m.group(1)), s)
norm = lambda s: re.sub(r"\s+", " ", html.unescape(s)).strip()

def fragments(chunk):
    chunk = unescape_js(chunk); res = []
    res += re.findall(r'(?:title|aria-label|placeholder|alt)="([^"]*)', chunk)  # attribute values, also when a ${} cuts them
    m = re.match(r'^([^"<>=]*)"', chunk)  # tail of an attribute value that began before a ${}
    if m: res.append(m.group(1))
    res += [p for p in re.split(r"<[^<>]*>|[<>]", chunk) if '="' not in p and not p.lstrip().startswith('"')]
    return [norm(p) for p in res if VI.search(p)]

segs = set()
src = open("web/app.js").read()
for ch in js_strings(src):
    segs.update(x for x in fragments(ch) if x)
for x in fragments(open("web/index.html").read()): segs.add(x)
segs = sorted(segs, key=lambda x: (-len(x), x))
json.dump(segs, open(sys.argv[1], "w"), ensure_ascii=False, indent=0)
print(len(segs), sum(map(len, segs)))
