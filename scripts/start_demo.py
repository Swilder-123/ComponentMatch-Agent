"""Local supervisor: separate backend credentials from the Streamlit process."""

import argparse
import importlib.metadata
import os
import socket
import sqlite3
import subprocess
import sys
import time
from contextlib import ExitStack
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from dotenv import dotenv_values
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
TABLES = (
    "components",
    "suppliers",
    "offers",
    "supplier_certifications",
    "performance_records",
    "demo_metadata",
)


def frontend_environment(source, api_port=None):
    # Allowlist, not a blacklist: no DeepSeek, database, tracing, or other credentials inherited.
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
    }
    env = {k: v for k, v in source.items() if k.upper() in allowed}
    for key in ("COMPONENTMATCH_API_URL", "COMPONENTMATCH_HTTP_TIMEOUT_SECONDS"):
        if key in source:
            env[key] = source[key]
    if api_port is not None:
        env["COMPONENTMATCH_API_URL"] = f"http://127.0.0.1:{api_port}"
    env.update(PYTHONIOENCODING="utf-8", STREAMLIT_BROWSER_GATHER_USAGE_STATS="false")
    return env


def backend_environment(env_file):
    env = dict(os.environ)
    if env_file.is_file():
        # Never print these values or write them to a log/temporary credentials file.
        env.update(
            {k: v for k, v in dotenv_values(env_file, interpolate=False).items() if v is not None}
        )
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def check_dependencies():
    for package in (
        "httpx",
        "fastapi",
        "uvicorn",
        "sqlalchemy",
        "pydantic",
        "langgraph",
        "langchain-deepseek",
    ):
        importlib.metadata.version(package)


def database_freshness(env, *, now=None):
    """Read-only availability warning; not a substitute for matching hard constraints."""
    now = now or datetime.now(UTC)
    url = make_url(env.get("DATABASE_URL", "sqlite:///./data/componentmatch.db"))
    path = Path(url.database)
    if not path.is_absolute():
        path = ROOT / path
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as connection:
        offers = connection.execute(
            "SELECT observed_at, valid_until FROM offers WHERE status='active'"
        ).fetchall()
        certificates = connection.execute(
            "SELECT expires_on FROM supplier_certifications WHERE verification_status='verified'"
        ).fetchall()

    def stamp(value):
        parsed = datetime.fromisoformat(value)
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed

    stale = sum(now - stamp(observed) > timedelta(days=7) for observed, _ in offers)
    expired = sum(now > stamp(until) for _, until in offers)
    usable = sum(
        stamp(observed) <= now <= stamp(until) and now - stamp(observed) <= timedelta(days=7)
        for observed, until in offers
    )
    from zoneinfo import ZoneInfo

    day = now.astimezone(ZoneInfo("Asia/Shanghai")).date()
    return {
        "active_offers": len(offers),
        "stale_offers": stale,
        "expired_offers": expired,
        "fresh_active_offers": usable,
        "expired_certificates": sum(
            datetime.fromisoformat(row[0]).date() < day for row in certificates
        ),
    }


def check_database(env):
    url = make_url(env.get("DATABASE_URL", "sqlite:///./data/componentmatch.db"))
    if url.drivername != "sqlite" or not url.database:
        raise ValueError("database configuration")
    path = Path(url.database)
    if not path.is_absolute():
        path = ROOT / path
    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError("database missing")
    # Read-only connection: startup must never create, seed, or refresh a database.
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5) as connection:
        if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ValueError("database integrity")
        counts = {
            table: connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in TABLES
        }
        if any(count == 0 for count in counts.values()):
            raise ValueError("incomplete demo data")
    return counts


def port_available(port):
    with socket.socket() as sock:
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def wait_ready(process, url, *, json_response=False):
    deadline = time.monotonic() + 40
    with httpx.Client(trust_env=False, timeout=2, follow_redirects=False) as client:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError("child exited")
            try:
                response = client.get(url)
                if response.status_code == 200 and (
                    response.json().get("status") == "ok"
                    if json_response
                    else response.text.strip() == "ok"
                ):
                    return
            except (httpx.HTTPError, ValueError, AttributeError):
                pass
            time.sleep(0.25)
    raise TimeoutError("service startup")


