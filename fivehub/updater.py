"""Pipeline self-update.

FiveHub installs by reference to its git clone, so updating IS a git pull:
one pull refreshes core, the Houdini menu/windows, drop-in tools, pipeline
HDAs and the app's renderer. This module makes that a one-click operation:

- ``check()``   compare the local version against the newest vX.Y.Z tag on
                the remote (``git ls-remote`` — touches nothing locally)
- ``update()``  ``git pull --ff-only`` + ``npm install`` when the app's
                dependencies changed; reports what needs a restart

The app checks in the background on every launch and offers the update in
a small dismissible popup (plus a header UPDATE button) — nothing pulls
without the user accepting. All of it degrades safely: offline, non-git
installs and dirty checkouts produce clear messages, never a broken
pipeline.
"""

import os
import re
import shutil
import subprocess

from . import __version__, config

GIT_TIMEOUT = 60
_TAG_RE = re.compile(r"refs/tags/v(\d+)\.(\d+)\.(\d+)$")

# Paths the pipeline regenerates on each machine (gitignored; clones from
# before the ignore may still track them). Local changes there are
# disposable by definition and must never block an update.
GENERATED_PATHS = ("houdini/splash",)


def _run(repo, *args, timeout=GIT_TIMEOUT):
    if not shutil.which("git"):
        return False, "git is not installed"
    try:
        completed = subprocess.run(
            ["git", "-C", repo, *args], capture_output=True, text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return False, str(error)
    output = (completed.stdout or "") + (completed.stderr or "")
    return completed.returncode == 0, output.strip()


def parse_version(text):
    try:
        return tuple(int(part) for part in str(text).strip().split("."))
    except ValueError:
        return (0, 0, 0)


def newest_tag(ls_remote_output):
    """Highest vX.Y.Z from `git ls-remote --tags` output, or ''."""
    best = None
    for line in ls_remote_output.splitlines():
        match = _TAG_RE.search(line.strip())
        if match:
            version = tuple(int(part) for part in match.groups())
            if best is None or version > best:
                best = version
    return ".".join(str(part) for part in best) if best else ""


def is_git_checkout(repo=None):
    return os.path.isdir(os.path.join(repo or config.repo_root(), ".git"))


def check(repo=None):
    """{'current', 'remote', 'update_available', 'error'} — read-only."""
    repo = repo or config.repo_root()
    result = {"current": __version__, "remote": "", "update_available": False,
              "error": ""}
    if not is_git_checkout(repo):
        result["error"] = "not a git checkout — update by re-downloading FiveHub"
        return result
    ok, output = _run(repo, "ls-remote", "--tags", "origin")
    if not ok:
        result["error"] = output or "could not reach the remote"
        return result
    remote = newest_tag(output)
    result["remote"] = remote
    result["update_available"] = bool(
        remote and parse_version(remote) > parse_version(__version__)
    )
    return result


def update(repo=None):
    """Fast-forward the clone; npm install when the app manifest changed."""
    repo = repo or config.repo_root()
    result = {"old": __version__, "new": __version__, "updated": False,
              "npm": "", "restart": [], "error": ""}
    if not is_git_checkout(repo):
        result["error"] = "not a git checkout — update by re-downloading FiveHub"
        return result

    for generated in GENERATED_PATHS:
        _run(repo, "checkout", "--", generated)  # no-op once untracked

    before_ok, before = _run(repo, "rev-parse", "HEAD")
    ok, output = _run(repo, "pull", "--ff-only", timeout=300)
    if not ok:
        result["error"] = (
            "git pull failed — local changes or a diverged branch:\n%s"
            % output[-1500:]
        )
        return result
    after_ok, after = _run(repo, "rev-parse", "HEAD")
    if before_ok and after_ok and before == after:
        return result  # already up to date

    result["updated"] = True
    result["new"] = _read_pulled_version(repo)
    result["restart"] = ["app", "houdini"]
    _refresh_splash(repo)

    _ok, changed = _run(repo, "diff", "--name-only", before, after)
    if "app/package.json" in changed:
        npm = shutil.which("npm")
        if npm:
            try:
                completed = subprocess.run(
                    [npm, "install"], cwd=os.path.join(repo, "app"),
                    capture_output=True, text=True, timeout=1200,
                )
                result["npm"] = "ok" if completed.returncode == 0 else "failed"
            except (OSError, subprocess.TimeoutExpired):
                result["npm"] = "failed"
        else:
            result["npm"] = "npm not found — run npm install in app/"
    return result


def _refresh_splash(repo):
    """Re-render the machine-generated splash after every update — the
    pull may have brought new art or a new generator. Reloaded so even a
    long-lived process (Houdini) renders the freshly pulled code."""
    if os.path.normpath(repo) != os.path.normpath(config.repo_root()):
        return  # test fixtures and foreign clones render nothing
    try:
        import importlib

        from .tools import splash

        importlib.reload(splash)
        splash.render(
            os.path.join(repo, "houdini", "splash", "fivehub_splash.png")
        )
    except Exception:
        pass  # no Pillow — Houdini shows its stock splash until reinstall


def _read_pulled_version(repo):
    """__version__ from the freshly pulled file (this process still runs
    the old code, so read it from disk)."""
    try:
        with open(os.path.join(repo, "fivehub", "__init__.py"), encoding="utf-8") as f:
            match = re.search(r'__version__\s*=\s*"([^"]+)"', f.read())
            return match.group(1) if match else __version__
    except OSError:
        return __version__
