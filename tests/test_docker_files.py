"""Static checks for the Docker, Compose and packaging files. They need no Docker daemon."""

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_dockerfile_never_copies_the_whole_context():
    assert "COPY . ." not in (ROOT / "Dockerfile").read_text(encoding="utf-8")


def test_pip_installs_use_the_cache_mount_and_not_pip_no_cache_dir():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "PIP_NO_CACHE_DIR" not in dockerfile
    # Join the continuation lines so that each RUN instruction is one line.
    instructions = dockerfile.replace("\\\n", " ").splitlines()
    pip_lines = [line for line in instructions if "pip install" in line]
    assert pip_lines, "the Dockerfile has no pip install"
    mount = "RUN --mount=type=cache,target=/root/.cache/pip "
    assert all(line.startswith(mount) for line in pip_lines), pip_lines
    assert "torch==2.14.1 torchvision==0.29.1" in dockerfile


def test_runtime_venv_drops_test_folders_pip_and_setuptools_after_the_install():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    builder, runtime = dockerfile.split("AS runtime", 1)
    install = builder.index("pip install --no-deps .")
    prune = (
        "find /opt/venv/lib/python3.11/site-packages -type d -name tests -prune -exec rm -rf {} +"
    )
    uninstall = "python -m pip uninstall -y pip setuptools"
    assert prune in builder
    assert builder.index(prune) > install
    assert uninstall in builder
    assert builder.index(uninstall) > install
    assert "|| true" not in dockerfile
    assert "COPY --from=builder /opt/venv /opt/venv" in runtime
    # The removal must not touch the consultqa package: its name is not in the cleanup line
    # and the package source has no tests folder that the find could delete.
    assert "consultqa" not in prune
    assert not [path for path in (ROOT / "src" / "consultqa").rglob("tests") if path.is_dir()]


def test_images_are_pinned():
    text = (ROOT / "compose.yml").read_text(encoding="utf-8")
    assert ":latest" not in text
    assert "image: qdrant/qdrant:" in text


def test_base_image_is_pinned_to_an_exact_version():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    bases = re.findall(r"^FROM\s+(\S+)", dockerfile, flags=re.MULTILINE)
    assert bases, "the Dockerfile has no FROM line"
    assert all(re.fullmatch(r"python:3\.11\.\d+-slim-[a-z]+", base) for base in bases), bases


def test_dockerignore_is_an_allowlist():
    lines = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    rules = [line.strip() for line in lines if line.strip() and not line.startswith("#")]
    assert rules[0] == "*"


def test_page_is_copied_into_the_image_and_found_through_the_environment():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY frontend /app/frontend" in dockerfile
    assert "CONSULTQA_FRONTEND_DIR=/app/frontend" in dockerfile
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert "consultqa.api" not in pyproject["tool"]["setuptools"]["package-data"]


def test_dockerignore_allows_the_frontend_folder():
    lines = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    assert "!frontend/" in [line.strip() for line in lines]


def test_app_healthcheck_waits_for_the_models():
    compose = (ROOT / "compose.yml").read_text(encoding="utf-8")
    assert "http://127.0.0.1:8000/api/ready" in compose
    assert "/api/health'" not in compose


def test_health_checks_poll_every_second_during_their_start_period():
    import yaml

    compose = yaml.safe_load((ROOT / "compose.yml").read_text(encoding="utf-8"))
    for name in ("app", "qdrant"):
        healthcheck = compose["services"][name]["healthcheck"]
        # start_interval applies only inside start_period, so both are needed for the 1 s polling.
        assert healthcheck["start_interval"] == "1s", name
        assert "start_period" in healthcheck, name
    assert compose["services"]["app"]["healthcheck"]["test"][-1].endswith("/api/ready', timeout=5)")


def test_llm_api_key_is_passed_through_to_the_app():
    compose = (ROOT / "compose.yml").read_text(encoding="utf-8")
    assert "CONSULTQA_LLM_API_KEY: ${CONSULTQA_LLM_API_KEY:-}" in compose


def test_ci_grants_read_only_token_permissions_and_runs_qdrant():
    import yaml

    ci = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
    assert ci["permissions"] == {"contents": "read"}
    lint_test = ci["jobs"]["lint-test"]
    assert lint_test["services"]["qdrant"]["image"].startswith("qdrant/qdrant:")
    assert ":latest" not in lint_test["services"]["qdrant"]["image"]
    tests_step = next(step for step in lint_test["steps"] if step.get("name") == "Tests")
    assert tests_step["env"]["CONSULTQA_QDRANT_URL"] == "http://localhost:6333"


def test_lint_job_installs_only_ruff_and_runs_both_ruff_checks():
    import yaml

    ci = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
    runs = [step["run"] for step in ci["jobs"]["lint"]["steps"] if "run" in step]
    assert "ruff check ." in runs and "ruff format --check ." in runs, runs
    installs = [run for run in runs if "install" in run]
    assert len(installs) == 1 and re.fullmatch(r"pip install ruff==\S+", installs[0]), installs
    text = " ".join(runs)
    assert ".[" not in text and "torch" not in text, text


def test_tests_job_keys_the_pip_cache_on_pyproject():
    import yaml

    ci = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
    steps = ci["jobs"]["lint-test"]["steps"]
    setup = next(step for step in steps if step.get("uses", "").startswith("actions/setup-python@"))
    assert setup["with"]["cache"] == "pip"
    assert setup["with"]["cache-dependency-path"] == "pyproject.toml"


def test_compose_smoke_builds_the_image_with_the_gha_cache_before_compose_up():
    import yaml

    ci = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
    steps = ci["jobs"]["compose-smoke"]["steps"]
    uses = [step.get("uses", "") for step in steps]
    build_index = next(
        i for i, use in enumerate(uses) if use.startswith("docker/build-push-action@")
    )
    assert any(use.startswith("docker/setup-buildx-action@") for use in uses[:build_index])
    build = steps[build_index]["with"]
    assert build["cache-from"] == "type=gha"
    assert build["cache-to"] == "type=gha,mode=max"
    assert build["load"] is True and build["tags"] == "consultqa:dev"
    up_index = next(i for i, step in enumerate(steps) if "docker compose up" in step.get("run", ""))
    assert build_index < up_index


def test_compose_smoke_asks_a_question_not_only_health():
    import yaml

    ci = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
    script = "\n".join(step.get("run", "") for step in ci["jobs"]["compose-smoke"]["steps"])
    assert "/documents" in script and "/jobs/" in script and "/ask" in script


def test_compose_smoke_checks_the_page_and_the_capabilities():
    import yaml

    ci = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
    script = "\n".join(step.get("run", "") for step in ci["jobs"]["compose-smoke"]["steps"])
    assert "/js/main.js" in script and "/api/capabilities" in script


def test_ci_and_conda_env_install_the_core_extra():
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    environment = (ROOT / "environment.yml").read_text(encoding="utf-8")
    assert ".[core,ml,pdf,api,dev]" in ci
    assert ".[core,ml,pdf,api,dev,e2e]" in environment


def test_requires_python_matches_the_code():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["requires-python"] == ">=3.11"


def test_dockerignore_does_not_send_the_sample_data():
    lines = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    rules = [line.strip() for line in lines if line.strip() and not line.strip().startswith("#")]
    assert not any(rule.startswith("!data") for rule in rules), rules
