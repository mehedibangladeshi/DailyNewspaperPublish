from pathlib import Path

WORKFLOW_PATH = Path(__file__).parent.parent / ".github" / "workflows" / "daily-kindle-fallback.yml"


def test_fallback_workflow_file_exists():
    assert WORKFLOW_PATH.exists()


def test_fallback_workflow_runs_on_hosted_runner_with_buffer_schedule():
    content = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "runs-on: ubuntu-latest" in content
    assert "cron: '0 4 * * *'" in content
    assert "workflow_dispatch:" in content


def test_fallback_workflow_has_its_own_concurrency_group():
    content = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "group: daily-kindle-fallback" in content


def test_fallback_workflow_guard_checks_todays_primary_run_success():
    content = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "gh run list" in content
    assert "--workflow daily-kindle.yml" in content
    # the jq filter is embedded inside a bash double-quoted string, so the
    # literal file content has escaped quotes around "success", not bare ones
    assert '.conclusion == \\"success\\"' in content
    assert "already_succeeded=true" in content
    assert "already_succeeded=false" in content


def test_fallback_workflow_dedups_via_send_status_and_source_flag():
    content = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "send-status/$TODAY.json?ref=gh-pages" in content
    assert "from jugantor_epub import config, send_tracker" in content
    assert "send_tracker.missing_source_args(sent)" in content
    assert "missing_sources" in content
    assert "python main.py ${{ steps.dedup.outputs.missing_sources }}" in content


def test_fallback_workflow_forwards_required_secrets_and_env():
    content = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "GMAIL_ADDRESS: ${{ secrets.GMAIL_ADDRESS }}" in content
    assert "GMAIL_APP_PASSWORD: ${{ secrets.GMAIL_APP_PASSWORD }}" in content
    assert "KINDLE_EMAIL: ${{ secrets.KINDLE_EMAIL }}" in content
    assert "GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}" in content
    assert "SEND_TO_KINDLE: 'true'" in content
    assert "PUBLISH_OPDS: 'true'" in content


def test_fallback_workflow_publishes_gh_pages_same_as_primary():
    content = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "uses: peaceiris/actions-gh-pages@" in content
    assert "keep_files: false" in content
    assert "force_orphan: true" in content


def test_fallback_workflow_gates_build_steps_on_the_guard():
    content = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert content.count("steps.guard.outputs.already_succeeded == 'false'") == 10
