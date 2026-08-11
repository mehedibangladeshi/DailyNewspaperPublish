from pathlib import Path

ROOT = Path(__file__).parent.parent


def test_readme_documents_kindle_delivery_not_deferred():
    content = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Daily Kindle delivery" in content
    assert "Not implemented yet" not in content


def test_claude_md_deferred_section_reflects_implemented_automation():
    content = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    assert "daily-kindle.yml" in content
    assert "email_sender.py" in content
