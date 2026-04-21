"""Application factory + module-level `app` for gunicorn."""
import logging
import os
import sys

from flask import Flask

from config import Config
from extensions import db, login_manager, migrate


def create_app(config_class: type = Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_class)

    config_class.validate()

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    # Import models so Flask-Migrate's autogenerate sees every table.
    import models  # noqa: F401

    for path in (app.config["UPLOAD_DIR"], app.config["PAST_PAPERS_DIR"]):
        try:
            os.makedirs(path, exist_ok=True)
        except OSError:
            app.logger.warning("Data dir %s not writable on startup", path)

    _configure_logging(app)

    # Register blueprints. Deferred import — routes.* import services and models,
    # both of which need the extension singletons live already.
    from routes import ALL_BLUEPRINTS

    for bp in ALL_BLUEPRINTS:
        app.register_blueprint(bp)

    # Make `current_syllabus` available in every template so the topnav can
    # show which syllabus the user is on.
    @app.context_processor
    def inject_current_syllabus():
        from flask import session
        from flask_login import current_user

        from models import Syllabus

        syll = None
        try:
            if current_user.is_authenticated and current_user.syllabus_id:
                syll = db.session.get(Syllabus, current_user.syllabus_id)
            else:
                code = session.get("syllabus_code")
                if code:
                    syll = Syllabus.query.filter_by(code=code).first()
        except Exception:
            syll = None
        return {"current_syllabus": syll}

    return app


def _configure_logging(app: Flask) -> None:
    """Structured-ish logging (Phase 8 leaves it line-based until a real JSON
    formatter is justified). Logs go to stdout so Railway collects them."""
    if app.config.get("FLASK_ENV") == "testing":
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO if not app.config.get("DEBUG") else logging.DEBUG)


app = create_app()


if __name__ == "__main__":
    app.run(debug=app.config["DEBUG"], host="0.0.0.0", port=5000)
