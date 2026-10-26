"""Experiment hosts: type local | ssh (| slurm, kept for the CLI). Logs are the contract.

Every run gets its own folder on a host: <workdir>/<run slug>. `setup: auto` makes a venv there and installs
requirements.txt. With several hosts, `--host auto` sends a job to the least busy reachable one.
"""
import os, re, shlex, subprocess, time
from pathlib import Path

SSH_DEST = re.compile(r"^(?:[A-Za-z0-9._-]{1,64}@)?[A-Za-z0-9][A-Za-z0-9.-]{0,252}$")  # user@host, never an ssh option
WORKDIR = re.compile(r"^(?:~|~/|/)?[A-Za-z0-9._/-]{0,200}$")
TAG = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
GPUS = re.compile(r"^[0-9]{1,2}(,[0-9]{1,2}){0,15}$")
SBATCH_KEY, SBATCH_VAL = re.compile(r"^[a-z][a-z-]{0,30}$"), re.compile(r"^[A-Za-z0-9:_.,=/@+-]{1,100}$")
AUTO_SETUP = ("{ [ -d .venv ] || python3 -m venv .venv 2>/dev/null; [ -f .venv/bin/activate ] && . .venv/bin/activate; "
              "[ ! -f requirements.txt ] || python3 -m pip install -q --disable-pip-version-check -r requirements.txt; true; }")
# One line per fact; parsed by probe_info(). Works on Linux (macOS hosts report less).
PROBE = ("echo BONRS_OK; echo \"HOST=$(hostname)\"; echo \"OS=$( (. /etc/os-release 2>/dev/null && echo $PRETTY_NAME) || uname -sr)\"; "
         "echo \"HOME=$HOME\"; echo \"CPU=$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null)\"; "
         "echo \"MEM=$(free -g 2>/dev/null | awk '/Mem:/{print $2}')\"; echo \"LOAD=$(cut -d' ' -f1 /proc/loadavg 2>/dev/null)\"; "
         "echo \"DISK=$(df -h \"$HOME\" 2>/dev/null | awk 'NR==2{print $4}')\"; echo \"PY=$(python3 --version 2>&1 | head -1)\"; "
         "echo \"VENV=$(python3 -c 'import venv,ensurepip' 2>/dev/null && echo yes || echo no)\"; "
         "echo \"CONDA=$(command -v conda || ls -d ~/miniconda3 ~/anaconda3 ~/miniforge3 2>/dev/null | head -1)\"; "
         "nvidia-smi --query-gpu=index,name,memory.total,memory.used,utilization.gpu --format=csv,noheader,nounits 2>/dev/null | sed 's/^/GPU=/'; true")


def check_host(h: dict) -> dict:
    """Validate the fields that end up in ssh/rsync argv or a remote shell line. `setup` is a shell command by design
    (it runs on the user's own host, or locally as the user's sandboxed uid)."""
    t = h.get("type") or ("ssh" if h.get("ssh") else "local")
    if t not in ("local", "ssh", "slurm"): raise ValueError("host type must be local|ssh|slurm")
    out = {"name": str(h.get("name") or t)[:40], "type": t, "setup": str(h.get("setup") or "auto")[:2000]}
    if t != "local":
        if not SSH_DEST.match(str(h.get("ssh") or "")): raise ValueError("ssh must look like user@host")
        out["ssh"] = h["ssh"]
        wd = str(h.get("workdir") or "~/bonrs-runs")
        if not WORKDIR.match(wd) or ".." in wd.split("/"): raise ValueError("workdir: letters, digits, . _ - / ~ only")
        out["workdir"] = wd.rstrip("/") or "/"
        if h.get("port") not in (None, "", 22, "22"):
            p = int(h["port"])
            if not 1 <= p <= 65535: raise ValueError("port must be 1-65535")
            out["port"] = p
    if h.get("gpus") not in (None, ""):
        if not GPUS.match(str(h["gpus"]).replace(" ", "")): raise ValueError("gpus: GPU numbers like 0 or 0,1")
        out["gpus"] = str(h["gpus"]).replace(" ", "")
    sb = h.get("sbatch") or {}
    if not isinstance(sb, dict) or any(not SBATCH_KEY.match(str(k)) or not SBATCH_VAL.match(str(v)) for k, v in sb.items()): raise ValueError("bad sbatch options")
    if sb: out["sbatch"] = {str(k): str(v) for k, v in sb.items()}
    return out


def hosts_of(cfg: dict) -> list[dict]:
    return [check_host(h) for h in ((cfg.get("remote") or {}).get("hosts") or [{"name": "local", "type": "local"}])]


