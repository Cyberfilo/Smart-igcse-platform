"""Env-var-driven config. All runtime toggles live here."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")


def _normalise_db_url(url: str) -> str:
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql://", 1)
    return url


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "")

    SQLALCHEMY_DATABASE_URI = _normalise_db_url(os.environ.get("DATABASE_URL", ""))
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

    UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "/data/student-uploads")
    PAST_PAPERS_DIR = os.environ.get("PAST_PAPERS_DIR", "/data/past-papers")

    FLASK_ENV = os.environ.get("FLASK_ENV", "production")
    DEBUG = FLASK_ENV == "development"

    @classmethod
    def required_in_prod(cls) -> dict[str, str]:
        return {
            "SECRET_KEY": cls.SECRET_KEY,
            "DATABASE_URL": cls.SQLALCHEMY_DATABASE_URI,
            "OPENAI_API_KEY": cls.OPENAI_API_KEY,
        }

    @classmethod
    def validate(cls) -> None:
        if cls.FLASK_ENV != "production":
            return
        missing = [k for k, v in cls.required_in_prod().items() if not v]
        if missing:
            raise RuntimeError(
                f"Missing required env vars in production: {missing}. "
                "Set them on Railway → App → Variables (see RAILWAY.md §4)."
            )
