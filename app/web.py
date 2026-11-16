"""Flask web UI and JSON API for the Text-to-SQL assistant."""

import os
from dataclasses import asdict
from pathlib import Path

from flask import Flask, jsonify, render_template, request

from . import agent, schema
from .db import ReadOnlyDB
from .llm import GroqLLM

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB = BASE_DIR / "data" / "northwind.db"
MAX_QUESTION_CHARS = 500


def create_app(db_path=None, llm=None):
    db_path = str(db_path or os.environ.get("TEXT2SQL_DB", DEFAULT_DB))
    llm = llm or GroqLLM()
    tables = schema.load_tables(db_path)
    schema_text = schema.render(tables)
    db = ReadOnlyDB(db_path)

    app = Flask(
        __name__,
        template_folder=str(BASE_DIR / "templates"),
    )

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
