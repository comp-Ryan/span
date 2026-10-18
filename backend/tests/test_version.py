"""The API reports which git commit it is running (`/health.version`), so a stale tab or backend is visible at a glance."""
import subprocess
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

REPO = Path(__file__).resolve().parents[2]


def git(*args):
    return subprocess.check_output(['git', *args], cwd=REPO, text=True).strip()


def test_version_is_the_git_commit_by_default(monkeypatch):
    from owed import version
    monkeypatch.delenv('SPAN_VERSION', raising=False)
    version.git_info.cache_clear()
    assert version.api_version() == git('rev-parse', '--short', 'HEAD')
    assert version.api_branch() == git('rev-parse', '--abbrev-ref', 'HEAD')


def test_version_env_overrides_git(monkeypatch):
    from owed import version
    monkeypatch.setenv('SPAN_VERSION', 'v-demo-1')
    version.git_info.cache_clear()
    assert version.api_version() == 'v-demo-1'
    version.git_info.cache_clear()


def test_version_without_a_git_checkout_is_unknown(monkeypatch, tmp_path):
    from owed import version
    monkeypatch.delenv('SPAN_VERSION', raising=False)
    monkeypatch.setattr(version, 'REPO', tmp_path)
    version.git_info.cache_clear()
    assert version.api_version() == 'unknown' and version.api_branch() == ''
    version.git_info.cache_clear()


def test_health_reports_version_and_branch(monkeypatch):
    from owed import db, version
    from owed.main import app
    monkeypatch.setattr(db, 'conn', lambda: nullcontext(SimpleNamespace(execute=lambda *a: None)))
    monkeypatch.delenv('SPAN_VERSION', raising=False)
    version.git_info.cache_clear()
    body = TestClient(app).get('/api/health').json()
    assert body['version'] == git('rev-parse', '--short', 'HEAD')
    assert body['branch'] == git('rev-parse', '--abbrev-ref', 'HEAD')
