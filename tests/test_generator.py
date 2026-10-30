import random
import subprocess
import sys
from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest
from dpmxl import CellQuery, Item, Number, evaluate_rule

from dpmsynth import (
    DEFAULT_ENTITY,
    GenerationResult,
    SyntheticData,
    TemplateError,
    build_report,
    generate,
    load_template,
)
from tests.support import SAMPLES, cell, document


def run(cells, rules, **options) -> GenerationResult:
    open_keys = options.pop("open_keys", ())
    decimals = options.pop("decimals", None)
    more_tables = options.pop("more_tables", ())
    raw = document(
        cells, rules, open_keys=open_keys, decimals=decimals, more_tables=more_tables
    )
    return generate(
        load_template(raw),
        **options,
    )


def value(result: GenerationResult, number: int, keys=()):
    return result.data.values[f"dp{number}", keys]


# The sample template ------------------------------------------------------------


def test_sample_satisfies_every_evaluable_rule() -> None:
    template = load_template(SAMPLES / "sample.json")
    result = generate(template, seed=3)

    assert result.failed == []
    assert result.summary == {
        "rules": 9,
        "passed": 8,
        "failed": 0,
        "not_applicable": 0,
        "error": 0,
        "unsupported": 1,
        "skipped": 0,
    }
    assert result.statuses["history"] == "unsupported"
    assert list(result.messages) == ["history"]
    assert "time_shift" in result.messages["history"]
    for rule in template.rules[:-1]:
        status = evaluate_rule(
            rule.expression, result.data, precondition=rule.precondition
        ).status
        assert status == "passed", rule.code
    values = result.data.values
    assert values["dp60", ()] == Item("AS", "x2")
    for number in (41, 42):
        bounded = values[f"dp{number}", ()]
        assert isinstance(bounded, Number) and bounded.value <= 0
    for number in (10, 11, 12, 20, 21, 22, 30, 31, 32, 40, 41, 42):
        amount = values[f"dp{number}", ()]
        assert isinstance(amount, Number)
        assert amount.value == amount.value.to_integral_value()


def test_report_is_deterministic() -> None:
    template = load_template(SAMPLES / "sample.json")
    first, second = generate(template, seed=5), generate(template, seed=5)
    assert first.report == second.report
    assert first.history == second.history
    assert generate(template, seed=6).report != first.report


def test_report_does_not_depend_on_string_hashing(tmp_path) -> None:
    script = (
        "from dpmsynth import generate, load_template;"
        f"r = generate(load_template({str(SAMPLES / 'sample.json')!r}), seed=4);"
        "print([(f.datapoint, f.value, sorted(f.keys.items())) for f in r.report.facts])"
    )
    outputs = {
        subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            check=True,
            env={"PYTHONHASHSEED": seed},
        ).stdout
        for seed in ("1", "2", "3")
    }
    assert len(outputs) == 1


def test_report_layout() -> None:
    result = generate(load_template(SAMPLES / "sample.json"), seed=5)
    report = result.report
    assert report.format == "xbrl-csv"
    assert report.entity_id == f"{DEFAULT_ENTITY}.CON"
    assert report.entity_scheme == "https://eurofiling.info/eu/rs"
    assert report.reference_date == date(2026, 12, 31)
    assert report.base_currency == "iso4217:EUR"
    assert report.filing_indicators == {
        "S_01.00": True,
        "S_02.00": True,
        "S_03.00": True,
        "S_04.00": False,  # in the module, not in the template
    }
    # Only the numeric types the template uses get a decimals parameter.
    assert report.decimals_parameters == {
        "decimalsMonetary": 0,
        "decimalsPercentage": 4,
    }
    keyed = [fact for fact in report.facts if fact.template == "s_02.00.a"]
    assert {fact.keys["qEBB"] for fact in keyed} == {"eba_qEC:qx16", "eba_qEC:qx23"}
    typed = [fact for fact in report.facts if fact.template == "s_03.00"]
    assert len(typed) == 2
    assert all(len(fact.keys["c0010"]) == 20 for fact in typed)
    assert build_report(result.data) == report


def test_percentages_keep_reporting_decimals() -> None:
    result = generate(load_template(SAMPLES / "sample.json"), seed=1)
    ratio = next(fact for fact in result.report.facts if fact.datapoint == "dp50")
    assert ratio.value is not None
    exponent = Decimal(ratio.value).as_tuple().exponent
    assert isinstance(exponent, int) and -exponent <= 4


# Options ------------------------------------------------------------------------


def test_options_reach_the_report() -> None:
    template = load_template(SAMPLES / "sample.json")
    result = generate(
        template,
        entity="SYNTHETICDPMXL000002",
        reporting_level="IND",
        reference_date=date(2025, 6, 30),
        open_rows=1,
    )
    assert result.report.entity_id == "SYNTHETICDPMXL000002.IND"
    assert result.report.reference_date == date(2025, 6, 30)
    assert result.data.template.reference_date == date(2025, 6, 30)
    assert template.reference_date == date(2026, 12, 31)  # unchanged
    assert result.data.parameter("ReportingLevel") == "ind"
    assert result.data.parameter("refPeriod") == date(2025, 6, 30)
    assert result.data.parameter("other") is None
    assert len(result.data.key_rows["S_02.00.a"]) == 1


