"""Which build is running: the git commit is the API version (override with SPAN_VERSION)."""
import os
import subprocess
from functools import lru_cache
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


@lru_cache(maxsize=1)
def git_info() -> tuple[str, str]:
    """(short commit, branch) of the checkout this code runs from; ('unknown', '') outside git."""
    try:
        commit = subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD'], cwd=REPO, text=True, stderr=subprocess.DEVNULL, timeout=5).strip()
        branch = subprocess.check_output(['git', 'rev-parse', '--abbrev-ref', 'HEAD'], cwd=REPO, text=True, stderr=subprocess.DEVNULL, timeout=5).strip()
        return (commit or 'unknown', branch)
    except (OSError, subprocess.SubprocessError):
        return ('unknown', '')


def api_version() -> str:
    return os.environ.get('SPAN_VERSION', '').strip() or git_info()[0]


def api_branch() -> str:
    return git_info()[1]