def serve(args, backend_env):
    ports = [args.ui_port] if args.frontend_only else [args.api_port, args.ui_port]
    if len(set(ports)) != len(ports) or not all(port_available(p) for p in ports):
        print(
            "启动失败：本地端口已占用或端口重复。请调整 --api-port / --ui-port；不会停止已有服务。"
        )
        return 1
    children = []
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S") + f"-{os.getpid()}"
    log_dir = ROOT / "logs" / f"demo-{stamp}"
    log_dir.mkdir(parents=True)
    try:
        with ExitStack() as stack:

            def launch(name, command, env, interpreter=None):
                output = stack.enter_context((log_dir / f"{name}.log").open("w", encoding="utf-8"))
                child = subprocess.Popen(
                    [str(interpreter or sys.executable), *command],
                    cwd=ROOT,
                    env=env,
                    stdout=output,
                    stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
                children.append(child)
                return child

            if not args.frontend_only:
                api = launch(
                    "backend",
                    [
                        "scripts/start_backend.py",
                        "--port",
                        str(args.api_port),
                        "--env-file",
                        str(args.env_file),
                    ],
                    backend_env,
                )
                wait_ready(api, f"http://127.0.0.1:{args.api_port}/health", json_response=True)
            ui_env = frontend_environment(
                os.environ if args.frontend_only else backend_env,
                None if args.frontend_only else args.api_port,
            )
            ui = launch(
                "frontend",
                [
                    "-m",
                    "streamlit",
                    "run",
                    "frontend/app.py",
                    "--server.address",
                    "127.0.0.1",
                    "--server.port",
                    str(args.ui_port),
                    "--server.headless",
                    "true",
                ],
                ui_env,
                args.frontend_python,
            )
            wait_ready(ui, f"http://127.0.0.1:{args.ui_port}/_stcore/health")
            print(f"打开演示页面：http://127.0.0.1:{args.ui_port}", flush=True)
            if not args.frontend_only:
                print(f"后端文档：http://127.0.0.1:{args.api_port}/docs", flush=True)
            print(
                "启动检查未调用 DeepSeek。页面提交采购需求才会调用模型，可能产生 API 费用。",
                flush=True,
            )
            print(f"本地日志：logs/demo-{stamp}/；按 Ctrl+C 停止本次启动的服务。", flush=True)
            if args.smoke_test:
                return 0
            while all(p.poll() is None for p in children):
                time.sleep(0.5)
            print("子服务已退出，请检查本地日志。")
            return 1
    except KeyboardInterrupt:
        print("正在停止本次启动的服务。")
        return 0
    except Exception:
        print("服务启动失败，请检查依赖、端口或本地日志；未调用模型。")
        return 1
    finally:
        for child in reversed(children):
            if child.poll() is None:
                if os.name == "nt":
                    # Windows venv python can be a redirector with a second interpreter process.
                    # Stop only this owned child's tree, including its real server interpreter.
                    subprocess.run(
                        ["taskkill", "/PID", str(child.pid), "/T", "/F"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=False,
                    )
                else:
                    child.terminate()
                try:
                    child.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=3)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-port", type=int, default=8000)
    parser.add_argument("--ui-port", type=int, default=8501)
    parser.add_argument("--frontend-python", type=Path, default=Path(sys.executable))
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--frontend-only", action="store_true")
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument(
        "--smoke-test", action="store_true", help="Start, health-check, then stop; no LLM"
    )
    args = parser.parse_args()
    preparation_step = "端口参数"
    try:
        if not all(1024 <= p <= 65535 for p in (args.api_port, args.ui_port)):
            raise ValueError("ports")
        preparation_step = "后端依赖（运行 scripts/setup.ps1 -Target Backend）"
        check_dependencies()
        preparation_step = "前端环境（运行 scripts/setup.ps1 -Target Frontend）"
        probe = subprocess.run(
            [str(args.frontend_python), "-c", "import streamlit, componentmatch_frontend"],
            env=frontend_environment(os.environ),
            capture_output=True,
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        if probe.returncode:
            raise RuntimeError("frontend environment unavailable; run scripts/setup.ps1")
        preparation_step = "后端配置文件"
        backend_env = {} if args.frontend_only else backend_environment(args.env_file)
        if not args.frontend_only:
            preparation_step = "后端环境参数（检查 .env 中的数值与地址）"
            from componentmatch.core.config import Settings

            Settings.model_validate(
                {
                    key.lower(): value
                    for key, value in backend_env.items()
                    if key.lower() in Settings.model_fields
                }
            )
            preparation_step = "数据库路径与六表（按 README 显式执行 seed_demo.py）"
            check_database(backend_env)
            print("依赖与 SQLite 六表读取检查通过；未修改数据。")
            preparation_step = "报价与证书时效"
            freshness = database_freshness(backend_env)
            print(
                f"数据时效：有效期内且快照新鲜的活跃报价 {freshness['fresh_active_offers']}/"
                f"{freshness['active_offers']}；过期 {freshness['expired_offers']}，"
                f"超过7日 {freshness['stale_offers']}，"
                f"已过期的核验资质 {freshness['expired_certificates']}。"
            )
            if freshness["fresh_active_offers"] == 0:
                print(
                    "注意：当前无时效合格报价。请按 data/README.md "
                    "显式创建新演示库并修改 DATABASE_URL。"
                )
            print(
                "后端密钥："
                + (
                    "已配置（未联网验证）"
                    if backend_env.get("DEEPSEEK_API_KEY", "").strip()
                    else "未配置；页面可启动，自然语言匹配需先配置后端凭据。"
                )
            )
        if args.check_only:
            return 0
        return serve(args, backend_env)
    except Exception as exc:
        print(f"准备检查失败：{preparation_step}（{type(exc).__name__}）。")
        print("不会自动创建、重置数据库或覆盖 .env；详细准备步骤见 README。")
        return 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