def test_base_currency_is_written_only_for_monetary_facts() -> None:
    raw = document([cell("0010", "0010", 1)], [])
    assert generate(load_template(raw)).report.base_currency == "iso4217:EUR"
    raw["currency"] = "SEK"
    template = load_template(raw)
    assert generate(template).report.base_currency == "iso4217:SEK"
    assert generate(template, currency="PLN").report.base_currency == "iso4217:PLN"
    ratios = load_template(document([cell("0010", "0010", 1, "p")], []))
    assert generate(ratios).report.base_currency is None


def test_currency_of_denomination_facts_have_a_unit() -> None:
    result = generate(load_template(SAMPLES / "currencies.json"), open_rows=3)
    units = {
        (fact.datapoint, fact.keys["CUS"]): fact.keys["unit"]
        for fact in result.report.facts
        if fact.template == "k_01.00"
    }
    assert units == {
        ("dp1", "eba_CU:x1"): "iso4217:SEK",  # all currencies: the reporting one
        ("dp2", "eba_CU:x1"): "iso4217:SEK",
        ("dp3", "eba_CU:x1"): "",  # a percentage has no unit
        ("dp1", "eba_CU:USD"): "iso4217:USD",
        ("dp2", "eba_CU:USD"): "iso4217:USD",
        ("dp3", "eba_CU:USD"): "",
        ("dp1", "eba_CU:GBP"): "iso4217:GBP",
        ("dp2", "eba_CU:GBP"): "iso4217:GBP",
        ("dp3", "eba_CU:GBP"): "",
    }
    assert result.report.base_currency == "iso4217:SEK"  # for dp4
    closed = [fact for fact in result.report.facts if fact.template == "k_02.00"]
    assert [dict(fact.keys) for fact in closed] == [{}]


def test_base_currency_is_left_out_when_every_amount_has_a_unit() -> None:
    raw = document([dict(cell("0010", "0010", 1), unit=True)], [])
    report = generate(load_template(raw)).report
    assert report.base_currency is None
    assert [dict(fact.keys) for fact in report.facts] == [{"unit": "iso4217:EUR"}]


@pytest.mark.parametrize(
    ("module", "reference", "scheme", "entity"),
    [
        ("TEST", date(2022, 12, 31), "https://eurofiling.info/eu/rs", "X.CON"),
        ("TEST", date(2022, 9, 30), "http://standards.iso.org/iso/17442", "X"),
        ("COREP_LR_CON", date(2026, 12, 31), "http://standards.iso.org/iso/17442", "X"),
        ("FINREP_IND_X", date(2026, 12, 31), "http://standards.iso.org/iso/17442", "X"),
        ("INDEX_CONTROL", date(2026, 12, 31), "https://eurofiling.info/eu/rs", "X.CON"),
    ],
)
def test_reporting_subject_follows_filing_rule_3_6(
    tmp_path, module, reference, scheme, entity
) -> None:
    from dpmxbrl import read_report, write_xbrl_csv

    lei = "SYNTHETICDPMXL000002"
    raw = document([cell("0010", "0010", 1)], [])
    raw["module"] = module
    result = generate(load_template(raw), reference_date=reference, entity=lei)
    report = result.report
    assert (report.entity_scheme, report.entity_id) == (
        scheme,
        entity.replace("X", lei, 1),
    )
    write_xbrl_csv(report, tmp_path / "r.zip")
    read = read_report(tmp_path / "r.zip")
    assert (read.entity_scheme, read.entity_id) == (scheme, report.entity_id)


def test_reporting_level_is_a_parameter_for_rules() -> None:
    rules = ['if {vReportingLevel} = "ind" then {tT, r0010, c0010} = 5 endif']
    individual = run([cell("0010", "0010", 1)], rules, reporting_level="IND")
    assert individual.summary["passed"] == 1
    assert value(individual, 1) == Number(Decimal(5))
    consolidated = run([cell("0010", "0010", 1)], rules)
    assert value(consolidated, 1) != Number(Decimal(5))


@pytest.mark.parametrize(
    ("option", "message"),
    [
        ({"open_rows": 0}, "open_rows"),
        ({"open_rows": True}, "open_rows"),
        ({"open_rows": 1001}, "open_rows must be a whole number from 1 to 1000"),
        ({"max_rounds": -1}, "max_rounds"),
        ({"entity": ""}, "entity"),
        ({"entity": "A B"}, "entity"),
        ({"reporting_level": "../x"}, "reporting_level"),
        ({"currency": "eur"}, "currency must be an ISO 4217 code"),
    ],
)
def test_invalid_options(option, message) -> None:
    with pytest.raises(ValueError, match=message):
        generate(load_template(SAMPLES / "minimal.json"), **option)


