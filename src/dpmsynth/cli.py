"""Command-line interface: ``dpm-synth generate``.

Exit statuses: 0 when no rule at or above ``--fail-on`` fails or is an
``error``, 1 when one does (the package is written either way), 2 for a
usage error, and 3 when the template cannot be read or is invalid, or the
package cannot be written. ``unsupported`` rules never change the status.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections.abc import Iterator, Sequence
from datetime import date
from pathlib import Path
from typing import Any

from dpmxbrl import write_xbrl_csv

from ._version import __version__
from .generator import (
    DEFAULT_ENTITY,
    MAX_OPEN_ROWS,
    SIZES,
    STATUSES,
    GenerationResult,
    generate,
)
from .scale import _MAX_ROWS, write_scaled_package
from .template import _CURRENCY, TemplateError, load_template

RULES_FAILED = 1
"""Exit status when the package is written but a rule at or above
``--fail-on`` still fails or is an ``error``."""

INVALID_INPUT = 3
"""Exit status when the template is unreadable or invalid, or the package
cannot be written."""

JSON_SCHEMA_VERSION = 2
"""Version of the ``generate --json`` layout; it changes when the layout does."""

_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
# The most rules the text summary names in a list.
_SHOWN = 20

_EPILOG = """examples:
  dpm-synth generate template.json -o report.zip
  dpm-synth generate template.json -o report.zip --seed 7 --open-rows 3
  dpm-synth generate template.json -o report.zip --size large --fill 0.6
  dpm-synth generate template.json -o report.zip --json
  dpm-synth generate template.json -o report.zip --fail-on warning
  dpm-synth generate template.json -o big.zip --scale-rows 1000000

exit statuses: 0 no rule at or above --fail-on fails or cannot be evaluated
(default error: failing warnings exit 0), 1 one does (the package is written),
2 usage error, 3 unreadable or invalid template, or the package cannot be
written.

The template format: https://luukhopman.github.io/dpm-synth/reference/template-format/"""


class _Options(argparse.HelpFormatter):
    """Lists ``-o, --output ZIP`` as Python 3.13 and later do, on every version."""

    def _format_action_invocation(self, action: argparse.Action) -> str:
        if not action.option_strings or action.nargs == 0:
            return super()._format_action_invocation(action)
        value = self._format_args(
            action, self._get_default_metavar_for_optional(action)
        )
        return f"{', '.join(action.option_strings)} {value}"


class _Main(_Options, argparse.RawDescriptionHelpFormatter):
    """Keeps the line breaks of the description and the epilog."""


def _whole(minimum: int, maximum: int | None = None) -> Any:
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
        if maximum is not None and value > maximum:
            raise argparse.ArgumentTypeError(
                f"expected a whole number of at most {maximum:_}, got {text!r}"
            )
        return value

    parse.__name__ = "number"
    return parse


def _date(text: str) -> date:
    try:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            raise ValueError(text)  # fromisoformat also takes 20261231
        return date.fromisoformat(text)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"expected a date as YYYY-MM-DD, got {text!r}"
        ) from None


def _package(text: str) -> Path:
    if not text.casefold().endswith(".zip"):
        raise argparse.ArgumentTypeError(f"expected a .zip file, got {text!r}")
    return Path(text)


def _entity(text: str) -> str:
    if not _IDENTIFIER.fullmatch(text):
        raise argparse.ArgumentTypeError(
            f"expected letters and digits, such as an LEI, got {text!r}"
        )
    return text


def _currency(text: str) -> str:
    if not _CURRENCY.fullmatch(text):
        raise argparse.ArgumentTypeError(
            f"expected an ISO 4217 code such as EUR, got {text!r}"
        )
    return text


