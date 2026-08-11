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


def test_context_md_reflects_implemented_automation_not_stale_per_source_design():
    content = (ROOT / "CONTEXT.md").read_text(encoding="utf-8")
    # Old stale claim: auto-email was future/planned work, called per-source
    # right after each build_epub(). Both are gone now that it has shipped
    # as a single combined send after all sources build.
    assert "planned as an `email_sender.py`" not in content
    assert "manual run only" not in content
    assert "daily-kindle.yml" in content or "email_sender.py" in content