def test_zero_rounds_evaluates_the_initial_values() -> None:
    result = generate(load_template(SAMPLES / "minimal.json"), max_rounds=0)
    assert result.rounds == 0
    assert result.history == []
    assert result.repairs == 0
    assert result.summary["passed"] + len(result.failed) == 2


# Rule accounting ----------------------------------------------------------------


def test_every_rule_is_counted_once() -> None:
    template = load_template(
        document(
            [cell("0010", "0010", 1)],
            [
                "{tT, r0010, c0010} >= 0",
                "{tT, r0010, c0010} = 0",
                "{tT, r0010, c0010} = time_shift({tT, r0010, c0010}, A, 1, refPeriod)",
                {
                    "code": "never",
                    "expression": "{tT, r0010, c0010} = 1",
                    "precondition": "{v_X_99.00}",
                },
                "{tT, r0990, c0010} = 1",  # selects no cell
                "{tT, r0010, c0010} = 0",
            ],
        )
    )
    # load_template rejects these two; a template built in code may have them.
    rules = list(template.rules)
    rules[1] = replace(rules[1], expression="{tT, r0010, c0010} >")
    rules[5] = replace(rules[5], expression="{tX_99.00, r0010, c0010} = 1")
    result = generate(replace(template, rules=tuple(rules)))
    assert result.statuses == {
        "r1": "passed",
        "r2": "error",
        "r3": "unsupported",
        "never": "not_applicable",
        "r5": "not_applicable",
        "r6": "error",
    }
    assert list(result.messages) == ["r2", "r3", "r6"]
    assert result.messages["r2"].startswith("syntax error:")
    assert "X_99.00" in result.messages["r6"]
    summary = result.summary
    assert summary["rules"] == 6
    assert sum(summary.values()) == 2 * summary["rules"]


def test_unsatisfiable_rules_are_reported_as_failed() -> None:
    result = run(
        [cell("0010", "0010", 1)],
        ["{tT, r0010, c0010} > 10", "{tT, r0010, c0010} < 5"],
    )
    assert len(result.failed) == 1
    assert result.summary["passed"] == 1


def test_oscillation_stops_the_loop() -> None:
    result = run(
        [cell("0010", "0010", 1), cell("0020", "0010", 2)],
        [
            "{tT, r0010, c0010} = {tT, r0020, c0010} + 1000",
            "{tT, r0020, c0010} = {tT, r0010, c0010} + 1000",
        ],
        max_rounds=100,
    )
    assert result.rounds < 100
    assert len(result.failed) == 1


# Analysis: definitions and bounds -------------------------------------------------


def test_totals_are_solved_after_their_components() -> None:
    # Listed total first: ordering by definition depth still converges.
    cells = [cell(f"00{n}0", "0010", n) for n in range(1, 6)]
    result = run(
        cells,
        [
            "with {tT, c0010, default: 0}: {r0010} = {r0020} + {r0030}",
            "with {tT, c0010, default: 0}: {r0030} = {r0040} + {r0050}",
        ],
    )
    assert result.failed == []
    assert result.history[-1] == 0


def test_sign_rules_bound_cells() -> None:
    cells = [cell("0010", "0010", 1), cell("0020", "0010", 2), cell("0030", "0010", 3)]
    result = run(
        cells,
        [
            "{tT, r0010, c0010} <= 0",
            "0 < {tT, r0020, c0010}",
            "{tT, r0030, c0010} >= -100",
            # The total must absorb the difference, not the bounded cells.
            "with {tT, c0010, default: 0}: {r0010} + {r0020} = 50",
        ],
    )
    assert result.failed == []
    assert value(result, 1).value <= 0
    assert value(result, 2).value >= 1
    assert value(result, 3).value >= -100


def test_strict_bounds_use_the_reporting_step() -> None:
    result = run(
        [cell("0010", "0010", 1, "p"), cell("0020", "0010", 2, "p")],
        [
            "{tT, r0010, c0010} > 0",
            "{tT, r0010, c0010} < 1",
            "{tT, r0020, c0010} > {tT, r0010, c0010}",
            "{tT, r0020, c0010} <= 1",
        ],
        decimals={"p": 4},
    )
    assert result.failed == []
    assert 0 < value(result, 1).value < 1
    assert value(result, 2).value <= 1


def test_initial_values_move_fully_inside_bounds() -> None:
    data = SyntheticData(
        load_template(document([cell("0010", "0010", 1), cell("0020", "0010", 2)], [])),
        random.Random(1),
        1,
    )
    data.values["dp1", ()] = Number(Decimal(-3))
    data.values["dp2", ()] = Number(Decimal(4000))
    data._bounds["dp1", ()] = (Decimal(-1000), Decimal(-5000))
    data._bounds["dp2", ()] = (Decimal(10), Decimal(500))
    data._bounds["dp1", ()] = (None, Decimal(-5000))
    data._apply_bounds()
    assert data.values["dp1", ()] == Number(Decimal(-5000))
    assert data.values["dp2", ()] == Number(Decimal(500))


