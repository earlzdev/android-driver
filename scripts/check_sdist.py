"""Refuse to publish an sdist that carries local machine data.

Hatchling reads only the *root* `.gitignore`, so a nested one (`test_app/.gitignore`,
which hides `local.properties` and the absolute SDK path in it) and the user's global
git ignore are both invisible to it. The 0.0.1 build was 950K and shipped
`test_app/local.properties` and `.claude/settings.local.json` before anyone noticed.
`pyproject.toml` now names what ships, and this checks that the allowlist held.

A release cannot be unpublished, so this runs before the upload, not after.
"""

from __future__ import annotations

import re
import sys
import tarfile
from pathlib import Path

# Paths whose presence means the allowlist has been widened by accident.
FORBIDDEN_NAMES = re.compile(
    r"(^|/)(local\.properties|settings\.local\.json|\.env|\.claude/|\.venv/|runs/|build/|\.gradle/)"
)
# Content that could only have come from the machine that ran the build.
FORBIDDEN_CONTENT = re.compile(r"sdk\.dir\s*=|/Users/[a-z]|/home/[a-z]", re.IGNORECASE)

# Text worth scanning. Reading the whole tarball would mean decoding PNGs and jars.
TEXT_SUFFIXES = {".py", ".toml", ".md", ".yaml", ".yml", ".json", ".txt", ".cfg", ".properties", ""}


def check(path: Path) -> list[str]:
    problems: list[str] = []
    with tarfile.open(path, "r:gz") as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue
            # Strip the `android_driver-1.2.3/` prefix every sdist member carries.
            rel = member.name.split("/", 1)[1] if "/" in member.name else member.name
            if FORBIDDEN_NAMES.search(rel):
                problems.append(f"{rel}: should not ship")
                continue
            if Path(rel).suffix.lower() not in TEXT_SUFFIXES:
                continue
            fh = tar.extractfile(member)
            if fh is None:
                continue
            body = fh.read().decode("utf-8", errors="replace")
            for hit in set(FORBIDDEN_CONTENT.findall(body)):
                problems.append(f"{rel}: contains {hit!r}")
    return problems


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: check_sdist.py <sdist.tar.gz>", file=sys.stderr)
        return 2
    path = Path(sys.argv[1])
    problems = check(path)
    if problems:
        print(f"{path.name} is not safe to publish:", file=sys.stderr)
        for p in sorted(set(problems)):
            print(f"  {p}", file=sys.stderr)
        return 1
    size_kb = path.stat().st_size // 1024
    print(f"{path.name} looks clean ({size_kb}K)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
