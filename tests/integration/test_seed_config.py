"""The new-machine seed command must initialize the same DB as the backend launcher."""

import sys

from scripts.seed_demo import main


def test_seed_reads_env_database_and_respects_explicit_override(tmp_path, monkeypatch, capsys):
    configured, override = tmp_path / "configured.db", tmp_path / "override.db"
    env_file = tmp_path / "backend.env"
    env_file.write_text(
        f"DATABASE_URL=sqlite:///{configured.as_posix()}\nDEEPSEEK_API_KEY=private-test-key\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(sys, "argv", ["seed_demo.py", "--env-file", str(env_file)])
    main()
    assert configured.is_file()
    before = configured.read_bytes()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "seed_demo.py",
            "--env-file",
            str(env_file),
            "--database-url",
            f"sqlite:///{override.as_posix()}",
        ],
    )
    main()
    assert override.is_file() and configured.read_bytes() == before
    assert "private-test-key" not in capsys.readouterr().out