# Repairs ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "rule",
    [
        "{tT, r0010, c0010} = {tT, r0020, c0010} - {tT, r0030, c0010}",
        "{tT, r0010, c0010} = -{tT, r0020, c0010}",
        "{tT, r0010, c0010} = abs({tT, r0020, c0010}) + 7",
        "{tT, r0010, c0010} = sum({tT, (r0020, r0030), c0010})",
        "{tT, r0010, c0010} * 2 = {tT, r0020, c0010}",
        "{tT, r0010, c0010} / 4 = {tT, r0020, c0010}",
        "{tT, r0010, c0010} != {tT, r0020, c0010}",
        "{tT, r0010, c0010} > {tT, r0020, c0010} + {tT, r0030, c0010}",
        "{tT, r0010, c0010} < {tT, r0020, c0010} - 100000",
        "{tT, r0010, c0010} = 12345",
    ],
)
def test_linear_comparisons_are_repaired(rule) -> None:
    cells = [cell(f"00{n}0", "0010", n) for n in (1, 2, 3)]
    result = run(cells, [rule])
    assert result.failed == [], rule


def test_products_of_two_cells_are_linearized() -> None:
    result = run(
        [
            cell("0010", "0010", 1, "p"),
            cell("0020", "0010", 2),
            cell("0030", "0010", 3),
        ],
        [
            "with {default: 0, interval: true}: "
            "{tT, r0010, c0010} * {tT, r0020, c0010} = {tT, r0030, c0010}"
        ],
    )
    assert result.failed == []


def test_isnull_and_logic_are_repaired() -> None:
    cells = [cell(f"00{n}0", "0010", n, "s") for n in (1, 2, 3, 4)]
    result = run(
        cells,
        [
            "isnull({tT, r0010, c0010})",
            "isnull({tT, r0020, c0010}) or not isnull({tT, r0010, c0010})",
            "not (not isnull({tT, r0030, c0010}) and isnull({tT, r0040, c0010}))",
        ],
    )
    assert result.failed == []
    assert value(result, 1) is None
    assert value(result, 2) is None


def test_isnull_negation_fills_a_cleared_cell() -> None:
    result = run(
        [cell("0010", "0010", 1), cell("0020", "0010", 2)],
        [
            "if {tT, r0020, c0010} > 0 then isnull({tT, r0010, c0010}) endif",
            "not isnull({tT, r0010, c0010})",
        ],
        max_rounds=3,
    )
    assert "r2" not in result.failed


def test_if_repairs_the_branch_that_applies() -> None:
    result = run(
        [cell("0010", "0010", 1), cell("0020", "0010", 2), cell("0030", "0010", 3)],
        [
            "if {tT, r0010, c0010} > 0 then {tT, r0020, c0010} = 5 "
            "else {tT, r0030, c0010} = 5 endif"
        ],
    )
    assert result.failed == []
    assert value(result, 2) == Number(Decimal(5))


def test_in_is_repaired_for_any_set_operand() -> None:
    def enumerated(row, number, items):
        return cell(row, "0010", number, "e", items=items)

    result = run(
        [
            enumerated("0010", 1, ["eba_AS:x1", "eba_AS:x2"]),
            enumerated("0020", 2, ["eba_AS:x2"]),
            enumerated("0030", 3, ["eba_AS:x1", "eba_AS:x3"]),
            cell("0040", "0010", 4),
            enumerated("0050", 5, ["eba_AS:x1"]),
        ],
        [
            # A selection of cells, a set function, a numeric literal set,
            # and a set whose first member does not fit the cell.
            "{tT, r0010, c0010} in {tT, r0020, c0010}",
            "{tT, r0030, c0010} in union({[eba_AS:x3]}, {[eba_AS:x4]})",
            "{tT, r0040, c0010} in {1000, 2000}",
            "{tT, r0050, c0010} in {1, [eba_AS:x9]}",
        ],
    )
    assert result.failed == []
    assert value(result, 1) == Item("AS", "x2")
    assert value(result, 3) == Item("AS", "x3")
    assert value(result, 4) == Number(Decimal(1000))
    assert value(result, 5) == Item("AS", "x9")


def test_match_writes_leis_and_dates() -> None:
    result = run(
        [cell(f"00{n}0", "0010", n, "s") for n in (1, 2, 3)],
        [
            'match({tT, r0010, c0010}, "^[A-Z0-9]{18}[0-9]{2}$")',
            'match({tT, r0020, c0010}, "^[0-9]{2}[/]{1}[0-9]{2}[/]{1}[0-9]{4}$")',
            'match({tT, r0030, c0010}, "^x+$") or isnull({tT, r0030, c0010})',
        ],
        reference_date=date(2025, 3, 31),
    )
    assert result.failed == []
    lei = value(result, 1)
    assert lei.startswith("SYNTH")
    assert int("".join(str(int(character, 36)) for character in lei)) % 97 == 1
    assert value(result, 2) == "31/03/2025"
    assert value(result, 3) is None


