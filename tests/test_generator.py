import json
from decimal import Decimal

import pytest
from dpmxl import Item, Number, evaluate_rule
from xbrlreport import read_report

from dpmsynth import TemplateError, generate, load_template
from dpmsynth.cli import main


def cell(row, column, number, data_type="m", sheet=None, items=None):
    return {
        "id": f"cell-{number}",
        "row": row,
        "column": column,
        "sheet": sheet,
        "datapoint": f"dp{number}",
        "data_type": data_type,
        "items": items,
    }


def template_document():
    return {
        "format": "dpm-synth-template/1",
        "release": "4.3",
        "module": "COREP_OF",
        "entry_point": "http://www.eba.europa.eu/eu/fr/xbrl/crr/fws/corep/4.3/mod/corep_of.json",
        "reference_date": "2026-12-31",
        "decimals": {"m": 0, "p": 4},
        "tables": [
            {
                "code": "C_01.00",
                "filing_indicator": "C_01.00",
                "open_keys": [],
                "cells": [
                    cell(row, column, 10 * index + offset)
                    for index, row in enumerate(("0010", "0020", "0030", "0040"), 1)
                    for offset, column in enumerate(("0010", "0020", "0030"))
                ]
                + [
                    cell("0050", "0010", 50, "p"),
                    cell("0060", "0010", 60, "e", items=["eba_AS:x1", "eba_AS:x2"]),
                ],
            },
            {
                "code": "C_07.00.a",
                "filing_indicator": "C_07.00",
                "open_keys": [
                    {
                        "code": "qEBB",
                        "column": "qEBB",
                        "items": ["eba_qEC:qx16", "eba_qEC:qx23"],
                    }
                ],
                "cells": [
                    cell("0010", "0010", 70, sheet="*"),
                    cell("0020", "0010", 71, sheet="*"),
                ],
            },
            {
                "code": "B_01.01",
                "filing_indicator": "B_01.01",
                "open_keys": [{"code": "ERI", "column": "c0010", "items": None}],
                "cells": [cell("*", "0020", 80, "s")],
            },
        ],
        "rules": [
            # Row totals and column totals of the same block.
            {
                "code": "rows",
                "expression": "with {tC_01.00, (c0010, c0020, c0030), default: 0, interval: true}: {r0010} = {r0020} + {r0030} + {r0040}",
                "precondition": "{v_C_01.00}",
            },
            {
                "code": "columns",
                "expression": "with {tC_01.00, (r0010, r0020, r0030, r0040), default: 0, interval: true}: {c0010} = {c0020} + {c0030}",
            },
            {
                "code": "sign",
                "expression": "with {tC_01.00, r0040, default: 0, interval: false}: {(c0020, c0030)} <= 0",
            },
            {
                "code": "ratio",
                "expression": "{tC_01.00, r0050, c0010, default: 0, interval: true} * {tC_01.00, r0020, c0010, default: 0, interval: true} = {tC_01.00, r0030, c0010, default: 0, interval: true}",
            },
            {"code": "item", "expression": "{tC_01.00, r0060, c0010} in {[eba_AS:x2]}"},
            {
                "code": "open",
                "expression": "with {tC_07.00.a, c0010, default: 0, interval: true}: {r0020} <= {r0010}",
            },
            {
                "code": "open-total",
                "expression": "sum({tC_07.00.a, r0010, c0010, default: 0}) = {tC_01.00, r0010, c0010}",
            },
            {
                "code": "lei",
                "expression": 'match({tB_01.01, c0020}, "^[A-Z0-9]{18}[0-9]{2}$") and match({tB_01.01, c0020}[get ERI], "^[A-Z0-9]{18}[0-9]{2}$")',
            },
            {
                "code": "history",
                "expression": "{tC_01.00, r0010, c0010} = time_shift({tC_01.00, r0010, c0010}, A, 1, refPeriod)",
            },
        ],
    }


