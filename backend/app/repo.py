"""The shared git repo agents actually write and commit code into — the real
build output behind the task board. Task rows track who's on the hook for
what; this is where the work itself lands."""
import subprocess
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent / "workspace_repo"


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=REPO_DIR, capture_output=True, text=True, check=True
    )


def ensure_repo() -> None:
    REPO_DIR.mkdir(exist_ok=True)
    if not (REPO_DIR / ".git").exists():
        _git("init")
        _git("config", "user.email", "agents@collab.local")
        _git("config", "user.name", "Agent Collab Platform")


def _safe_path(path: str) -> Path:
    target = (REPO_DIR / path).resolve()
    if REPO_DIR.resolve() not in target.parents:
        raise ValueError(f"path escapes workspace repo: {path}")
    return target


def write_and_commit(path: str, content: str, author_name: str, message: str) -> str:
    """Write a file and commit it under the given agent's name. Returns the short commit hash."""
    ensure_repo()
    target = _safe_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    _git("add", path)
    author = f"{author_name} <agent@collab.local>"
    _git("commit", "-m", message, f"--author={author}", "--allow-empty")
    return _git("rev-parse", "--short", "HEAD").stdout.strip()


def list_files() -> list[str]:
    ensure_repo()
    return [f for f in _git("ls-files").stdout.splitlines() if f]


def read_file(path: str) -> str:
    ensure_repo()
    target = _safe_path(path)
    if not target.exists():
        raise FileNotFoundError(path)
    return target.read_text(encoding="utf-8")


def log(limit: int = 20) -> list[dict]:
    ensure_repo()
    result = _git("log", f"-{limit}", "--pretty=format:%h|%an|%s|%ai")
    commits = []
    for line in result.stdout.splitlines():
        if not line:
            continue
        h, author, subject, date = line.split("|", 3)
        commits.append({"hash": h, "author": author, "message": subject, "date": date})
    return commits


def reset() -> None:
    """Wipe and reinitialize the repo — called by seed_demo.py for a clean demo."""
    import os
    import shutil
    import stat
    import time

    def _force_delete(func, path, exc_info):
        # git marks object files read-only on Windows; rmtree can't unlink
        # them without this.
        os.chmod(path, stat.S_IWRITE)
        func(path)

    if REPO_DIR.exists():
        # On Windows (especially inside a OneDrive-synced folder), a file in
        # the tree can be locked by the sync client or an editor's watcher.
        # Retry a few times; if it still won't budge, keep the existing repo
        # rather than blocking the whole demo on an environment quirk.
        for attempt in range(5):
            try:
                shutil.rmtree(REPO_DIR, onerror=_force_delete)
                break
            except OSError as e:
                if attempt == 4:
                    print(f"warning: could not reset workspace_repo ({e}); keeping existing history")
                else:
                    time.sleep(0.5 * (attempt + 1))
    ensure_repo()