def test_huge_corrections_are_not_written() -> None:
    result = run(
        [cell("0010", "0010", 1, "p"), cell("0020", "0010", 2)],
        ["{tT, r0010, c0010} * 0.000000001 = 1000000000000000000000000000000"],
    )
    assert result.failed == ["r1"]
    assert abs(value(result, 1).value) < 10**16


# Values and rounding --------------------------------------------------------------


def test_initial_values_by_data_type() -> None:
    kinds = ["m", "p", "i", "r", "e", "b", "d", "s", None, "es"]
    cells = [
        cell(f"00{index}0", "0010", index, kind, items=["eba_AB:x1", "eba_AB:x2"])
        if kind in ("e", "es")
        else cell(f"00{index}0", "0010", index, kind)
        for index, kind in enumerate(kinds, 1)
    ]
    result = run(cells, [], seed=11)
    m, p, i, r, e, b, d, s, text, es = (value(result, n) for n in range(1, 11))
    assert m.value % 1000 == 0 and 100_000 <= m.value <= 100_000_000
    assert 0 < p.value < 1
    assert 1 <= i.value <= 50 and i.value == i.value.to_integral_value()
    assert 1 <= r.value < 10
    assert e == es == Item("AB", "x1")
    assert isinstance(b, bool)
    assert date(2016, 12, 31) <= d <= date(2026, 12, 31)
    # Text is not LEI-shaped: only match repairs write LEIs.
    assert isinstance(s, str) and s.startswith("Synthetic text ")
    assert isinstance(text, str) and text.startswith("Synthetic text ")


def test_booleans_and_dates_vary_by_seed() -> None:
    cells = [cell(f"00{n}0", "0010", n, kind) for n, kind in ((1, "b"), (2, "d"))]
    results = [run(cells, [], seed=seed) for seed in range(20)]
    assert {value(result, 1) for result in results} == {True, False}
    assert len({value(result, 2) for result in results}) > 10
    again = run(cells, [], seed=3)
    assert value(again, 2) == value(results[3], 2)


@pytest.mark.parametrize(("size", "low", "high"), [
    ("small", 10**3, 10**6),
    ("medium", 10**5, 10**8),
    ("large", 10**7, 10**10),
])  # fmt: skip
def test_amounts_scale_with_the_institution_size(size, low, high) -> None:
    cells = [cell(f"{n:04d}", "0010", n) for n in range(1, 40)]
    result = run(cells, [], size=size)
    amounts = [value(result, n).value for n in range(1, 40)]
    assert all(low <= amount <= high and amount % 1000 == 0 for amount in amounts)
    assert max(amounts) > 10 * min(amounts)  # spread over magnitudes


@pytest.mark.parametrize("seed", range(3))
def test_sparse_reports_still_satisfy_the_rules(seed) -> None:
    template = load_template(SAMPLES / "sample.json")
    full = generate(template, seed=seed)
    sparse = generate(template, seed=seed, fill=0.3)
    assert sparse.failed == []
    assert len(sparse.report.facts) < len(full.report.facts)
    # Every table keeps a fact.
    tables = {fact.template for fact in sparse.report.facts}
    assert tables == {fact.template for fact in full.report.facts}
    assert generate(template, seed=seed, fill=0.3).report == sparse.report


def test_rules_give_empty_cells_a_value() -> None:
    cells = [cell(f"00{n}0", "0010", n) for n in (1, 2, 3)]
    rules = [
        "not isnull({tT, r0030, c0010, default: null})",
        "with {tT, c0010, default: 0, interval: true}: {r0010} = {r0020} + {r0030}",
    ]
    for seed in range(5):
        result = run(cells, rules, seed=seed, fill=0.01)
        assert result.failed == []
        assert value(result, 2) is None  # left empty, counted as 0
        assert value(result, 3) is not None
        assert value(result, 1) == value(result, 3)


@pytest.mark.parametrize(
    ("option", "message"),
    [
        ({"size": "huge"}, "size must be one of small, medium, large"),
        ({"fill": 0}, "fill must be a number above 0"),
        ({"fill": 1.5}, "fill must be a number above 0"),
        ({"fill": True}, "fill must be a number above 0"),
    ],
)
def test_size_and_fill_are_checked(option, message) -> None:
    with pytest.raises(ValueError, match=message):
        run([cell("0010", "0010", 1)], [], **option)


def test_dates_move_against_the_reference_date() -> None:
    cells = [cell("0010", "0010", 1, "d")]
    result = run(cells, ["{tT, r0010, c0010} > refPeriod"], seed=0)
    assert result.failed == []
    assert value(result, 1) == date(2027, 1, 1)


