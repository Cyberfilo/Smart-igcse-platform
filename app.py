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

    @app.before_request
    def _force_password_rotation():
        """If an authenticated user still has `must_change_password=True`
        (freshly issued OTP, not rotated yet), shove every request into
        the set-password form. Allow-list: the set-password route itself,
        logout, login, static, and media so cached images still render."""
        from flask import redirect, request, url_for
        from flask_login import current_user

        if not current_user.is_authenticated:
            return None
        if not getattr(current_user, "must_change_password", False):
            return None
        allowed = {
            "pages.set_password",
            "pages.logout",
            "pages.login",
            "pages.health",
            "static",
        }
        if request.endpoint in allowed:
            return None
        # Media is whitelisted because the set-password template may later
        # inline paper-diagram assets; harmless to allow now.
        if request.endpoint and request.endpoint.startswith("media."):
            return None
        return redirect(url_for("pages.set_password"))

    # Make `current_syllabus` + `available_syllabi` available in every template
    # so the topnav can render the switcher dropdown.
    @app.context_processor
    def inject_current_syllabus():
        from flask import session
        from flask_login import current_user

        from models import Syllabus

        syll = None
        available: list = []
        try:
            if current_user.is_authenticated and current_user.syllabus_id:
                syll = db.session.get(Syllabus, current_user.syllabus_id)
            else:
                code = session.get("syllabus_code")
                if code:
                    syll = Syllabus.query.filter_by(code=code).first()
            available = Syllabus.query.order_by(Syllabus.code).all()
        except Exception:
            pass
        return {"current_syllabus": syll, "available_syllabi": available}

    # Cache-bust the stylesheet + JS using file mtime — every Railway deploy
    # overwrites the files, changing mtime, which forces browser revalidation.
    @app.context_processor
    def inject_asset_version():
        static_root = app.static_folder
        try:
            css = int(os.path.getmtime(os.path.join(static_root, "css", "style.css")))
            js = int(os.path.getmtime(os.path.join(static_root, "js", "app.js")))
            return {"asset_v": {"css": css, "js": js}}
        except OSError:
            return {"asset_v": {"css": 0, "js": 0}}

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
