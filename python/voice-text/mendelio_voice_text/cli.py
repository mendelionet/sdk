"""Command-line interface for normalization, explanation and benchmarks."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from importlib.resources import files
import json
import sys
import time

from mendelio_voice_text import SpeechPreprocessor, __version__


def _preprocessor(args: argparse.Namespace) -> SpeechPreprocessor:
    if args.profile == "cs-generic":
        return SpeechPreprocessor.czech_generic(max_chars=args.max_chars)
    if args.profile == "cs-omnivoice":
        return SpeechPreprocessor.czech_omnivoice(max_chars=args.max_chars)
    return SpeechPreprocessor.verbatim(
        args.locale,
        target=args.target,
        max_chars=args.max_chars,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mendelio-voice-text")
    parser.add_argument("--version", action="version", version=__version__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    for name in ("normalize", "explain", "benchmark"):
        command = subcommands.add_parser(name)
        command.add_argument(
            "--profile",
            choices=("cs-generic", "cs-omnivoice", "verbatim"),
            default="cs-omnivoice",
        )
        command.add_argument("--locale", default="cs")
        command.add_argument("--target", default="generic")
        command.add_argument("--max-chars", type=int, default=300)
        command.add_argument("text", nargs="?")
    subcommands.choices["benchmark"].add_argument(
        "--iterations",
        type=int,
        default=100,
    )
    subcommands.choices["benchmark"].add_argument(
        "--bundled-corpus",
        action="store_true",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    text = args.text or ""
    corpus_id = None
    sentence_count = None
    if args.command == "benchmark" and args.bundled_corpus:
        corpus = json.loads(
            files("mendelio_voice_text.data")
            .joinpath("benchmark-corpus-v0.1.json")
            .read_text(encoding="utf-8")
        )
        corpus_id = corpus["corpus_id"]
        sentences = tuple(str(sentence) for sentence in corpus["sentences"])
        text = "\n".join(sentences)
        sentence_count = len(sentences)
    elif args.text is None:
        text = sys.stdin.read()
    preprocessor = _preprocessor(args)
    if args.command == "benchmark":
        started = time.perf_counter()
        for _ in range(max(1, args.iterations)):
            preprocessor.prepare(text)
        elapsed = time.perf_counter() - started
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "package_version": __version__,
                    "profile": args.profile,
                    "iterations": max(1, args.iterations),
                    "input_chars": len(text),
                    "corpus_id": corpus_id,
                    "sentence_count": sentence_count,
                    "elapsed_ms": round(elapsed * 1_000, 3),
                    "per_prepare_ms": round(
                        elapsed * 1_000 / max(1, args.iterations),
                        6,
                    ),
                },
                ensure_ascii=False,
            )
        )
        return 0
    prepared = preprocessor.prepare(text)
    if args.command == "normalize":
        print(prepared.model_text)
        return 0
    print(json.dumps(asdict(prepared), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