@pytest.mark.parametrize(
    ("decimals", "expected"),
    [
        ({"m": -3}, "1235000"),
        ({"m": 0}, "1234568"),
        ({"m": 2}, "1234567.89"),
        ({"m": -3, "value": "1234500"}, "1234000"),  # ties go to the even digit
        ({"m": -3, "value": "1235500"}, "1236000"),
    ],
)
def test_values_are_rounded_to_the_reporting_decimals(decimals, expected) -> None:
    decimals = dict(decimals)
    target = decimals.pop("value", "1234567.891")
    result = run(
        [cell("0010", "0010", 1)],
        [f"{{tT, r0010, c0010}} = {target}"],
        decimals=decimals,
    )
    fact = result.report.facts[0]
    assert fact.value == expected


def test_negative_zero_is_written_as_zero() -> None:
    result = run(
        [cell("0010", "0010", 1), cell("0020", "0010", 2)],
        ["{tT, r0010, c0010} = -{tT, r0020, c0010}", "{tT, r0020, c0010} = 0"],
    )
    values = {fact.datapoint: fact.value for fact in result.report.facts}
    assert values == {"dp1": "0", "dp2": "0"}


def test_items_keep_the_template_prefix() -> None:
    result = run(
        [cell("0010", "0010", 1, "e", items=["own_AB:x1", "eba_AB:x2"])],
        [],
        open_keys=[{"code": "qKY", "items": ["xyz_KY:k1"]}],
    )
    facts = result.report.facts
    assert {fact.value for fact in facts} == {"own_AB:x1"}
    assert {fact.keys["qKY"] for fact in facts} == {"xyz_KY:k1"}


def test_typed_keys_are_valid_leis() -> None:
    result = run(
        [cell("0010", "0010", 1)], [], open_keys=[{"code": "ERI"}], open_rows=5
    )
    keys = [fact.keys["ERI"] for fact in result.report.facts]
    assert len(set(keys)) == 5
    for key in keys:
        assert key.startswith("SYNTH")
        digits = int("".join(str(int(character, 36)) for character in key))
        assert digits % 97 == 1


def test_enumerated_keys_cap_the_rows() -> None:
    result = run(
        [cell("0010", "0010", 1)],
        [],
        open_keys=[{"code": "qAB", "items": ["eba_AB:x1", "eba_AB:x2"]}],
        open_rows=5,
    )
    assert len(result.data.key_rows["T"]) == 2


# The provider -----------------------------------------------------------------------


def test_synthetic_data_is_a_provider() -> None:
    result = run(
        [cell("0010", "0010", 1), cell("0020", "0010", 2, sheet="*")],
        [],
        open_keys=[{"code": "qAB", "items": ["eba_AB:x1"]}],
        more_tables=[
            {
                "code": "T_02.00.a",
                "filing_indicator": "T_02.00",
                "cells": [cell("0010", "0010", 3)],
            }
        ],
    )
    data = result.data
    assert data.open_keys("t") == ("qAB",)
    assert data.open_keys("T_02.00.a") == ()
    assert data.open_keys("missing") == ()
    assert data.table_reported("T")
    assert data.table_reported("t_02.00")
    assert data.table_reported("T_02.00.a")
    assert not data.table_reported("T_03.00")
    points = data.select(CellQuery("T"))
    assert [(point.row, point.keys) for point in points] == [
        ("0010", {"qAB": Item("AB", "x1")}),
        ("0020", {"qAB": Item("AB", "x1")}),
    ]
    with pytest.raises(LookupError, match=r"T_09\.00 is not in module TEST"):
        data.select(CellQuery("T_09.00"))


def test_enumerated_keys_stop_at_their_cycle() -> None:
    result = run(
        [cell("0010", "0010", 1)],
        [],
        open_keys=[
            {"code": "qAB", "items": ["eba_AB:x1", "eba_AB:x2", "eba_AB:x3"]},
            {"code": "qCD", "items": ["eba_CD:y1", "eba_CD:y2"]},
        ],
        open_rows=1000,
    )
    # Row i takes item i of each key: the rows repeat after lcm(3, 2) = 6.
    assert len(result.data.key_rows["T"]) == 6


def test_templates_outside_the_template_are_indicated_as_not_reported() -> None:
    raw = document(
        [cell("0010", "0010", 1)],
        [
            {
                "code": "absent",
                "expression": "{tT, r0010, c0010} = 1",
                "precondition": "{v_U_01.00}",
            }
        ],
    )
    raw["filing_indicators"] = ["U_01.00", "T"]
    result = generate(load_template(raw))
    assert result.report.filing_indicators == {"U_01.00": False, "T": True}
    assert result.statuses == {"absent": "not_applicable"}
    assert {fact.template for fact in result.report.facts} == {"t"}


def test_enumeration_sets_take_an_allowed_item() -> None:
    items = ["eba_AB:x1", "eba_AB:x2"]
    result = run(
        [cell("0010", "0010", 1, "es", items=items)],
        ["{tT, r0010, c0010} in {[eba_AB:x2]}"],
    )
    assert result.summary["passed"] == 1
    assert [fact.value for fact in result.report.facts] == ["eba_AB:x2"]


