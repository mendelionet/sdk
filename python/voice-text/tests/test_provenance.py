from __future__ import annotations

import tomllib
from pathlib import Path

from mendelio_voice_text import __version__, package_provenance


def test_runtime_version_matches_build_metadata() -> None:
    pyproject = tomllib.loads(
        (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(
            encoding="utf-8"
        )
    )
    assert __version__ == pyproject["project"]["version"]


def test_package_provenance_is_stable_and_non_content() -> None:
    first = package_provenance()
    second = package_provenance()

    assert first is second
    assert first.package_version == __version__
    assert first.ruleset_id.startswith("mendelio-voice-text/")
    assert first.model_adapter_id.startswith("omnivoice.cs/")
    assert first.data_id.startswith("sha256:")
