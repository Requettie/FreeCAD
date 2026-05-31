"""
Git-based update checker for the in-app updater.

Pure-Python (uses the ``git`` CLI via subprocess), no FreeCAD dependency, so
it is testable against the real repository. The GUI layer (InitGui.py) polls
``check_for_updates`` on a timer and shows a status-bar notice when the fork
has new commits; ``pull`` applies them with a fast-forward.
"""

from __future__ import annotations

import os
import subprocess
from typing import Dict, Optional, Tuple


def _run(args, cwd) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True,
    )


def repo_root(start: str) -> Optional[str]:
    """Walk up from ``start`` to the directory containing ``.git``."""
    p = os.path.abspath(start)
    while True:
        if os.path.isdir(os.path.join(p, ".git")):
            return p
        parent = os.path.dirname(p)
        if parent == p:
            return None
        p = parent


def current_branch(repo: str) -> Optional[str]:
    r = _run(["rev-parse", "--abbrev-ref", "HEAD"], repo)
    return r.stdout.strip() or None if r.returncode == 0 else None


def fetch(repo: str, remote: str = "origin") -> bool:
    return _run(["fetch", "--quiet", remote], repo).returncode == 0


def _parse_counts(text: str) -> Optional[Tuple[int, int]]:
    """Parse ``git rev-list --left-right --count HEAD...remote`` output.

    Output is '<left>\\t<right>' = (ahead, behind) for HEAD...remote.
    Returns (behind, ahead).
    """
    parts = text.split()
    if len(parts) != 2:
        return None
    ahead, behind = int(parts[0]), int(parts[1])
    return behind, ahead


def behind_ahead(repo: str, branch: Optional[str] = None,
                 remote: str = "origin") -> Optional[Tuple[int, int]]:
    branch = branch or current_branch(repo)
    if not branch:
        return None
    r = _run(["rev-list", "--left-right", "--count",
              f"HEAD...{remote}/{branch}"], repo)
    if r.returncode != 0:
        return None
    return _parse_counts(r.stdout)


def latest_remote_message(repo: str, branch: Optional[str] = None,
                          remote: str = "origin") -> str:
    branch = branch or current_branch(repo)
    r = _run(["log", "-1", "--format=%h %s", f"{remote}/{branch}"], repo)
    return r.stdout.strip() if r.returncode == 0 else ""


def check_for_updates(repo: str, do_fetch: bool = True,
                      remote: str = "origin") -> Dict:
    """Return a status dict the GUI can render directly."""
    branch = current_branch(repo)
    if branch is None:
        return {"ok": False, "error": "not a git repository"}
    if do_fetch and not fetch(repo, remote):
        return {"ok": False, "error": "git fetch failed (offline?)",
                "branch": branch}
    ba = behind_ahead(repo, branch, remote)
    if ba is None:
        return {"ok": False, "error": f"no upstream {remote}/{branch}",
                "branch": branch}
    behind, ahead = ba
    return {
        "ok": True,
        "branch": branch,
        "behind": behind,
        "ahead": ahead,
        "update_available": behind > 0,
        "latest": latest_remote_message(repo, branch, remote),
    }


def pull(repo: str, remote: str = "origin", branch: Optional[str] = None,
         ff_only: bool = True) -> Tuple[bool, str]:
    branch = branch or current_branch(repo)
    args = ["pull"] + (["--ff-only"] if ff_only else []) + [remote, branch]
    r = _run(args, repo)
    return r.returncode == 0, (r.stdout + r.stderr).strip()
