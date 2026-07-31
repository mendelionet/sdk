#!/usr/bin/env python3
"""Build and inspect a wheel/sdist, then import from a fresh virtualenv."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import zipfile


FORBIDDEN_CONTENT = (
    "roman_" + "seznamka",
    "/Users/" + "miakh",
    "hetzner" + "-prod",
    "OPENROUTER" + "_API_KEY",
    "VASTAI" + "_API_KEY",
    "SUPABASE" + "_SERVICE_ROLE_KEY",
    "BEGIN " + "PRIVATE KEY",
)
REQUIRED_WHEEL_PATHS = (
    "mendelio_voice_text/data/benchmark-corpus-v0.1.json",
    "mendelio_voice_text/data/czech_ipa_transliteration_map.json",
    "mendelio_voice_text/data/CZECH_PRONUNCIATION_MAP_LICENSE.md",
    "mendelio_voice_text/py.typed",
)
REQUIRED_SDIST_SUFFIXES = (
    "/ARCHITECTURE.md",
    "/CHANGELOG.md",
    "/CONTRIBUTING.md",
    "/LICENSE",
    "/NOTICE",
    "/README.md",
    "/SECURITY.md",
    "/tests/data/behavior-corpus-v0.1.json",
    "/tests/test_conformance.py",
    "/tools/build_czech_pronunciation_map.py",
)


def _run(*command: str) -> None:
    subprocess.run(command, check=True)


def _inspect_wheel(wheel: Path) -> None:
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        for required in REQUIRED_WHEEL_PATHS:
            if required not in names:
                raise RuntimeError(f"wheel is missing {required}")
        if any(name.startswith("voice_text/") for name in names):
            raise RuntimeError("wheel contains the retired voice_text namespace")
        if not any(
            name.endswith(".dist-info/licenses/LICENSE")
            or name.endswith(".dist-info/LICENSE")
            for name in names
        ):
            raise RuntimeError("wheel is missing the code license")


def _inspect_sdist(sdist: Path) -> None:
    with tarfile.open(sdist) as archive:
        names = tuple(member.name for member in archive.getmembers())
        for required in REQUIRED_SDIST_SUFFIXES:
            if not any(name.endswith(required) for name in names):
                raise RuntimeError(f"sdist is missing {required}")
        for member in archive.getmembers():
            if not member.isfile() or member.name.endswith(
                "verify_release_artifact.py"
            ):
                continue
            handle = archive.extractfile(member)
            if handle is None:
                continue
            text = handle.read().decode("utf-8", errors="ignore")
            for forbidden in FORBIDDEN_CONTENT:
                if forbidden in text:
                    raise RuntimeError(
                        f"private or secret marker {forbidden!r} in {member.name}"
                    )


def _fresh_install_smoke(wheel: Path, root: Path) -> None:
    environment = root / "fresh-venv"
    _run(sys.executable, "-m", "venv", str(environment))
    python = environment / "bin/python"
    pip = environment / "bin/pip"
    _run(str(pip), "install", "--no-index", "--no-deps", str(wheel))
    probe = (
        "import json; "
        "from mendelio_voice_text import SpeechPreprocessor, __version__; "
        "p=SpeechPreprocessor.czech_omnivoice().prepare('První.'); "
        "print(json.dumps({'version':__version__,'spoken':p.spoken_text,"
        "'model':p.model_text}, ensure_ascii=False))"
    )
    completed = subprocess.run(
        (str(python), "-c", probe),
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)
    if payload["version"] != "0.1.0" or payload["spoken"] == payload["model"]:
        raise RuntimeError(f"fresh import returned unexpected payload: {payload}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "source",
        nargs="?",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    args = parser.parse_args()
    source = args.source.resolve()
    with tempfile.TemporaryDirectory(prefix="mendelio-voice-release-") as raw:
        root = Path(raw)
        output = root / "dist"
        _run(
            "uv",
            "build",
            "--no-build-logs",
            "--no-create-gitignore",
            "--out-dir",
            str(output),
            str(source),
        )
        wheel = next(output.glob("*.whl"))
        sdist = next(output.glob("*.tar.gz"))
        _inspect_wheel(wheel)
        _inspect_sdist(sdist)
        _fresh_install_smoke(wheel, root)
    print(f"release artifact verified with {sys.version.split()[0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
