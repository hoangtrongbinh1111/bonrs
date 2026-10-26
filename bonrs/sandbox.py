"""Run job processes as the owning user's own uid (Docker, BONRS_SANDBOX=1) or, in local dev, as the
server user with a scrubbed environment. Either way a job never sees server secrets.

Tenant uid = 20000 + user id (0 = system jobs such as the crawler). Each tenant has DATA/tenants/<uid>/
(home, ssh key, lit cache, work dirs). The tenant cannot read bonrs.db, other tenants, or write /app.
"""
import json, os, secrets, subprocess, sys
from pathlib import Path
from . import DATA, ROOT

ON = os.environ.get("BONRS_SANDBOX") == "1"
HELPER = "/usr/local/sbin/bonrs-sandbox"
SPECDIR = DATA / ".sandbox"
# Only these variables of the server's own environment reach a job (never BONRS_ADMIN_*, keys, ...)
PASS_ENV = ("PATH", "LANG", "LC_ALL", "LC_CTYPE", "TZ", "TERM", "VIRTUAL_ENV", "BONRS_CLAUDE_BIN", "BONRS_MOCK_DELAY", "BONRS_KB_MODEL")


def uid_of(owner: int) -> int: return 20000 + int(owner or 0)


def tenant_dir(owner: int) -> Path:
    d = DATA / "tenants" / str(uid_of(owner))
    for sub in ("home", "work", "ssh"): (d / sub).mkdir(parents=True, exist_ok=True)
    return d


def base_env(owner: int, extra: dict | None = None) -> dict:
    td = tenant_dir(owner)
    env = {k: os.environ[k] for k in PASS_ENV if k in os.environ}
    env.setdefault("PATH", "/usr/local/bin:/usr/bin:/bin")
    key = td / "ssh/id_ed25519"
    env.update({"HOME": str(td / "home"), "BONRS_DATA": str(DATA), "BONRS_CACHE": str(td / "cache.sqlite"), "BONRS_ROOT": str(ROOT),
                "BONRS_SSH_KEY": str(key), "PYTHONUNBUFFERED": "1", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1", "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_SSH_COMMAND": f"ssh -i {key} -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new"})
    env["RSYNC_RSH"] = env["GIT_SSH_COMMAND"]
    env.update({k: str(v) for k, v in (extra or {}).items() if v is not None})
    return env


def _wrap(owner: int, argv: list, cwd: Path, env: dict, chown: list, timeout, reap=False, cpu=None) -> list:
    if not ON: return [str(a) for a in argv]
    SPECDIR.mkdir(mode=0o700, exist_ok=True); os.chmod(SPECDIR, 0o700)
    spec = SPECDIR / f"{secrets.token_hex(12)}.json"
    fd = os.open(spec, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as fh:
        json.dump({"chown": [str(p) for p in chown], "cwd": str(cwd), "argv": [str(a) for a in argv], "env": env, "timeout": timeout, "reap": reap, "cpu": cpu}, fh)
    return ["sudo", "-n", HELPER, str(uid_of(owner)), str(spec)]


def popen(owner: int, argv: list, cwd: Path, env: dict, chown=(), timeout=None, **kw) -> subprocess.Popen:
    """Start a long job. In sandbox mode the pid is sudo's: stop it with os.kill (sudo relays the signal)."""
    return subprocess.Popen(_wrap(owner, argv, cwd, env, [*chown, tenant_dir(owner)], timeout, reap=True), cwd="/" if ON else cwd,
                            env={"PATH": "/usr/bin:/bin"} if ON else env, start_new_session=True, **kw)


def run(owner: int, argv: list, cwd: Path, chown=(), timeout=120, env=None, **kw) -> subprocess.CompletedProcess:
    """Short command as the tenant (git, ssh test, pdftotext, zip, ssh-keygen)."""
    e = base_env(owner, env)
    return subprocess.run(_wrap(owner, argv, cwd, e, [*chown, tenant_dir(owner)], timeout, cpu=600), cwd="/" if ON else cwd,
                          env={"PATH": "/usr/bin:/bin"} if ON else e, timeout=(timeout + 30) if timeout else None, **kw)


GIT_SAFE = ["-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false", "-c", "safe.directory=*"]


def git(owner: int, rd: Path, *args, chown=False) -> str:
    """git in a run folder as the run's owner: a planted hook/config only ever runs with the tenant's own rights."""
    r = run(owner, ["git", *GIT_SAFE, "-C", str(rd), *args], rd, chown=[rd] if chown else (), capture_output=True, text=True, timeout=120)
    return r.stdout


def hand_over(owner: int, rd: Path):
    """Make server-written files in a run folder usable by its owner (no-op outside sandbox mode)."""
    if ON: run(owner, ["true"], rd, chown=[rd], timeout=60)


def python() -> str: return "/usr/local/bin/python3" if ON else sys.executable
