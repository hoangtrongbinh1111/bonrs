"""File I/O inside directories a lower-trust process can write (run folders, tenant folders).

The agent of a run may plant symlinks, FIFOs or hard links. Every server-side read/write there goes
through these helpers: each path component is opened relative to the previous one with O_NOFOLLOW,
and only regular files with a single link are read or overwritten.
"""
import os, stat
from pathlib import Path

_D = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


def _parts(rel: str) -> list[str]:
    parts = [p for p in str(rel).split("/") if p not in ("", ".")]
    if not parts or any(p == ".." for p in parts): raise ValueError(f"bad path: {rel!r}")
    return parts


def _dir(base: Path, parts: list[str], create=False) -> int:
    fd = os.open(base, _D)
    try:
        for p in parts:
            try: nfd = os.open(p, _D, dir_fd=fd)
            except FileNotFoundError:
                if not create: raise
                os.mkdir(p, 0o770, dir_fd=fd); nfd = os.open(p, _D, dir_fd=fd)
            os.close(fd); fd = nfd
        return fd
    except BaseException:
        os.close(fd); raise


def _check(fd: int):
    st = os.fstat(fd)
    if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1: raise PermissionError("not a plain file")
    return st


def read_bytes(base: Path, rel: str, limit: int | None = None, tail: bool = False) -> bytes:
    """Read a regular file under base. limit caps the bytes read (tail=True keeps the end)."""
    parts = _parts(rel); dfd = _dir(base, parts[:-1])
    try: fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dfd)
    finally: os.close(dfd)
    with os.fdopen(fd, "rb") as f:
        st = _check(fd)
        if limit and tail and st.st_size > limit: f.seek(st.st_size - limit)
        return f.read(limit) if limit else f.read()


def read_text(base: Path, rel: str, limit: int | None = None, tail: bool = False, default=None) -> str | None:
    try: return read_bytes(base, rel, limit, tail).decode("utf8", "replace")
    except (OSError, ValueError): return default


def open_read(base: Path, rel: str):
    """Binary file object for streaming (caller closes)."""
    parts = _parts(rel); dfd = _dir(base, parts[:-1])
    try: fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dfd)
    finally: os.close(dfd)
    try: _check(fd)
    except BaseException: os.close(fd); raise
    return os.fdopen(fd, "rb")


def write_bytes(base: Path, rel: str, data: bytes, append=False, exclusive=False, mkdirs=True):
    parts = _parts(rel); dfd = _dir(base, parts[:-1], create=mkdirs)
    fl = os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK | (os.O_APPEND if append else 0) | (os.O_EXCL if exclusive else 0)
    try: fd = os.open(parts[-1], fl, 0o660, dir_fd=dfd)
    finally: os.close(dfd)
    with os.fdopen(fd, "wb") as f:
        _check(fd)
        if not append: f.truncate(0)
        f.write(data)


def write_text(base: Path, rel: str, text: str, **kw): write_bytes(base, rel, text.encode("utf8"), **kw)


def open_write(base: Path, rel: str, append=False):
    """Binary file object for streaming writes (caller closes)."""
    parts = _parts(rel); dfd = _dir(base, parts[:-1], create=True)
    fl = os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK | (os.O_APPEND if append else 0)
    try: fd = os.open(parts[-1], fl, 0o660, dir_fd=dfd)
    finally: os.close(dfd)
    try:
        _check(fd)
        if not append: os.ftruncate(fd, 0)
    except BaseException: os.close(fd); raise
    return os.fdopen(fd, "ab" if append else "wb")


def exists(base: Path, rel: str) -> bool:
    try: parts = _parts(rel); dfd = _dir(base, parts[:-1])
    except (OSError, ValueError): return False
    try: os.stat(parts[-1], dir_fd=dfd, follow_symlinks=False); return True
    except OSError: return False
    finally: os.close(dfd)


def unlink(base: Path, rel: str, missing_ok=True):
    try: parts = _parts(rel); dfd = _dir(base, parts[:-1])
    except FileNotFoundError:
        if missing_ok: return
        raise
    try: os.unlink(parts[-1], dir_fd=dfd)  # removes a symlink itself, never its target
    except FileNotFoundError:
        if not missing_ok: raise
    finally: os.close(dfd)


def listing(base: Path, max_files: int = 20000, skip=(".git",)) -> list[tuple[str, int, float]]:
    """(relative path, size, mtime) of regular files, without following symlinks."""
    out = []
    for root, dirs, files, rfd in os.fwalk(base, follow_symlinks=False):
        dirs[:] = [d for d in dirs if d not in skip]
        for n in files:
            try: st = os.stat(n, dir_fd=rfd, follow_symlinks=False)
            except OSError: continue
            if stat.S_ISREG(st.st_mode): out.append((str(Path(root, n).relative_to(base)), st.st_size, st.st_mtime))
            if len(out) >= max_files: return out
    return out
