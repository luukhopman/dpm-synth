"""Command-line entry point: ``dpm-synth generate``."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from dpmxbrl import write_xbrl_csv

from .generator import generate
from .scale import write_scaled_package
from .template import TemplateError, load_template


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI.

    Returns:
        int: ``0`` when every evaluable rule passes, ``1`` when some still
        fail, ``2`` on invalid input.
    """
    parser = argparse.ArgumentParser(
        prog="dpm-synth", description="Generate synthetic EBA reports."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("generate", help="write an xBRL-CSV report package")
    run.add_argument("template", type=Path, help="dpm-synth-template/1 JSON file")
    run.add_argument("-o", "--output", type=Path, required=True, help="report .zip")
    run.add_argument("--seed", type=int, default=0)
    run.add_argument("--open-rows", type=int, default=2, help="key rows per open table")
    run.add_argument("--max-rounds", type=int, default=40)
    run.add_argument(
        "--scale-rows",
        type=int,
        help="after solving, write every open table with this many key rows "
        "(load testing; rules over open-table totals will fail)",
    )
    run.add_argument("--reference-date", type=date.fromisoformat)
    run.add_argument("--entity", default="SYNTHETICDPMXL000002", help="LEI")
    run.add_argument("--level", choices=("CON", "IND"), default="CON")
    run.add_argument("--json", action="store_true", help="print a JSON summary")
    arguments = parser.parse_args(argv)
    try:
        template = load_template(arguments.template)
    except (OSError, TemplateError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    result = generate(
        template,
        seed=arguments.seed,
        open_rows=arguments.open_rows,
        max_rounds=arguments.max_rounds,
        entity=arguments.entity,
        reporting_level=arguments.level,
        reference_date=arguments.reference_date,
    )
    if arguments.scale_rows is None:
        write_xbrl_csv(result.report, arguments.output)
        facts = len(result.report.facts)
    else:
        written = write_scaled_package(
            result.data, arguments.output, rows=arguments.scale_rows
        )
        facts = sum(written.values())
    if arguments.json:
        print(
            json.dumps(
                {
                    "output": str(arguments.output),
                    "rules": result.rules,
                    "passed": result.passed,
                    "failed": result.failed,
                    "not_evaluated": result.not_evaluated,
                    "rounds": result.rounds,
                    "history": result.history,
                    "repairs": result.repairs,
                    "facts": facts,
                },
                indent=2,
            )
        )
    else:
        print(
            f"rules: {result.rules}, passed: {result.passed}, "
            f"failed: {len(result.failed)}"
        )
        print(f"wrote {arguments.output} ({facts} facts)")
    return 1 if result.failed else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