def test_enumerated_cells_without_items_get_no_value() -> None:
    template = load_template(document([cell("0010", "0010", 1, "m")], []))
    table = template.tables[0]
    bare = replace(table.cells[0], data_type="e")
    template = replace(template, tables=(replace(table, cells=(bare,)),))
    result = generate(template)
    assert result.data.values["dp1", ()] is None
    assert result.report.facts == ()


def test_typed_keys_get_values_of_their_data_type() -> None:
    result = run(
        [cell("*", "0010", 1)],
        [
            "with {tT, c0010}: {r*}[where qID = 2] >= 0",
            "with {tT, c0010}: {r*}[where qDT = #2026-12-30#] >= 0",
            'match({tT, c0010}[get qLE], "^[A-Z0-9]{18}[0-9]{2}$")',
        ],
        open_keys=[
            {"code": "qID", "data_type": "i"},
            {"code": "qDT", "data_type": "d"},
            {"code": "qLE", "data_type": "s"},
        ],
        open_rows=3,
    )
    rows = [dict(keys) for keys in result.data.key_rows["T"]]
    assert [row["qID"] for row in rows] == [Number(Decimal(n)) for n in (1, 2, 3)]
    assert [row["qDT"] for row in rows] == [
        date(2026, 12, 31),
        date(2026, 12, 30),
        date(2026, 12, 29),
    ]
    assert all(row["qLE"].startswith("SYNTH") for row in rows)
    assert result.summary["passed"] == 3
    keys = {tuple(fact.keys.values()) for fact in result.report.facts}
    assert ("2", "2026-12-30") in {key[:2] for key in keys}


X = "{tT, r0010, c0010}"


@pytest.mark.parametrize(
    "rule",
    [
        " and ".join([f"{X} = 5"] * 1000),
        " and ".join([f"{X} >= 0"] * 999 + [f"{X} = 5"]),
        " or ".join([f"{X} = 1"] * 999 + [f"{X} = 5"]),
        f"{X} = " + " + ".join(["{tT, r0020, c0010}"] * 1000),
        f"{X} = 5 + " + " - ".join(["{tT, r0020, c0010}"] * 1000),
    ],
    ids=["and", "and-bounds", "or", "sum", "differences"],
)
def test_long_chains_are_repaired_without_recursion(rule) -> None:
    result = run([cell("0010", "0010", 1), cell("0020", "0010", 2)], [rule])
    assert result.failed == []
    assert result.summary["passed"] == 1


def test_too_deeply_nested_rules_are_reported_not_raised() -> None:
    nested = "not (" * 3000 + f"{X} = 5" + ")" * 3000
    template = load_template(document([cell("0010", "0010", 1)], [X, f"{X} >= 0"]))
    with pytest.raises(TemplateError, match="too deeply nested"):
        load_template(document([cell("0010", "0010", 1)], [nested]))
    rules = (replace(template.rules[0], expression=nested), template.rules[1])
    result = generate(replace(template, rules=rules))
    assert len(result.statuses) == 2
    assert "r2" not in result.failed


@pytest.mark.parametrize(
    "rule",
    [
        f"{X} = 5 and {X} = 5",
        f"not(not({X} = 5))",
        "with {tT, c0010}: {r0010} = {r0020} + {r0030} and {r0010} >= 5000000",
        "with {tT, c0010}: {r0010} >= 2000000 and {r0010} <= 3000000",
    ],
)
@pytest.mark.parametrize("seed", [0, 1, 2])
def test_and_repairs_are_not_applied_twice(rule, seed) -> None:
    cells = [cell(f"00{n}0", "0010", n) for n in (1, 2, 3)]
    result = run(cells, [rule], seed=seed)
    assert result.failed == [], rule
    assert result.rounds <= 2


def test_inactive_rules_are_skipped() -> None:
    result = run(
        [cell("0010", "0010", 1)],
        [
            "{tT, r0010, c0010} = 5",
            {"code": "off", "expression": "{tT, r0010, c0010} = 7", "active": False},
            {"code": "gone", "expression": "{tX, r0010, c0010} = 1", "active": False},
        ],
    )
    assert result.statuses == {"r1": "passed", "off": "skipped", "gone": "skipped"}
    assert result.summary["skipped"] == 2
    assert result.messages == {}
    assert value(result, 1) == Number(Decimal(5))


def test_warnings_are_repaired_like_errors() -> None:
    result = run(
        [cell("0010", "0010", 1)],
        [{"code": "w", "expression": "{tT, r0010, c0010} = 5", "severity": "warning"}],
    )
    assert result.statuses == {"w": "passed"}


# Failure patterns of EBA modules, as small templates --------------------------


def _grid_cells(rows, columns, data_type="m"):
    return [
        cell(row, column, int(row) * 1000 + int(column), data_type)
        for row in rows
        for column in columns
    ]


