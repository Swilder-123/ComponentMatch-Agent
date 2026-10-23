"""Run only FastAPI, loading backend credentials from the project .env."""

import argparse
import os
from pathlib import Path

import uvicorn
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("port must be between 1024 and 65535")
    os.chdir(ROOT)
    os.environ.update(
        {k: v for k, v in dotenv_values(args.env_file, interpolate=False).items() if v is not None}
    )
    uvicorn.run(
        "componentmatch.api.main:app",
        host="127.0.0.1",
        port=args.port,
        log_level="info",
        log_config=log_config(),
    )


def log_config():
    from copy import deepcopy

    from uvicorn.config import LOGGING_CONFIG

    config = deepcopy(LOGGING_CONFIG)
    config["loggers"]["componentmatch.agent"] = {
        "handlers": ["default"],
        "level": "INFO",
        "propagate": False,
    }
    return config


if __name__ == "__main__":
    main()
