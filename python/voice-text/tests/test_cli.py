from __future__ import annotations

import json

from mendelio_voice_text.cli import main


def test_bundled_benchmark_emits_versioned_schema(capsys) -> None:
    assert main(
        [
            "benchmark",
            "--profile",
            "cs-generic",
            "--bundled-corpus",
            "--iterations",
            "1",
        ]
    ) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == 1
    assert payload["package_version"] == "0.1.0"
    assert payload["corpus_id"] == "mendelio-voice-text.synthetic.v0.1"
    assert payload["sentence_count"] == 5
    assert payload["iterations"] == 1
