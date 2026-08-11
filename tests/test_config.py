import importlib

import pytest

from jugantor_epub import config


@pytest.fixture(autouse=True)
def _reload_config_after_test():
    yield
    importlib.reload(config)


def test_send_to_kindle_defaults_false_when_env_unset(monkeypatch):
    monkeypatch.delenv("SEND_TO_KINDLE", raising=False)
    importlib.reload(config)
    assert config.SEND_TO_KINDLE is False


def test_send_to_kindle_true_when_env_set_true(monkeypatch):
    monkeypatch.setenv("SEND_TO_KINDLE", "true")
    importlib.reload(config)
    assert config.SEND_TO_KINDLE is True


def test_send_to_kindle_case_insensitive(monkeypatch):
    monkeypatch.setenv("SEND_TO_KINDLE", "TRUE")
    importlib.reload(config)
    assert config.SEND_TO_KINDLE is True


def test_kindle_credentials_read_from_env(monkeypatch):
    monkeypatch.setenv("KINDLE_EMAIL", "me@kindle.com")
    monkeypatch.setenv("GMAIL_ADDRESS", "sender@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "app-password")
    importlib.reload(config)
    assert config.KINDLE_EMAIL == "me@kindle.com"
    assert config.GMAIL_ADDRESS == "sender@gmail.com"
    assert config.GMAIL_APP_PASSWORD == "app-password"


def test_kindle_credentials_default_none_when_unset(monkeypatch):
    monkeypatch.delenv("KINDLE_EMAIL", raising=False)
    monkeypatch.delenv("GMAIL_ADDRESS", raising=False)
    monkeypatch.delenv("GMAIL_APP_PASSWORD", raising=False)
    importlib.reload(config)
    assert config.KINDLE_EMAIL is None
    assert config.GMAIL_ADDRESS is None
    assert config.GMAIL_APP_PASSWORD is None
