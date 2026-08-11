from pathlib import Path

WORKFLOW_PATH = Path(__file__).parent.parent / ".github" / "workflows" / "daily-kindle.yml"


def test_workflow_file_exists():
    assert WORKFLOW_PATH.exists()


def test_workflow_has_daily_schedule_and_manual_dispatch():
    content = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "cron: '0 2 * * *'" in content
    assert "workflow_dispatch:" in content


def test_workflow_runs_main_with_send_to_kindle_and_required_secrets():
    content = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "run: python main.py" in content
    assert "SEND_TO_KINDLE: 'true'" in content
    assert "GMAIL_ADDRESS: ${{ secrets.GMAIL_ADDRESS }}" in content
    assert "GMAIL_APP_PASSWORD: ${{ secrets.GMAIL_APP_PASSWORD }}" in content
    assert "KINDLE_EMAIL: ${{ secrets.KINDLE_EMAIL }}" in content


def test_workflow_uploads_epub_artifact_always():
    content = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "if: always()" in content
    assert "path: output/*.epub" in content
    assert "retention-days: 7" in content
