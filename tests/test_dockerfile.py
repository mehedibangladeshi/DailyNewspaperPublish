from pathlib import Path

DOCKERFILE_PATH = Path(__file__).parent.parent / "Dockerfile"


def test_dockerfile_exists():
    assert DOCKERFILE_PATH.exists()


def test_dockerfile_installs_runtime_requirements_and_runs_main():
    content = DOCKERFILE_PATH.read_text(encoding="utf-8")
    assert "COPY requirements.txt ." in content
    assert "pip install --no-cache-dir -r requirements.txt" in content
    assert 'CMD ["python", "main.py"]' in content
