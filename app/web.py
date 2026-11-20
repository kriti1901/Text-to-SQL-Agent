"""Flask web UI and JSON API for the Text-to-SQL assistant."""

import hmac
import os
from dataclasses import asdict
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request

from . import agent, schema
from .db import ReadOnlyDB
from .llm import GroqLLM

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB = BASE_DIR / "data" / "northwind.db"
MAX_QUESTION_CHARS = 500


def load_credentials_from_env():
    """Read APP_USERNAME and APP_PASSWORD. Refuse to run without both."""
    username = os.environ.get("APP_USERNAME")
    password = os.environ.get("APP_PASSWORD")
    if not username or not password:
        raise RuntimeError(
            "Set APP_USERNAME and APP_PASSWORD before starting the server. "
            "The app will not run without authentication."
        )
    return username, password


def _credentials_match(auth, expected_user, expected_password):
    if auth is None or auth.username is None or auth.password is None:
        return False
    # compare_digest runs in constant time, which avoids leaking the password through timing.
    user_ok = hmac.compare_digest(auth.username.encode(), expected_user.encode())
    pass_ok = hmac.compare_digest(auth.password.encode(), expected_password.encode())
    return user_ok and pass_ok


def create_app(db_path=None, llm=None, credentials=None):
    if credentials is None:
        credentials = load_credentials_from_env()
    expected_user, expected_password = credentials

    db_path = str(db_path or os.environ.get("TEXT2SQL_DB", DEFAULT_DB))
    llm = llm or GroqLLM()
    tables = schema.load_tables(db_path)
    schema_text = schema.render(tables)
    db = ReadOnlyDB(db_path)

    app = Flask(
        __name__,
        template_folder=str(BASE_DIR / "templates"),
    )

    @app.before_request
    def require_login():
        if not _credentials_match(request.authorization, expected_user, expected_password):
            return Response(
                "Authentication required.",
                401,
                {"WWW-Authenticate": 'Basic realm="Text-to-SQL Agent"'},
            )
        return None

    @app.get("/")
    def index():
        return render_template("index.html", table_names=list(tables.keys()))

    @app.post("/api/ask")
    def ask():
        payload = request.get_json(silent=True) or {}
        question = (payload.get("question") or "").strip()
        if not question:
            return jsonify({"error": "Please enter a question."}), 400
        if len(question) > MAX_QUESTION_CHARS:
            return jsonify({"error": f"Question is too long (max {MAX_QUESTION_CHARS} chars)."}), 400

        try:
            result = agent.answer_question(
                question, db=db, llm=llm, tables=tables, schema_text=schema_text
            )
        except Exception as e:  # LLM outage, network, etc.
            return jsonify({"error": f"The assistant failed: {e}"}), 502

        body = asdict(result)
        body["attempts"] = [asdict(a) for a in result.attempts]
        return jsonify(body)

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")), debug=False)
