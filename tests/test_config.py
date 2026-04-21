import pytest


def test_postgres_url_normalised(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgres://u:p@h:5432/d")
    from importlib import reload

    import config

    reload(config)
    assert config.Config.SQLALCHEMY_DATABASE_URI.startswith("postgresql://")


def test_validate_raises_on_missing_vars_in_prod(monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "")
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    from importlib import reload

    import config

    reload(config)
    with pytest.raises(RuntimeError, match="Missing required env vars"):
        config.Config.validate()


def test_validate_noop_in_dev(monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "development")
    monkeypatch.setenv("SECRET_KEY", "")
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    from importlib import reload

    import config

    reload(config)
    config.Config.validate()
