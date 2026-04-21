"""Uninitialised Flask extension singletons. init_app() is called in create_app()."""
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()

login_manager.login_view = "pages.login"
login_manager.login_message_category = "info"


@login_manager.user_loader
def _load_user(user_id):
    # Lazy import to avoid circular dependency (models imports db from this module).
    from models import User

    try:
        return db.session.get(User, int(user_id))
    except (ValueError, TypeError):
        return None