def host(cfg: dict, name: str | None, run_dir: Path | None = None, tag: str | None = None) -> dict:
    """Named host; without a name, the host this tag was sent to (see run --host auto), else the first host."""
    hs = hosts_of(cfg)
    if name is None and run_dir is not None and tag and TAG.match(tag) and (run_dir / f"exp/logs/{tag}.host").exists():
        name = (run_dir / f"exp/logs/{tag}.host").read_text().strip()
    if name is None: return hs[0]
    h = next((x for x in hs if x["name"] == name), None)
    if not h: raise SystemExit(f"no host named {name!r} in bonrs.yaml (have: {', '.join(x['name'] for x in hs)})")
    return h


def setup_cmd(h: dict) -> str:
    s = h.get("setup") or "auto"
    s = AUTO_SETUP if s == "auto" else s
    return (f"export CUDA_VISIBLE_DEVICES={h['gpus']}; " if h.get("gpus") else "") + s


def _wd(h, run_dir: Path) -> str: return f"{h['workdir']}/{run_dir.name}"  # one folder per run: runs never overwrite each other


def _key(): return os.environ.get("BONRS_SSH_KEY")  # the job owner's own key, set by the server (never taken from bonrs.yaml)


def ssh_opts(h, key=None) -> list:
    key = key or _key()
    o = ["-i", str(key), "-o", "IdentitiesOnly=yes"] if key else []
    return o + ["-o", "StrictHostKeyChecking=accept-new"] + (["-p", str(h["port"])] if h.get("port") else [])


def _rsh(h): return ["-e", " ".join(["ssh", *ssh_opts(h)])]


def _ssh(h, cmd, retries=4, **kw):
    """ssh with exponential backoff (30s→1m→5m→15m); never silently give up on transient errors."""
    delays = [30, 60, 300, 900]
    for i in range(retries + 1):
        r = subprocess.run(["ssh", *ssh_opts(h), "-o", "BatchMode=yes", "-o", "ConnectTimeout=20", "--", h["ssh"], cmd], text=True, **kw)
        if r.returncode != 255: return r  # 255 = ssh transport failure
        if i < retries: print(f"ssh failed, retry in {delays[i]}s"); time.sleep(delays[i])
    return r


def _local(cmd, run_dir, **kw):
    (run_dir / "exp").mkdir(parents=True, exist_ok=True)
    return subprocess.run(["bash", "-lc", cmd], cwd=run_dir / "exp", text=True, **kw)


def probe_info(text: str) -> dict:
    """Parse PROBE output into {host, os, home, cpu, mem, load, disk, py, venv, conda, gpus:[...]}."""
    info, gpus = {}, []
    for line in text.splitlines():
        k, _, v = line.partition("=")
        if k == "GPU":
            p = [x.strip() for x in v.split(",")]
            if len(p) >= 5: gpus.append({"index": p[0], "name": p[1][:80], "mem_total_mb": p[2], "mem_used_mb": p[3], "util": p[4]})
        elif k in ("HOST", "OS", "HOME", "CPU", "MEM", "LOAD", "DISK", "PY", "VENV", "CONDA"): info[k.lower()] = v.strip()[:200]
    info["gpus"] = gpus[:16]
    return info


def _f(x, d=0.0):
    try: return float(x)
    except (TypeError, ValueError): return d


def busy(h: dict, run_dir: Path) -> float | None:
    """0 = idle, 1 = full; None = unreachable. GPU hosts: worst of util and memory per GPU, averaged; else load/cores."""
    r = _local(PROBE, run_dir, capture_output=True, timeout=60) if h["type"] == "local" else _ssh(h, PROBE, retries=0, capture_output=True, timeout=60)
    if "BONRS_OK" not in (r.stdout or ""): return None
    i = probe_info(r.stdout)
    gs = [g for g in i["gpus"] if not h.get("gpus") or g["index"] in h["gpus"].split(",")]
    if gs: return sum(max(_f(g["util"]) / 100, _f(g["mem_used_mb"]) / max(1.0, _f(g["mem_total_mb"], 1))) for g in gs) / len(gs)
    return _f(i.get("load"), 1.0) / max(1.0, _f(i.get("cpu"), 1.0))


def pick(cfg, run_dir: Path, need_gpu=False) -> dict:
    """Least busy reachable host of this run (ponytail: probes each host every time; fine for a handful of hosts)."""
    scored = []
    for h in hosts_of(cfg):
        if h["type"] == "slurm": scored.append((0.5, h)); continue  # the scheduler queues for us
        if need_gpu:
            r = _local("nvidia-smi -L", run_dir, capture_output=True, timeout=30) if h["type"] == "local" else _ssh(h, "nvidia-smi -L", retries=0, capture_output=True, timeout=30)
            if r.returncode != 0: print(f"  {h['name']}: no GPU"); continue
        b = busy(h, run_dir)
        if b is not None: scored.append((b, h))
        print(f"  {h['name']}: {'unreachable' if b is None else f'busy {b:.2f}'}")
    if not scored: raise SystemExit("no reachable host" + (" with a GPU" if need_gpu else ""))
    return min(scored, key=lambda x: x[0])[1]


