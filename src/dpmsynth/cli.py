"""Command-line interface: ``dpm-synth generate``.

Exit statuses: 0 when every evaluable rule passes, 1 when some still fail
(the package is written either way), 2 for a usage error, and 3 when the
template cannot be read or is invalid, or the package cannot be written.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterator, Sequence
from datetime import date
from pathlib import Path
from typing import Any

from dpmxbrl import ReportError, write_xbrl_csv

from ._version import __version__
from .generator import DEFAULT_ENTITY, GenerationResult, generate
from .scale import write_scaled_package
from .template import TemplateError, load_template

RULES_FAILED = 1
"""Exit status when the package is written but some rules still fail."""

INVALID_INPUT = 3
"""Exit status when the template is unreadable or invalid, or the package
cannot be written."""

JSON_SCHEMA_VERSION = 1
"""Version of the ``generate --json`` layout; it changes only with a new major."""

_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")

_EPILOG = """examples:
  dpm-synth generate template.json -o report.zip
  dpm-synth generate template.json -o report.zip --seed 7 --open-rows 3
  dpm-synth generate template.json -o report.zip --json
  dpm-synth generate template.json -o big.zip --scale-rows 1000000

exit statuses: 0 every evaluable rule passes, 1 some rules still fail (the
package is written), 2 usage error, 3 unreadable or invalid template, or the
package cannot be written.

The template format: https://luukhopman.github.io/dpm-synth/reference/template-format/"""


def _whole(minimum: int) -> Any:
    def parse(text: str) -> int:
        try:
            value = int(text)
        except ValueError:
            raise argparse.ArgumentTypeError(
                f"expected a whole number, got {text!r}"
            ) from None
        if value < minimum:
            raise argparse.ArgumentTypeError(
                f"expected a whole number of {minimum} or more, got {text!r}"
            )
        return value

    parse.__name__ = "number"
    return parse


def _date(text: str) -> date:
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"expected a date as YYYY-MM-DD, got {text!r}"
        ) from None


def _entity(text: str) -> str:
    if not _IDENTIFIER.fullmatch(text):
        raise argparse.ArgumentTypeError(
            f"expected letters and digits, such as an LEI, got {text!r}"
        )
    return text


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dpm-synth",
        description="Generate synthetic EBA xBRL-CSV reports that satisfy a "
        "module's DPM-XL validation rules.",
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser(
        "generate",
        help="write an xBRL-CSV report package for a template",
        description="Generate values for every cell of a template, repair them "
        "until the rules pass, and write an xBRL-CSV report package.",
    )
    run.add_argument("template", type=Path, help="dpm-synth-template/1 JSON file")
    run.add_argument(
        "-o",
        "--output",
        type=Path,
        required=True,
        help="report package to write (.zip)",
    )
    run.add_argument("--seed", type=int, default=0, help="random seed (default 0)")
    run.add_argument(
        "--open-rows",
        type=_whole(1),
        default=2,
        metavar="N",
        help="key rows per open table (default 2)",
    )
    run.add_argument(
        "--max-rounds",
        type=_whole(0),
        default=40,
        metavar="N",
        help="most evaluate-and-repair rounds (default 40)",
    )
    run.add_argument(
        "--scale-rows",
        type=_whole(1),
        metavar="N",
        help="after solving, write every open table with N key rows "
        "(load testing; rules over open-table totals will fail)",
    )
    run.add_argument(
        "--reference-date",
        type=_date,
        metavar="YYYY-MM-DD",
        help="reference date (default: the template's, else 2026-12-31)",
    )
    run.add_argument(
        "--entity",
        type=_entity,
        default=DEFAULT_ENTITY,
        metavar="LEI",
        help=f"LEI of the reporting entity (default {DEFAULT_ENTITY})",
    )
    run.add_argument(
        "--level",
        choices=("CON", "IND"),
        default="CON",
        help="reporting level, the entity suffix (default CON)",
    )
    run.add_argument("--json", action="store_true", help="print a JSON summary")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line.

    Args:
        argv: Arguments without the program name; ``sys.argv[1:]`` when
            ``None``.

    Returns:
        int: The exit status: 0 when every evaluable rule passes, 1 when some
        still fail, 3 when the template or the package cannot be read or
        written. Usage errors exit with status 2 through ``SystemExit``.
    """
    parser = _parser()
    arguments = parser.parse_args(argv)
    if arguments.output.suffix.casefold() != ".zip":
        parser.error(f"--output must end in .zip: {arguments.output}")
    try:
        template = load_template(arguments.template)
    except TemplateError as error:
        return _fail(error)
    result = generate(
        template,
        seed=arguments.seed,
        open_rows=arguments.open_rows,
        max_rounds=arguments.max_rounds,
        entity=arguments.entity,
        reporting_level=arguments.level,
        reference_date=arguments.reference_date,
    )
    try:
        if arguments.scale_rows is None:
            write_xbrl_csv(result.report, arguments.output)
            facts = len(result.report.facts)
        else:
            written = write_scaled_package(
                result.data, arguments.output, rows=arguments.scale_rows
            )
            facts = sum(written.values())
    except (OSError, ReportError) as error:
        return _fail(f"{arguments.output}: cannot write: {_reason(error)}")
    if arguments.json:
        print(json.dumps(_summary(result, arguments, facts), indent=2))
    else:
        for line in _lines(result):
            print(line)
        print(f"wrote {arguments.output} ({facts} facts)")
    return RULES_FAILED if result.failed else 0


def _fail(error: object) -> int:
    print(f"error: {error}", file=sys.stderr)
    return INVALID_INPUT


def _reason(error: Exception) -> str:
    if isinstance(error, OSError) and error.strerror:
        return error.strerror
    return str(error)


def _summary(
    result: GenerationResult, arguments: argparse.Namespace, facts: int
) -> dict[str, Any]:
    template = result.data.template
    return {
        "schema_version": JSON_SCHEMA_VERSION,
        "output": str(arguments.output),
        "release": template.release,
        "module": template.module,
        "seed": arguments.seed,
        "rules": result.rules,
        "passed": result.passed,
        "failed": result.failed,
        "not_evaluated": result.not_evaluated,
        "not_applicable": result.not_applicable,
        "rounds": result.rounds,
        "history": result.history,
        "repairs": result.repairs,
        "facts": facts,
    }


def _lines(result: GenerationResult) -> Iterator[str]:
    yield (
        f"rules: {result.rules}, passed: {result.passed}, "
        f"failed: {len(result.failed)}, not evaluated: {len(result.not_evaluated)}, "
        f"not applicable: {len(result.not_applicable)}"
    )
    history = ", ".join(str(count) for count in result.history) or "-"
    yield f"rounds: {result.rounds} (failing rules per round: {history})"
    if result.failed:
        shown = ", ".join(result.failed[:20])
        more = len(result.failed) - 20
        yield f"still failing: {shown}" + (f" and {more} more" if more > 0 else "")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
