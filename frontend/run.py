"""Standalone frontend launcher: standard library and frontend dependencies only."""

import argparse
import os
import sys
from pathlib import Path

from componentmatch_frontend.api_client import UIConfig

ROOT = Path(__file__).resolve().parents[1]


def frontend_environment(source, api_port=None):
    allowed = {
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "WINDIR",
        "SYSTEMDRIVE",
        "COMSPEC",
        "TEMP",
        "TMP",
        "USERPROFILE",
        "HOME",
        "APPDATA",
        "LOCALAPPDATA",
        "LANG",
        "LC_ALL",
        "COMPONENTMATCH_API_URL",
        "COMPONENTMATCH_HTTP_TIMEOUT_SECONDS",
    }
    env = {key: value for key, value in source.items() if key.upper() in allowed}
    if api_port is not None:
        env["COMPONENTMATCH_API_URL"] = f"http://127.0.0.1:{api_port}"
    env.update(PYTHONIOENCODING="utf-8", STREAMLIT_BROWSER_GATHER_USAGE_STATS="false")
    return env


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8501)
    parser.add_argument("--api-url", default=os.getenv("COMPONENTMATCH_API_URL", UIConfig.api_url))
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("port must be between 1024 and 65535")
    env = frontend_environment(os.environ)
    env["COMPONENTMATCH_API_URL"] = args.api_url
    # Replace this launcher process with Streamlit: Ctrl+C stops the server as well.
    os.environ.clear()
    os.environ.update(env)
    UIConfig.from_env()
    os.chdir(ROOT)
    sys.argv = [
        "streamlit",
        "run",
        str(ROOT / "frontend/app.py"),
        "--server.address",
        "127.0.0.1",
        "--server.port",
        str(args.port),
        "--server.headless",
        "true",
    ]
    from streamlit.web.cli import main as streamlit_main

    return streamlit_main()


if __name__ == "__main__":
    raise SystemExit(main())
