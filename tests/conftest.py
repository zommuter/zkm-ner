from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def make_store(tmp_path: Path) -> Path:
    s = tmp_path / "store"
    s.mkdir()
    subprocess.run(["git", "init", "-q", str(s)], check=True)
    subprocess.run(
        ["git", "-C", str(s), "config", "user.email", "test@example.com"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(s), "config", "user.name", "Test"],
        check=True,
    )
    return s


def make_md(directory: Path, filename: str, *, body: str = "Test body.", **meta) -> Path:
    import frontmatter

    directory.mkdir(parents=True, exist_ok=True)
    path = directory / filename
    path.write_text(frontmatter.dumps(frontmatter.Post(body, **meta)), encoding="utf-8")
    return path
