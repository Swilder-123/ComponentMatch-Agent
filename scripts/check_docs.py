"""Check committed/candidate Markdown links and anonymization without external HTTP."""

import re
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"!?\[[^\]\n]*\]\(\s*(<[^>]+>|[^\s)]+)(?:\s+\"[^\"]*\")?\s*\)")
PRIVATE_PATH = re.compile(r"[A-Za-z]:[/\\]+Users[/\\]+[^/\\\s`]+")


def markdown_files():
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    )
    return sorted(
        {
            ROOT / name.decode("utf-8")
            for name in result.stdout.split(b"\0")
            if name and name.decode("utf-8").endswith(".md")
        }
    )


def check():
    errors, files, count = [], markdown_files(), 0
    for path in files:
        text = path.read_text(encoding="utf-8")
        if PRIVATE_PATH.search(text):
            errors.append(f"{path.relative_to(ROOT)}: contains a personal Windows home path")
        # Skip fenced examples; links inside them are illustrative code rather than navigation.
        content = re.sub(r"(?ms)^\s*(`{3,}|~{3,}).*?^\s*\1\s*$", "", text)
        for match in LINK.finditer(content):
            target = match[1].strip("<>")
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            count += 1
            destination = (path.parent / unquote(parsed.path)).resolve()
            if not destination.is_relative_to(ROOT) or not destination.exists():
                errors.append(f"{path.relative_to(ROOT)}: broken local link: {target}")
    if errors:
        print("\n".join(errors))
        return 1
    print(f"Documentation checks passed: {len(files)} Markdown files, {count} local links.")
    return 0


if __name__ == "__main__":
    raise SystemExit(check())
