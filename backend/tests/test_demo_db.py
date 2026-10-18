"""DB-free safety validation: no reset should accept a shared or remote database."""
import importlib.util
from pathlib import Path
import pytest
spec = importlib.util.spec_from_file_location('demo_db', Path(__file__).parents[1] / 'scripts/demo_db.py')
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)
@pytest.mark.parametrize('name', ['owed', 'postgres', 'span_demo_short', 'span_test_x;drop database owed'])
def test_refuses_unsafe_names(name):
    with pytest.raises(ValueError): demo.isolated_name(name)

def test_refuses_remote_url():
    with pytest.raises(ValueError): demo.local_url('postgresql://owed:owed@production.example/owed')

def test_exact_confirmation_before_connecting(monkeypatch):
    monkeypatch.setattr(demo.psycopg, 'connect', lambda *a, **k: pytest.fail('must not connect'))
    with pytest.raises(ValueError): demo.reset('postgresql://owed:owed@localhost:5433/span_test_safe123', 'owed')
