"""Git awareness for projects that live in a repository.

FiveHub never requires git — a project works identically on a local disk,
on a server share, or inside a clone. When a project root *is* a git
repository these helpers add the sync layer: status, pull-rebase + push,
setup (init + .gitignore), and optional auto-commits of publishes and
scene saves signed with the artist's name.

All calls shell out to the ``git`` binary; every failure degrades to a
clear message instead of an exception — pipeline operations must never
die because git hiccupped.
"""

import os
import shutil
import subprocess

GIT_TIMEOUT = 120

# What a FiveHub project repository should never track: the local database
# cache (rebuilt from .fivehub/records), transient dirs, and heavy outputs.
GITIGNORE = """# FiveHub — local cache and transient data (rebuilt / per-machine)
project.db
project.db-journal
.trash/
reports/

# Heavy working data — publish what matters instead
*/*/caches/
*/*/render/

# OS noise
.DS_Store
Thumbs.db
"""


def git_available():
    return shutil.which("git") is not None


def is_git_project(root):
    return os.path.isdir(os.path.join(root, ".git"))


def _run(root, *args):
    """(ok, output) — never raises."""
    if not git_available():
        return False, "git is not installed on this machine"
    try:
        completed = subprocess.run(
            ["git", "-C", root, *args],
            capture_output=True, text=True, timeout=GIT_TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return False, str(error)
    output = (completed.stdout or "") + (completed.stderr or "")
    return completed.returncode == 0, output.strip()


def status(root):
    """Compact repo state for the UI: branch, ahead/behind, dirty count."""
    if not is_git_project(root):
        return {"git": False}
    ok, branch = _run(root, "rev-parse", "--abbrev-ref", "HEAD")
    result = {
        "git": True,
        "branch": branch if ok else "?",
        "ahead": 0,
        "behind": 0,
        "dirty": 0,
        "remote": False,
        "error": "",
    }
    ok, porcelain = _run(root, "status", "--porcelain")
    if ok:
        result["dirty"] = len([line for line in porcelain.splitlines() if line.strip()])
    else:
        result["error"] = porcelain
    ok, counts = _run(root, "rev-list", "--left-right", "--count", "@{upstream}...HEAD")
    if ok:
        try:
            behind, ahead = counts.split()
            result["behind"] = int(behind)
            result["ahead"] = int(ahead)
            result["remote"] = True
        except ValueError:
            pass
    return result


def setup(root, user=""):
    """Make a project git-ready: .gitignore, init if needed, first commit."""
    if not git_available():
        raise ValueError("git is not installed on this machine")
    gitignore = os.path.join(root, ".gitignore")
    if not os.path.isfile(gitignore):
        with open(gitignore, "w", encoding="utf-8") as handle:
            handle.write(GITIGNORE)
    initialized = False
    if not is_git_project(root):
        ok, output = _run(root, "init")
        if not ok:
            raise ValueError("git init failed: %s" % output)
        initialized = True
    _run(root, "add", "-A")
    committed, output = _run(
        root, "commit", "-m",
        "[fivehub] project setup%s" % (" — %s" % user if user else ""),
    )
    return {
        "initialized": initialized,
        "committed": committed,
        "detail": output if not committed else "",
    }


def autocommit(root, message):
    """Stage and commit everything (respecting .gitignore). Best-effort:
    returns True on a new commit, False otherwise — never raises."""
    if not is_git_project(root) or not git_available():
        return False
    _run(root, "add", "-A")
    ok, _output = _run(root, "commit", "-m", message)
    return ok


def sync(root, message="", user=""):
    """Share work: commit local changes, pull --rebase, push.

    Steps degrade gracefully — no remote means commit-only, conflicts are
    reported, nothing is destroyed."""
    if not is_git_project(root):
        raise ValueError("this project is not a git repository (run git-setup)")
    if not git_available():
        raise ValueError("git is not installed on this machine")

    steps = []
    _run(root, "add", "-A")
    commit_message = message or "[fivehub] sync%s" % (" — %s" % user if user else "")
    committed, output = _run(root, "commit", "-m", commit_message)
    steps.append({"step": "commit", "ok": True,
                  "detail": "committed" if committed else "nothing to commit"})

    has_remote, _ = _run(root, "rev-parse", "--abbrev-ref", "@{upstream}")
    if not has_remote:
        steps.append({"step": "pull", "ok": True, "detail": "no remote configured"})
        steps.append({"step": "push", "ok": True, "detail": "no remote configured"})
        return {"steps": steps, "ok": True}

    ok, output = _run(root, "pull", "--rebase", "--autostash")
    steps.append({"step": "pull", "ok": ok, "detail": output[-2000:]})
    if not ok:
        _run(root, "rebase", "--abort")
        steps.append({
            "step": "abort", "ok": True,
            "detail": "rebase aborted — resolve the conflict in git, then sync again",
        })
        return {"steps": steps, "ok": False}

    ok, output = _run(root, "push")
    steps.append({"step": "push", "ok": ok, "detail": output[-2000:]})
    return {"steps": steps, "ok": ok}
