"""Explicitly create DEMO data using the backend .env DATABASE_URL or a CLI override."""

import argparse
import json
from pathlib import Path

from componentmatch.core.config import Settings
from componentmatch.db.seed import seed_demo
from componentmatch.db.session import make_engine
from dotenv import dotenv_values
from sqlalchemy.engine import make_url


def main():
    parser = argparse.ArgumentParser(
        description="Create a dedicated DEMO database without overwrite"
    )
    parser.add_argument("--database-url", default=None)
    parser.add_argument(
        "--env-file", type=Path, default=Path(__file__).resolve().parents[1] / ".env"
    )
    args = parser.parse_args()
    env = dotenv_values(args.env_file, interpolate=False)
    url = args.database_url or env.get("DATABASE_URL") or Settings().database_url
    database = make_url(url).database
    if database and database != ":memory:":
        Path(database).resolve().parent.mkdir(parents=True, exist_ok=True)
    engine = make_engine(url)
    try:
        print(json.dumps(seed_demo(engine), ensure_ascii=False, indent=2))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
