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
    assert "docker build -t daily-newspaper ." in content
    assert "docker run --rm" in content
    assert "-e SEND_TO_KINDLE=true" in content
    assert "GMAIL_ADDRESS=\"$GMAIL_ADDRESS\"" in content
    assert "GMAIL_ADDRESS: ${{ secrets.GMAIL_ADDRESS }}" in content
    assert "GMAIL_APP_PASSWORD: ${{ secrets.GMAIL_APP_PASSWORD }}" in content
    assert "KINDLE_EMAIL: ${{ secrets.KINDLE_EMAIL }}" in content


def test_workflow_runs_on_self_hosted_runner():
    content = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "runs-on: [self-hosted, Linux]" in content


def test_workflow_uploads_epub_artifact_always():
    content = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "if: always()" in content
    assert "path: output/*.epub" in content
    assert "retention-days: 7" in content


def test_workflow_has_write_permission_for_gh_pages_publish():
    content = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "contents: write" in content


def test_workflow_checks_out_gh_pages_branch_only_if_it_exists():
    content = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "ref: gh-pages" in content
    assert "git ls-remote --exit-code --heads origin gh-pages" in content
    assert "steps.gh_pages_exists.outputs.exists == 'true'" in content
    # an ambiguous ls-remote result (network/auth error, not "no such branch")
    # must not be treated as "branch absent" - see the exists=unknown branch
    assert 'echo "exists=unknown" >> "$GITHUB_OUTPUT"' in content
    # a transient checkout failure of an existing branch must not fail the
    # whole job (that would block Kindle delivery too) - the publish step's
    # own outcome==success check is what keeps a failed checkout from
    # publishing, not this job-level continue-on-error
    assert "continue-on-error: true" in content


def test_workflow_runs_main_with_opds_env_vars():
    content = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "-e PUBLISH_OPDS=true" in content
    assert "GH_PAGES_DIR: gh-pages-checkout" in content


def test_workflow_publishes_to_gh_pages_with_keep_files_false_and_force_orphan():
    content = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "uses: peaceiris/actions-gh-pages@" in content
    assert "keep_files: false" in content
    assert "force_orphan: true" in content


def test_workflow_publish_step_gated_on_checkout_outcome():
    content = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "steps.gh_pages_exists.outputs.exists == 'false' || steps.gh_pages_checkout.outcome == 'success'" in content
