"""Manual source-only migration check; downloads dependencies, never calls a model."""

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    output = ROOT / "logs/refactor"
    output.mkdir(parents=True, exist_ok=True)
    workspace = Path(tempfile.mkdtemp(prefix="clean-install-", dir=output)).resolve()
    report = {"paid_model_calls": 0, "source_only": True}
    try:
        for name in ("backend", "frontend", "packages", "scripts", ".streamlit"):
            shutil.copytree(
                ROOT / name,
                workspace / name,
                ignore=shutil.ignore_patterns("__pycache__", "*.egg-info", ".venv*"),
            )
        for name in ("README.md", "pyproject.toml", "uv.lock", ".env.example", ".python-version"):
            shutil.copy2(ROOT / name, workspace / name)
        # No copied .env, local DB, virtual environment, tests, or user credentials.
        env = {
            key: value
            for key, value in os.environ.items()
            if key.upper()
            in {
                "PATH",
                "PATHEXT",
                "SYSTEMROOT",
                "WINDIR",
                "TEMP",
                "TMP",
                "USERPROFILE",
                "APPDATA",
                "LOCALAPPDATA",
                "COMSPEC",
                "SYSTEMDRIVE",
            }
        }
        env["PYTHONIOENCODING"] = "utf-8"

        def run(args):
            result = subprocess.run(
                args,
                cwd=workspace,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=300,
            )
            with (output / "clean_install.log").open("a", encoding="utf-8") as log:
                log.write(result.stdout + result.stderr)
            if result.returncode:
                raise RuntimeError(
                    f"Clean installation failed at {args[0]} (see clean_install.log)"
                )
            return result.stdout

        run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "scripts/setup.ps1"]
        )
        backend = str(workspace / ".venv-backend/Scripts/python.exe")
        frontend = str(workspace / ".venv-frontend/Scripts/python.exe")
        assert (workspace / ".env").read_bytes() == (workspace / ".env.example").read_bytes()
        run([backend, "scripts/seed_demo.py"])
        report["first_seed_created"] = (workspace / "data/componentmatch.db").is_file()
        report["repeat_seed_unchanged"] = '"action": "unchanged"' in run(
            [backend, "scripts/seed_demo.py"]
        )
        backend_probe = run(
            [
                backend,
                "-I",
                "-c",
                "import importlib.util as u; import componentmatch.api.main; "
                "assert u.find_spec('componentmatch_frontend') is None; "
                "assert u.find_spec('streamlit') is None",
            ]
        )
        run(
            [
                frontend,
                "-I",
                "-c",
                "import importlib.util as u; import componentmatch_frontend.app; "
                "assert u.find_spec('componentmatch') is None; "
                "assert u.find_spec('sqlalchemy') is None; assert u.find_spec('langgraph') is None",
            ]
        )
        report["isolated_package_imports"] = backend_probe == ""
        run([backend, "scripts/demo_match.py"])
        report["deterministic_scenarios"] = True
        text = run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                "scripts/start_demo.ps1",
                "-SmokeTest",
                "-ApiPort",
                "18013",
                "-UiPort",
                "18513",
            ]
        )
        report["api_and_frontend_started"] = "18513" in text
        report["status"] = "passed"
    finally:
        # Only remove this script's freshly generated directory, verified inside its output folder.
        if workspace.parent != output.resolve() or not workspace.name.startswith("clean-install-"):
            raise RuntimeError("Refusing to clean an unexpected path")
        shutil.rmtree(workspace)
        (output / "clean_install.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