@pytest.mark.parametrize("seed", range(5))
def test_totals_of_both_rows_and_columns(seed) -> None:
    # A grid whose last row and last column are totals, the corner defined
    # twice (as in C_13.01 and C_07.00.a): one cell at a time, the repairs
    # of the row and the column totals undo each other.
    rows, columns = ["0010", "0020", "0030", "0040"], ["0010", "0020", "0030", "0040"]
    rules = [
        "with {tT, default: 0, interval: true}: {c0040} = {c0010} + {c0020} + {c0030}",
        "with {tT, default: 0, interval: true}: {r0040} = {r0010} + {r0020} + {r0030}",
        "with {tT, default: 0, interval: true}: {r0040, c0040} = {r0010, c0040} + {r0020, c0040} + {r0030, c0040}",
        "{tT, c0010-0040} >= 0",
        "with {tT, default: 0, interval: true}: {r0020, c0040} >= {r0010, c0040}",
    ]
    result = run(_grid_cells(rows, columns), rules, seed=seed)
    assert result.failed == []


@pytest.mark.parametrize("seed", range(5))
def test_chains_through_constant_factors(seed) -> None:
    # Own funds requirements times 12.5 are exposures (as in C_18.00 and
    # C_02.00): the exposures total is defined by its parts and by the
    # requirement, which has parts of its own.
    cells = [cell(row, "0010", int(row)) for row in ("0010", "0020", "0030")]
    cells += [cell(row, "0020", 100 + int(row)) for row in ("0010", "0020", "0030")]
    rules = [
        "with {tT, c0010, default: 0, interval: true}: {r0010} = {r0020} + {r0030}",
        "with {tT, c0020, default: 0, interval: true}: {r0010} = {r0020} + {r0030}",
        "with {tT, default: 0, interval: true}: {r0010, c0010} * 12.5 = {r0010, c0020}",
        "with {tT, default: 0, interval: true}: {r0020, c0010} * 12.5 = {r0020, c0020}",
        "{tT, c0010-0020} >= 0",
    ]
    result = run(cells, rules, seed=seed)
    assert result.failed == []


@pytest.mark.parametrize("seed", range(5))
def test_absolute_values_of_defined_cells(seed) -> None:
    # abs(row) >= abs(row) + abs(row) where every cell is also part of a
    # column total (as in C_13.01), with a row that must not be positive.
    rows, columns = ["0010", "0020", "0030", "0040"], ["0010", "0020", "0030"]
    rules = [
        "with {tT, default: 0, interval: true}: {c0030} = {c0010} + {c0020}",
        "with {tT, default: 0, interval: true}: "
        "abs({r0010}) >= abs({r0020}) + abs({r0030}) + abs({r0040})",
        "with {tT, default: 0, interval: true}: {r0020} >= {r0040}",
        "{tT, r0030, c0010-0030} <= 0",
        "{tT, (r0010, r0020, r0040), c0010-0030} >= 0",
    ]
    result = run(_grid_cells(rows, columns), rules, seed=seed)
    assert result.failed == []


@pytest.mark.parametrize("seed", range(5))
def test_sums_of_bounded_ratios(seed) -> None:
    # c = a + b with every percentage between 0 and 1 (as in C_14.00): no
    # single cell can take the whole difference.
    cells = [
        cell("0010", column, int(column), "p") for column in ("0010", "0020", "0030")
    ]
    rules = [
        "with {tT, r0010, default: 0, interval: true}: {c0030} = {c0010} + {c0020}",
        "{tT, r0010, c0010-0030} >= 0",
        "{tT, r0010, c0010-0030} <= 1",
        "{tT, r0010, c0010} >= 0.6",
        "{tT, r0010, c0020} >= 0.2",
    ]
    result = run(cells, rules, seed=seed)
    assert result.failed == []


def test_dates_compared_with_each_other() -> None:
    # A start date before an end date (as in C_14.00).
    cells = [cell("0010", "0010", 1, "d"), cell("0010", "0020", 2, "d")]
    rules = [
        "{tT, r0010, c0010} < {tT, r0010, c0020}",
        "{tT, r0010, c0020} >= {tT, r0010, c0010}",
    ]
    result = run(cells, rules, seed=0)
    assert result.failed == []
    assert value(result, 1) < value(result, 2)


@pytest.mark.parametrize("seed", range(5))
def test_strict_comparisons_of_ratios_use_the_reporting_step(seed) -> None:
    # A margin of 1 would push percentages far past 1.
    cells = [cell("0010", "0010", 1, "p"), cell("0020", "0010", 2, "p")]
    rules = ["{tT, r0010, c0010} > {tT, r0020, c0010}", "{tT, r0010-0020, c0010} >= 0"]
    result = run(cells, rules, seed=seed)
    assert result.failed == []
    assert 0 < value(result, 1).value <= 1
    assert value(result, 1).value > value(result, 2).value > 0
