"""CORS origins: the local dev server is always allowed; deployed origins come from CORS_ORIGINS."""

from backend.main import DEV_ORIGINS, cors_origins


def test_defaults_to_the_local_dev_server(monkeypatch):
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    assert cors_origins() == DEV_ORIGINS


def test_adds_deployed_origins_from_the_environment(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", " https://app.example.com/ ,https://b.example.com,, http://localhost:5173")
    assert cors_origins() == DEV_ORIGINS + ["https://app.example.com", "https://b.example.com"]
