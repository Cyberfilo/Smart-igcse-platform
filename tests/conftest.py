"""Test-time environment setup. Uses SQLite in-memory — the /health `SELECT 1`
probe works on any DB, and create_all() materialises tables for routes that
query real models. Railway prod always runs Postgres."""
import pytest


@pytest.fixture(autouse=True)
def _test_env(monkeypatch, tmp_path):
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("PAST_PAPERS_DIR", str(tmp_path / "papers"))
    monkeypatch.setenv("FLASK_ENV", "testing")


@pytest.fixture
def app():
    from importlib import reload

    import config

    reload(config)
    from app import create_app
    from extensions import db

    app = create_app(config.Config)
    with app.app_context():
        db.create_all()
    yield app


@pytest.fixture
def client(app):
    return app.test_client()