def test_generated_report_satisfies_every_evaluable_rule() -> None:
    template = load_template(template_document())
    result = generate(template, seed=3)

    assert result.failed == []
    assert result.passed == 8
    assert set(result.not_evaluated) == {"history"}
    assert result.data is not None
    for rule in template.rules[:-1]:
        assert (
            evaluate_rule(
                rule.expression, result.data, precondition=rule.precondition
            ).status
            == "passed"
        ), rule.code
    values = result.data.values
    assert values["dp60", ()] == Item("AS", "x2")
    for number in (41, 42):
        bounded = values[f"dp{number}", ()]
        assert isinstance(bounded, Number) and bounded.value <= 0
    for number in (10, 11, 12, 20, 21, 22, 30, 31, 32, 40, 41, 42):
        value = values[f"dp{number}", ()]
        assert isinstance(value, Number)
        assert value.value == value.value.to_integral_value()


def test_report_is_deterministic_and_round_trips(tmp_path) -> None:
    template = load_template(template_document())
    first, second = generate(template, seed=5), generate(template, seed=5)
    assert first.report == second.report
    report = first.report
    assert report.filing_indicators == {
        "C_01.00": True,
        "C_07.00": True,
        "B_01.01": True,
    }
    assert report.decimals_parameters == {
        "decimalsMonetary": 0,
        "decimalsPercentage": 4,
    }
    keyed = [fact for fact in report.facts if fact.template == "c_07.00.a"]
    assert {fact.keys["qEBB"] for fact in keyed} == {"eba_qEC:qx16", "eba_qEC:qx23"}
    lei_rows = [fact for fact in report.facts if fact.template == "b_01.01"]
    assert all(len(fact.keys["c0010"]) == 20 for fact in lei_rows)

    path = tmp_path / "report.zip"
    assert (
        main(["generate", str(_write(tmp_path)), "-o", str(path), "--seed", "5"]) == 0
    )
    read = read_report(path)
    assert read.entity_id == "SYNTHETICDPMXL000002.CON"
    assert len(read.facts) == len(report.facts)
    assert {fact.datapoint for fact in read.facts} == {
        fact.datapoint for fact in report.facts
    }


def test_percentages_keep_reporting_decimals() -> None:
    result = generate(load_template(template_document()), seed=1)
    ratio = next(fact for fact in result.report.facts if fact.datapoint == "dp50")
    assert ratio.value is not None
    exponent = Decimal(ratio.value).as_tuple().exponent
    assert isinstance(exponent, int) and -exponent <= 4


def _write(tmp_path):
    path = tmp_path / "template.json"
    path.write_text(json.dumps(template_document()), encoding="utf-8")
    return path


def test_cli_reports_invalid_templates(tmp_path, capsys) -> None:
    path = tmp_path / "bad.json"
    path.write_text('{"format": "other"}', encoding="utf-8")
    assert main(["generate", str(path), "-o", str(tmp_path / "x.zip")]) == 2
    assert "dpm-synth-template/1" in capsys.readouterr().err
    with pytest.raises(TemplateError):
        load_template({"format": "dpm-synth-template/1", "release": "4.3"})


def test_scaled_package_repeats_solved_rows_under_unique_keys(tmp_path) -> None:
    path = tmp_path / "scaled.zip"
    arguments = ["generate", str(_write(tmp_path)), "-o", str(path)]
    assert main([*arguments, "--seed", "5", "--scale-rows", "50"]) in (0, 1)
    report = read_report(path)
    lei_rows = [fact for fact in report.facts if fact.template == "b_01.01"]
    # Typed keys get one fresh value per row; enumerated keys cap the rows.
    assert len({fact.keys["c0010"] for fact in lei_rows}) == 50
    keyed = [fact for fact in report.facts if fact.template == "c_07.00.a"]
    assert {fact.keys["qEBB"] for fact in keyed} == {"eba_qEC:qx16", "eba_qEC:qx23"}
    assert report.reference_date.isoformat() == "2026-12-31"
