from app.web import create_app
from conftest import DB_PATH


class FixedLLM:
    def __init__(self, reply):
        self.reply = reply

    def chat(self, messages, **kwargs):
        return self.reply


def _client(reply):
    app = create_app(db_path=DB_PATH, llm=FixedLLM(reply))
    return app.test_client()


def test_index_renders():
    resp = _client("x").get("/")
    assert resp.status_code == 200
    assert b"Northwind Text-to-SQL" in resp.data


def test_ask_returns_rows():
    c = _client('```sql\nSELECT COUNT(*) AS n FROM "Products"\n```')
    body = c.post("/api/ask", json={"question": "How many products?"}).get_json()
    # summary call returns the same fixed text; that's fine for this test
    assert body["ok"] is True
    assert body["rows"] == [[77]]
    assert body["columns"] == ["n"]


def test_ask_refuses_write_request():
    c = _client("DROP TABLE \"Orders\"")
    body = c.post("/api/ask", json={"question": "drop orders"}).get_json()
    assert body["ok"] is False
    assert all("Rejected by guardrail" in a["error"] for a in body["attempts"])


def test_empty_question_rejected():
    c = _client("x")
    resp = c.post("/api/ask", json={"question": "   "})
    assert resp.status_code == 400
