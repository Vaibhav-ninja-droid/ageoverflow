# makes application a package

from flask import Flask
from application.routes import api
from application.db import init_db

def create_app(config_overrides=None):
    app = Flask(__name__)
    app.config["JSON_SORT_KEYS"] = False

    if config_overrides:
        app.config.update(config_overrides)

    init_db()
    app.register_blueprint(api)
    return app

app = create_app()