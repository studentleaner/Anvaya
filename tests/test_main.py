import httpx
from fastapi.testclient import TestClient

from anvaya_api.abstractai import AbstractAIClient
from anvaya_api.config import Settings
from anvaya_api.main import create_app


def client_for(settings, handler):
    ai = AbstractAIClient(settings, transport=httpx.MockTransport(handler))
    return TestClient(create_app(settings, ai))


def gateway(request):
    if request.url.path == "/openapi.json":
        return httpx.Response(200, json={})
    if request.url.path == "/token":
        return httpx.Response(200, json={"access_token": "t", "token_type": "bearer"})
    return httpx.Response(404)


def test_healthz():
    assert client_for(Settings(), gateway).get("/healthz").json()["ok"] is True


def test_status_ok():
    body = client_for(Settings(username="a", password="b"), gateway).get("/api/status").json()
    assert body["gateway"] == "up" and body["auth"] == "ok"
    assert body["local_only"] is True and body["provider"] == "ollama"
    assert body["model"] == {"name": "llama3.1:8b", "state": "unknown"} and body["plugins"] == []


def test_status_not_configured():
    assert client_for(Settings(), gateway).get("/api/status").json()["auth"] == "not_configured"


def test_status_gateway_down_reports_unknown_auth():
    def down(request):
        raise httpx.ConnectError("refused")

    body = client_for(Settings(username="a", password="b"), down).get("/api/status").json()
    assert body["gateway"] == "down" and body["auth"] == "unknown"


def test_status_auth_failed():
    def bad_login(request):
        if request.url.path == "/openapi.json":
            return httpx.Response(200, json={})
        return httpx.Response(401)

    assert client_for(Settings(username="a", password="b"), bad_login).get("/api/status").json()["auth"] == "failed"


def test_module_level_app_exists():
    from anvaya_api.main import app
    assert app.title == "Anvaya API"
