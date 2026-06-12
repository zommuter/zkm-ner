"""Spec tests for roadmap:df05 — single-source the plugin version.

Four version carriers exist today and have drifted: pyproject.toml (via package
metadata), repo-root plugin.yaml, src/zkm_ner/plugin.yaml, and the
PLUGIN_VERSION constant in zkm_ner.convert. The package metadata (pyproject) is
canonical; everything else must match it. See ROADMAP.md id:df05,
ARCHITECTURE.md §11.

Note for executors: after bumping pyproject, re-run ``uv sync`` so the editable
install's metadata refreshes before running these tests.
"""

from __future__ import annotations

import importlib.metadata
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _metadata_version() -> str:
    return importlib.metadata.version("zkm-ner")


def test_plugin_version_matches_package_metadata():  # roadmap:df05
    """PLUGIN_VERSION must be derived from package metadata, not hand-copied."""
    from zkm_ner.convert import PLUGIN_VERSION

    assert PLUGIN_VERSION == _metadata_version()


def test_root_plugin_yaml_matches_package_metadata():  # roadmap:df05
    """The filesystem-discovery manifest at the repo root must carry the
    pyproject version (it has drifted before: 0.18.0 vs 0.18.1)."""
    data = yaml.safe_load((_REPO_ROOT / "plugin.yaml").read_text(encoding="utf-8"))
    assert str(data["version"]) == _metadata_version()


def test_packaged_plugin_yaml_matches_package_metadata():  # roadmap:df05
    """GUARD (green pre-implementation): the wheel-packaged manifest copy is
    currently in sync — this locks it for all future bumps."""
    data = yaml.safe_load(
        (_REPO_ROOT / "src" / "zkm_ner" / "plugin.yaml").read_text(encoding="utf-8")
    )
    assert str(data["version"]) == _metadata_version()