def _ratio(text: str) -> float:
    try:
        value = float(text)
    except ValueError:
        value = math.nan
    if not 0 < value <= 1:
        raise argparse.ArgumentTypeError(
            f"expected a number above 0 and at most 1, such as 0.6, got {text!r}"
        )
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dpm-synth",
        description="Generate synthetic EBA xBRL-CSV reports that satisfy a module's\n"
        "DPM-XL validation rules.",
        epilog=_EPILOG,
        formatter_class=_Main,
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser(
        "generate",
        help="write an xBRL-CSV report package for a template",
        formatter_class=_Options,
        description="Generate values for every cell of a template, repair them "
        "until the rules pass, and write an xBRL-CSV report package.",
    )
    run.add_argument("template", type=Path, help="dpm-synth-template/1 JSON file")
    run.add_argument(
        "-o",
        "--output",
        type=_package,
        required=True,
        metavar="ZIP",
        help="report package to write (.zip)",
    )
    run.add_argument(
        "--seed", type=int, default=0, metavar="N", help="random seed (default 0)"
    )
    run.add_argument(
        "--open-rows",
        type=_whole(1, MAX_OPEN_ROWS),
        default=2,
        metavar="N",
        help=f"key rows per open table, at most {MAX_OPEN_ROWS} (default 2)",
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
        type=_whole(1, _MAX_ROWS),
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
    run.add_argument(
        "--currency",
        type=_currency,
        metavar="CODE",
        help="reporting currency, an ISO 4217 code (default: the template's, else EUR)",
    )
    run.add_argument(
        "--size",
        choices=SIZES,
        default="medium",
        help="institution size that amounts are drawn for (default medium)",
    )
    run.add_argument(
        "--fill",
        type=_ratio,
        default=1.0,
        metavar="RATIO",
        help="share of cells that start with a value; the others are left "
        "out unless a rule needs them (default 1)",
    )
    run.add_argument(
        "--fail-on",
        choices=("error", "warning"),
        default="error",
        help="exit with status 1 when a rule of this severity or worse fails "
        "or is an error (default: error)",
    )
    run.add_argument("--json", action="store_true", help="print a JSON summary")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line.

    Args:
        argv: Arguments without the program name; ``sys.argv[1:]`` when
            ``None``.

    Returns:
        int: The exit status: 0 when no rule at or above ``--fail-on``
        (default ``error``, so failing warnings exit 0) fails or is an
        ``error``, 1 when one does, 3 when the template or the package
        cannot be read or written. Usage errors exit with status 2 through
        ``SystemExit``.
    """
    arguments = _parser().parse_args(argv)
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
        currency=arguments.currency,
        size=arguments.size,
        fill=arguments.fill,
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
    except (OSError, ValueError) as error:  # ReportError is a ValueError
        return _fail(f"{arguments.output}: cannot write: {_reason(error)}")
    if arguments.json:
        print(json.dumps(_summary(result, arguments, facts), indent=2))
    else:
        for line in _lines(result):
            print(line)
        print(f"wrote {arguments.output} ({facts} facts)")
    failing = {"error"} if arguments.fail_on == "error" else {"error", "warning"}
    severity = _severities(result)
    problems = any(
        status in {"failed", "error"} and severity[code] in failing
        for code, status in result.statuses.items()
    )
    return RULES_FAILED if problems else 0


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
    severity = _severities(result)
    return {
        "schema_version": JSON_SCHEMA_VERSION,
        "tool": "dpm-synth",
        "version": __version__,
        "summary": {**result.summary, "facts": facts},
        "output": str(arguments.output),
        "release": template.release,
        "module": template.module,
        "seed": arguments.seed,
        "rounds": result.rounds,
        "history": result.history,
        "repairs": result.repairs,
        "results": [
            {
                "rule": code,
                "severity": severity[code],
                "status": status,
                "message": result.messages.get(code),
            }
            for code, status in result.statuses.items()
        ],
    }


def _severities(result: GenerationResult) -> dict[str, str]:
    return {rule.code: rule.severity for rule in result.data.template.rules}


def _lines(result: GenerationResult) -> Iterator[str]:
    summary = result.summary
    # Passed and failed always, the other statuses when a rule has them.
    yield f"rules: {summary['rules']}, " + ", ".join(
        f"{status.replace('_', ' ')}: {summary[status]}"
        for status in STATUSES
        if summary[status] or status in {"passed", "failed"}
    )
    history = ", ".join(str(count) for count in result.history) or "-"
    yield f"rounds: {result.rounds} (failing rules per round: {history})"
    failed = result.failed
    if failed:
        severity = _severities(result)
        shown = ", ".join(
            code + (" (warning)" if severity[code] == "warning" else "")
            for code in failed[:_SHOWN]
        )
        more = len(failed) - _SHOWN
        yield f"still failing: {shown}" + (f" and {more} more" if more > 0 else "")
    messages = list(result.messages.items())
    for code, message in messages[:_SHOWN]:
        yield f"{code}: {result.statuses[code].replace('_', ' ')}: {message}"
    if len(messages) > _SHOWN:
        yield f"and {len(messages) - _SHOWN} more"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
