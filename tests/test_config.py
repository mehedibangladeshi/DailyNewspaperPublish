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


def test_gmail_app_password_strips_spaces_and_nbsp(monkeypatch):
    # Google's App Password page groups digits with spaces, and copying
    # from that page can grab a non-breaking space (\xa0) instead of a
    # regular one - both must be stripped or smtplib's ASCII-only
    # credential encoding crashes.
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "abcd\xa0efgh ijkl mnop")
    importlib.reload(config)
    assert config.GMAIL_APP_PASSWORD == "abcdefghijklmnop"


def test_kindle_email_and_gmail_address_strip_whitespace(monkeypatch):
    monkeypatch.setenv("KINDLE_EMAIL", " me@kindle.com\xa0")
    monkeypatch.setenv("GMAIL_ADDRESS", "\xa0sender@gmail.com ")
    importlib.reload(config)
    assert config.KINDLE_EMAIL == "me@kindle.com"
    assert config.GMAIL_ADDRESS == "sender@gmail.com"


def test_publish_opds_defaults_false_when_env_unset(monkeypatch):
    monkeypatch.delenv("PUBLISH_OPDS", raising=False)
    importlib.reload(config)
    assert config.PUBLISH_OPDS is False


def test_publish_opds_true_when_env_set_true(monkeypatch):
    monkeypatch.setenv("PUBLISH_OPDS", "true")
    importlib.reload(config)
    assert config.PUBLISH_OPDS is True


def test_publish_opds_case_insensitive(monkeypatch):
    monkeypatch.setenv("PUBLISH_OPDS", "TRUE")
    importlib.reload(config)
    assert config.PUBLISH_OPDS is True


def test_gh_pages_dir_defaults_to_gh_pages_checkout(monkeypatch):
    monkeypatch.delenv("GH_PAGES_DIR", raising=False)
    importlib.reload(config)
    assert config.GH_PAGES_DIR == "gh-pages-checkout"


def test_gh_pages_dir_read_from_env(monkeypatch):
    monkeypatch.setenv("GH_PAGES_DIR", "/custom/path")
    importlib.reload(config)
    assert config.GH_PAGES_DIR == "/custom/path"


def test_opds_retention_count_is_fixed():
    assert config.OPDS_RETENTION_COUNT == 7
