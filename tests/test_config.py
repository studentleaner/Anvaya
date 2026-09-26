from pathlib import Path

from anvaya_api.config import LOCAL_PROVIDER, Settings


def test_defaults_are_local_and_safe():
    s = Settings.from_env({})
    assert s.gateway_url == "http://abstractai-gateway:8000"
    assert s.project_id == "anvaya" and s.primary_model == "qwen2.5:7b"
    assert s.data_dir == Path("/data") and s.request_timeout_s == 240.0
    assert not s.has_credentials
    assert LOCAL_PROVIDER == "ollama"


def test_env_overrides_and_trailing_slash_stripped():
    s = Settings.from_env({
        "ANVAYA_ABSTRACTAI_URL": "http://x:1/", "ANVAYA_ABSTRACTAI_USER": "u", "ANVAYA_ABSTRACTAI_PASSWORD": "p",
        "ANVAYA_PROJECT_ID": "p2", "ANVAYA_PRIMARY_MODEL": "llama3.1:8b", "ANVAYA_DATA_DIR": "/tmp/a",
        "ANVAYA_REQUEST_TIMEOUT_S": "12.5"})
    assert s.gateway_url == "http://x:1" and s.has_credentials
    assert (s.project_id, s.primary_model, s.request_timeout_s) == ("p2", "llama3.1:8b", 12.5)
    assert s.data_dir == Path("/tmp/a")


def test_from_env_reads_process_environment(monkeypatch):
    monkeypatch.setenv("ANVAYA_PROJECT_ID", "from-os")
    assert Settings.from_env().project_id == "from-os"
