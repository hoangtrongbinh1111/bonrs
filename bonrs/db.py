"""SQLite state for the web app: users, settings, hosts, runs, jobs, comments, kb drafts."""
import hashlib, hmac, json, os, secrets, sqlite3, threading, time
from . import DATA

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, email TEXT UNIQUE, pw TEXT, role TEXT DEFAULT 'member', api_key TEXT, created REAL);
CREATE TABLE IF NOT EXISTS settings(k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS hosts(id INTEGER PRIMARY KEY, owner INTEGER, name TEXT, type TEXT, config TEXT, created REAL);
CREATE TABLE IF NOT EXISTS runs(slug TEXT PRIMARY KEY, owner INTEGER, idea TEXT, journal TEXT, created REAL);
CREATE TABLE IF NOT EXISTS jobs(id INTEGER PRIMARY KEY, kind TEXT, slug TEXT, args TEXT, status TEXT, pid INTEGER, owner INTEGER,
                               created REAL, started REAL, finished REAL, exit INTEGER, note TEXT);
CREATE TABLE IF NOT EXISTS comments(id INTEGER PRIMARY KEY, slug TEXT, user INTEGER, ts REAL, path TEXT, anchor TEXT, quote TEXT,
                                    body TEXT, kind TEXT, status TEXT DEFAULT 'open', reply TEXT);
"""
_local = threading.local()  # one connection per thread: a shared sqlite3 connection across FastAPI's threadpool + the worker segfaults


def db() -> sqlite3.Connection:
    c = getattr(_local, "conn", None)
    if c is None:
        c = _local.conn = sqlite3.connect(os.environ.get("BONRS_DB", str(DATA / "bonrs.db")), isolation_level=None, timeout=15)
        c.row_factory = sqlite3.Row; c.execute("PRAGMA journal_mode=WAL"); c.execute("PRAGMA busy_timeout=15000"); c.executescript(SCHEMA)
        cols = {r[1] for r in c.execute("PRAGMA table_info(users)")}
        if "disabled" not in cols: c.execute("ALTER TABLE users ADD COLUMN disabled INTEGER DEFAULT 0")  # deleted users stay as rows: ids are never reused
        if "sv" not in cols: c.execute("ALTER TABLE users ADD COLUMN sv INTEGER DEFAULT 0")  # session version: bump to revoke every cookie
        if "oauth_token" not in cols: c.execute("ALTER TABLE users ADD COLUMN oauth_token TEXT")  # the user's own Claude subscription (claude setup-token)
    return c


def q(sql, *a): return [dict(r) for r in db().execute(sql, a).fetchall()]
def one(sql, *a): r = db().execute(sql, a).fetchone(); return dict(r) if r else None
def ex(sql, *a): return db().execute(sql, a).lastrowid


def setting(k, default=None):
    r = one("SELECT v FROM settings WHERE k=?", k); return json.loads(r["v"]) if r else default
def set_setting(k, v): ex("INSERT OR REPLACE INTO settings VALUES (?,?)", k, json.dumps(v))


def hash_pw(pw: str) -> str:
    salt = secrets.token_bytes(16)
    return salt.hex() + ":" + hashlib.scrypt(pw.encode(), salt=salt, n=2 ** 14, r=8, p=1).hex()


def check_pw(pw: str, stored: str) -> bool:
    try: salt, h = stored.split(":"); salt = bytes.fromhex(salt)
    except (AttributeError, ValueError): return False  # disabled accounts store "!"
    return hmac.compare_digest(hashlib.scrypt(str(pw).encode(), salt=salt, n=2 ** 14, r=8, p=1).hex(), h)


def secret() -> bytes:
    s = setting("session_secret")
    if not s: s = secrets.token_hex(32); set_setting("session_secret", s)
    return s.encode()


def sign(uid: int, sv: int = 0) -> str:
    exp = int(time.time()) + 14 * 86400; msg = f"{uid}.{sv}.{exp}"
    return msg + "." + hmac.new(secret(), msg.encode(), "sha256").hexdigest()


def verify(token: str | None) -> tuple[int, int] | None:
    """(uid, session version) of a valid, unexpired cookie; None otherwise."""
    try:
        uid, sv, exp, sig = token.split(".")
        ok = hmac.compare_digest(sig.encode(), hmac.new(secret(), f"{uid}.{sv}.{exp}".encode(), "sha256").hexdigest().encode())
        return (int(uid), int(sv)) if ok and int(exp) > time.time() else None
    except (AttributeError, ValueError, TypeError):
        return None


def ensure_admin():
    email, pw = (os.environ.get("BONRS_ADMIN_EMAIL") or "").strip().lower(), os.environ.get("BONRS_ADMIN_PASSWORD")
    if email and pw and not one("SELECT id FROM users WHERE email=?", email):
        ex("INSERT INTO users(email,pw,role,created) VALUES (?,?,?,?)", email, hash_pw(pw), "admin", time.time())
    os.environ.pop("BONRS_ADMIN_PASSWORD", None)  # only needed once; never kept around for child processes
