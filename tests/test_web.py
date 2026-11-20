import base64

import pytest

from app.web import create_app, load_credentials_from_env
from conftest import DB_PATH

USER = "tester"
PASSWORD = "correct-horse-battery"


class FixedLLM:
    def __init__(self, reply):
        self.reply = reply

    def chat(self, messages, **kwargs):
        return self.reply


def _basic(user, password):
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def _client(reply):
    app = create_app(db_path=DB_PATH, llm=FixedLLM(reply), credentials=(USER, PASSWORD))
    return app.test_client(), _basic(USER, PASSWORD)


def test_index_renders():
    c, auth = _client("x")
    resp = c.get("/", headers=auth)
    assert resp.status_code == 200
    assert b"Northwind Text-to-SQL" in resp.data


def test_ask_returns_rows():
    c, auth = _client('```sql\nSELECT COUNT(*) AS n FROM "Products"\n```')
    body = c.post("/api/ask", json={"question": "How many products?"}, headers=auth).get_json()
    assert body["ok"] is True
    assert body["rows"] == [[77]]
    assert body["columns"] == ["n"]


def test_ask_refuses_write_request():
    c, auth = _client("DROP TABLE \"Orders\"")
    body = c.post("/api/ask", json={"question": "list orders"}, headers=auth).get_json()
    assert body["ok"] is False
    assert all("Rejected by guardrail" in a["error"] for a in body["attempts"])


def test_empty_question_rejected():
    c, auth = _client("x")
    resp = c.post("/api/ask", json={"question": "   "}, headers=auth)
    assert resp.status_code == 400


@pytest.mark.parametrize("headers", [
    {},
    _basic(USER, "wrong-password"),
    _basic("someone-else", PASSWORD),
])
def test_requests_without_valid_credentials_are_rejected(headers):
    c, _ = _client("x")
    assert c.get("/", headers=headers).status_code == 401
    assert c.post("/api/ask", json={"question": "hi"}, headers=headers).status_code == 401


def test_401_asks_browser_for_credentials():
    c, _ = _client("x")
    resp = c.get("/")
    assert resp.status_code == 401
    assert resp.headers["WWW-Authenticate"].startswith("Basic")


def test_app_refuses_to_start_without_env_credentials(monkeypatch):
    monkeypatch.delenv("APP_USERNAME", raising=False)
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    with pytest.raises(RuntimeError, match="APP_USERNAME"):
        load_credentials_from_env()


def test_env_credentials_are_used(monkeypatch):
    monkeypatch.setenv("APP_USERNAME", "envuser")
    monkeypatch.setenv("APP_PASSWORD", "envpass")
    assert load_credentials_from_env() == ("envuser", "envpass")
