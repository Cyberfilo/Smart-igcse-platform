"""Blueprint registration point. Importing blueprints here lets app.py stay
oblivious to individual route modules."""
from routes.admin import admin_bp
from routes.api import api_bp
from routes.media import media_bp
from routes.pages import pages_bp
from routes.prototype import prototype_bp

ALL_BLUEPRINTS = (pages_bp, api_bp, admin_bp, media_bp, prototype_bp)