def push(cfg, run_dir: Path, name=None):
    for h in (hosts_of(cfg) if name in (None, "auto") else [host(cfg, name)]):  # every host of the run gets the same code
        if h["type"] == "local": continue
        wd = _wd(h, run_dir)
        _ssh(h, f"mkdir -p {wd}/logs {wd}/results")
        subprocess.run(["rsync", *_rsh(h), "-az", "--delete", "--exclude", "results/", "--exclude", "logs/", "--exclude", ".venv/", "--exclude", "*.pt",
                        "--exclude", "data/", f"{run_dir}/exp/", f"{h['ssh']}:{wd}/"], check=True)
        print(f"pushed exp/ to {h['name']}:{wd}")


def run(cfg, run_dir: Path, command: str, name=None, tag="job", need_gpu=False):
    if not TAG.match(tag): raise SystemExit("tag: letters, digits, _ - only")
    h = pick(cfg, run_dir, need_gpu) if name == "auto" else host(cfg, name)
    (run_dir / "exp/logs").mkdir(parents=True, exist_ok=True)
    (run_dir / f"exp/logs/{tag}.host").write_text(h["name"])  # tail/pull of this tag find the host again
    print(f"host {h['name']}")
    if h["type"] == "local":
        p = subprocess.Popen(["bash", "-lc", f"{setup_cmd(h)} && {command}"], cwd=run_dir / "exp",
                             stdout=open(run_dir / f"exp/logs/{tag}.log", "w"), stderr=subprocess.STDOUT, start_new_session=True)
        return print(f"pid {p.pid} log exp/logs/{tag}.log")
    wd = _wd(h, run_dir)
    if h["type"] == "slurm":
        opts = " ".join(f"--{k}={v}" for k, v in (h.get("sbatch") or {}).items())  # partition, account, time, gres, cpus-per-task, mem
        r = _ssh(h, f"cd {wd} && mkdir -p logs && sbatch --parsable --job-name={tag} --output=logs/{tag}.log {opts} "
                    f"--wrap={shlex.quote(setup_cmd(h) + ' && ' + command)}", capture_output=True)
        return print("slurm job", r.stdout.strip() or r.stderr)
    r = _ssh(h, f"cd {wd} && mkdir -p logs && nohup bash -c {shlex.quote(setup_cmd(h) + ' && ' + command)} > logs/{tag}.log 2>&1 < /dev/null & echo $!", capture_output=True)
    print("pid", r.stdout.strip() or r.stderr)


def tail(cfg, run_dir: Path, name=None, tag="job", n=80):
    if not TAG.match(tag): raise SystemExit("tag: letters, digits, _ - only")
    h = host(cfg, name, run_dir, tag); n = int(n)
    if h["type"] == "local":
        f = run_dir / f"exp/logs/{tag}.log"; return print(f.read_text()[-4000:] if f.exists() else "no log yet")
    extra = f"; squeue -u $USER -n {tag} -h -o '%i %T %M' || true" if h["type"] == "slurm" else "; pgrep -af 'python|julia|Rscript' | head -5 || true"
    _ssh(h, f"tail -n {n} {_wd(h, run_dir)}/logs/{tag}.log 2>/dev/null || echo 'no log yet'{extra}")


def status(cfg, run_dir: Path, name=None):
    for h in (hosts_of(cfg) if name in (None, "auto") else [host(cfg, name)]):
        b = busy(h, run_dir) if h["type"] != "slurm" else 0.5
        print(f"{h['name']} ({h['type']}): " + ("unreachable" if b is None else f"busy {b:.2f}"))


def pull(cfg, run_dir: Path, name=None):
    for h in (hosts_of(cfg) if name in (None, "auto") else [host(cfg, name)]):  # results may sit on any host the run used
        if h["type"] == "local": continue
        for d in ("results", "logs"):
            (run_dir / "exp" / d).mkdir(parents=True, exist_ok=True)
            subprocess.run(["rsync", *_rsh(h), "-az", f"{h['ssh']}:{_wd(h, run_dir)}/{d}/", f"{run_dir}/exp/{d}/"], check=False)


def doctor(cfg, run_dir: Path, name=None) -> bool:
    """Before trusting hosts: python, GPU, write access, round-trip a file. True if every checked host is usable."""
    ok = True
    for h in (hosts_of(cfg) if name in (None, "auto") else [host(cfg, name)]):
        checks = "python3 --version && (nvidia-smi -L 2>/dev/null || echo 'no GPU') && echo ok > .bonrs_doctor && cat .bonrs_doctor"
        if h["type"] == "local": r = _local(checks, run_dir, capture_output=True)
        else: wd = _wd(h, run_dir); r = _ssh(h, f"mkdir -p {wd} && cd {wd} && {checks}", capture_output=True)
        good = r.returncode == 0 and "ok" in r.stdout; ok &= good
        print(f"== {h['name']}: {'OK' if good else 'NOT USABLE'}\n{r.stdout}{r.stderr}")
    return ok
