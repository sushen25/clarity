from __future__ import annotations

import os
from pathlib import Path

from flask import Flask, jsonify, send_from_directory

from .auth import auth_bp, init_auth
from .cases import cases_bp
from .config import Config
from .db import close_db, init_db


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__, static_folder=None)
    app.config.from_object(Config())
    if test_config:
        app.config.update(test_config)
    if not app.config.get("TESTING") and app.config["SECRET_KEY"] == "development-only-change-me-please":
        raise RuntimeError("SECRET_KEY must be set to a unique random value before the application starts.")

    Path(app.config["DATABASE_PATH"]).parent.mkdir(parents=True, exist_ok=True)
    Path(app.config["STORAGE_ROOT"]).mkdir(parents=True, exist_ok=True)
    app.teardown_appcontext(close_db)
    init_auth(app)
    app.register_blueprint(auth_bp)
    app.register_blueprint(cases_bp)

    with app.app_context():
        init_db()

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok"})

    @app.get("/")
    @app.get("/<path:path>")
    def frontend(path: str = "index.html"):
        dist = Path(app.root_path).parent / "frontend" / "dist"
        requested = dist / path
        if requested.is_file():
            return send_from_directory(dist, path)
        if (dist / "index.html").is_file():
            return send_from_directory(dist, "index.html")
        return jsonify({"message": "Frontend not built", "api": "/api/health"}), 200

    return app


if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
