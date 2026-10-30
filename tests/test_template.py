import copy
import json
from datetime import date
from pathlib import Path

import pytest

from dpmsynth import (
    TEMPLATE_FORMAT,
    OpenKey,
    TemplateCell,
    TemplateError,
    TemplateRule,
    load_template,
)

SAMPLES = Path(__file__).parent.parent / "docs" / "samples"


def document():
    return {
        "format": TEMPLATE_FORMAT,
        "release": "1.0",
        "module": "DEMO",
        "tables": [
            {
                "code": "T_01.00",
                "open_keys": [{"code": "qAB", "items": ["eba_AB:x1"]}],
                "cells": [{"id": "a", "datapoint": "dp1", "data_type": "m"}],
            }
        ],
        "rules": [{"code": "v1", "expression": "{tT_01.00, c0010} >= 0"}],
    }


def test_loads_a_file_a_path_string_and_a_mapping() -> None:
    path = SAMPLES / "minimal.json"
    from_path = load_template(path)
    assert load_template(str(path)) == from_path
    assert load_template(json.loads(path.read_text(encoding="utf-8"))) == from_path
    assert from_path.module == "DEMO"
    assert from_path.reference_date == date(2026, 12, 31)
    assert from_path.entry_point is not None


def test_defaults() -> None:
    template = load_template(document())
    table = template.tables[0]
    assert table.filing_indicator == "T_01.00"
    assert table.open_keys == (OpenKey("qAB", "qAB", ("eba_AB:x1",)),)
    assert table.cells == (TemplateCell("a", "dp1", "m"),)
    assert template.rules == (
        TemplateRule("v1", "{tT_01.00, c0010} >= 0", None, "eba", "error", True),
    )
    assert template.reference_date is None
    assert template.entry_point is None
    assert template.decimals == {}
    assert template.filing_indicators == ()
    assert template.currency is None


def test_optional_fields_and_unknown_fields() -> None:
    raw = document()
    raw["decimals"] = {"m": -3, "p": 6}
    raw["reference_date"] = "2025-06-30"
    raw["generator"] = "a newer export"  # unknown fields are ignored
    raw["tables"][0]["filing_indicator"] = "T_01"
    raw["tables"][0]["open_keys"][0]["column"] = "c0010"
    raw["tables"][0]["open_keys"].append({"code": "qID", "data_type": "i"})
    raw["tables"][0]["cells"][0].update(row="0010", column="0010", sheet="*", unit=True)
    raw["tables"][0]["cells"].append(
        {"id": "b", "datapoint": "dp2", "data_type": "s", "items": []}
    )
    raw["rules"][0].update(precondition="{v_T_01}", source="own", severity="warning")
    raw["rules"].append(
        # An inactive rule is not checked: it may select a table now gone.
        {"code": "v2", "expression": "{tX_99.00, c0010} >", "active": False}
    )
    raw["filing_indicators"] = ["T_01", "T_02"]
    raw["currency"] = "SEK"
    snapshot = copy.deepcopy(raw)
    template = load_template(raw)
    assert raw == snapshot  # the document is not changed
    assert template.decimals == {"m": -3, "p": 6}
    assert template.reference_date == date(2025, 6, 30)
    table = template.tables[0]
    assert table.filing_indicator == "T_01"
    assert table.open_keys[0].column == "c0010"
    assert table.open_keys[1] == OpenKey("qID", "qID", None, "i")
    assert table.cells[0].sheet == "*"
    assert table.cells[0].unit is True
    assert table.cells[1].unit is False
    assert table.cells[1].items is None  # an empty list allows anything
    assert template.rules[0].precondition == "{v_T_01}"
    assert template.rules[0].source == "own"
    assert template.rules[0].severity == "warning"
    assert template.rules[0].active is True
    assert template.rules[1].active is False
    assert template.rules[1].severity == "error"
    assert template.filing_indicators == ("T_01", "T_02")
    assert template.currency == "SEK"


def test_loads_a_dpm_xl_module_file() -> None:
    raw = document()
    raw["format"] = "dpm-module/1"
    assert load_template(raw) == load_template(document())


def test_es_cells_need_no_items() -> None:
    raw = document()
    raw["tables"][0]["cells"][0] = {"id": "a", "datapoint": "dp1", "data_type": "es"}
    assert load_template(raw).tables[0].cells[0].items is None


def test_rules_may_select_templates_reported_as_absent() -> None:
    raw = document()
    raw["filing_indicators"] = ["T_01.00", "U_01.00"]
    raw["rules"].append({"code": "v2", "expression": "{tU_01.00.a, c0010} > 0"})
    raw["rules"].append(
        {
            "code": "v3",
            "expression": "{tU_01.00, c0010} > 0",
            "precondition": "{v_U_01.00}",
        }
    )
    assert len(load_template(raw).rules) == 3
    raw["rules"].append({"code": "v4", "expression": "{tT_01.00.b, c0010} > 0"})
    with pytest.raises(TemplateError, match=r"selects table T_01\.00\.b, which is not"):
        load_template(raw)


def test_table_lookup_ignores_case() -> None:
    template = load_template(document())
    assert template.table("t_01.00") is template.tables[0]
    assert template.table("T_02.00") is None


def _broken(change):
    raw = document()
    change(raw)
    return raw


def _set(path, value):
    def change(raw):
        target = raw
        for part in path[:-1]:
            target = target[part]
        if value is _DELETE:
            del target[path[-1]]
        else:
            target[path[-1]] = value

    return change


_DELETE = object()


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (
            _set(["format"], "dpm-synth-template/2"),
            "format: expected 'dpm-synth-template/1' or 'dpm-module/1', "
            "got 'dpm-synth-template/2'",
        ),
        (_set(["format"], _DELETE), "format: required"),
        (_set(["release"], _DELETE), "release: required"),
        (
            _set(["release"], 4.3),
            "release: expected a non-empty string, got the number 4.3",
        ),
        (
            _set(["module"], " "),
            "module: expected a non-empty string, got an empty string",
        ),
        (
            _set(["entry_point"], ["x"]),
            "entry_point: expected a string or null, got an array",
        ),
        (
            _set(["reference_date"], "31/12/2026"),
            "reference_date: expected a date as YYYY-MM-DD, got '31/12/2026'",
        ),
        (
            _set(["reference_date"], "2026-02-30"),
            "reference_date: expected a date as YYYY-MM-DD, got '2026-02-30'",
        ),
        (_set(["decimals"], [0]), "decimals: expected an object, got an array"),
        (
            _set(["decimals"], {"m": 1.5}),
            "decimals.m: expected a whole number from -20 to 20, got 1.5",
        ),
        (
            _set(["decimals"], {"m": True}),
            "decimals.m: expected a whole number from -20 to 20, got True",
        ),
        (
            _set(["decimals"], {"m": 99}),
            "decimals.m: expected a whole number from -20 to 20, got 99",
        ),
        (
            _set(["rules", 0, "expression"], "{tT_01.00, c0010} >"),
            "rules[0].expression: syntax error: expression ends where an operand "
            "is expected at position 19",
        ),
        (
            _set(["rules", 0, "expression"], "{tT_01.00} = {tX_99.00}"),
            "rules[0].expression: selects table X_99.00, which is not in the template",
        ),
        (
            _set(["rules", 0, "precondition"], "{tX_99.00, c0010} > 0"),
            "rules[0].precondition: selects table X_99.00, which is not in the "
            "template",
        ),
        (
            _set(["rules", 0, "precondition"], "{v_T_01.00} and"),
            "rules[0].precondition: syntax error:",
        ),
        (
            _set(["tables", 0, "cells", 0, "data_type"], "e"),
            "tables[0].cells[0].items: required for an enumerated cell (data type 'e')",
        ),
        (
            _set(["filing_indicators"], "T_01.00"),
            "filing_indicators: expected an array, got the string 'T_01.00'",
        ),
        (
            _set(["filing_indicators"], ["T_01.00", 1]),
            "filing_indicators[1]: expected a filing indicator such as 'C_07.00', "
            "got the number 1",
        ),
        (
            _set(["filing_indicators"], ["T_01.00", "T_01.00"]),
            "filing_indicators[1]: 'T_01.00' repeats filing_indicators[0]",
        ),
        (
            _set(["filing_indicators"], ["T_02.00"]),
            "tables[0].filing_indicator: 'T_01.00' is not in filing_indicators",
        ),
        (
            _set(["currency"], "euro"),
            "currency: expected an ISO 4217 code such as 'EUR', got 'euro'",
        ),
        (
            _set(["tables", 0, "cells", 0, "unit"], "USD"),
            "tables[0].cells[0].unit: expected a boolean or null, got the string 'USD'",
        ),
        (
            _set(
                ["tables", 0, "cells", 0],
                {"id": "a", "datapoint": "dp1", "data_type": "p", "unit": True},
            ),
            "tables[0].cells[0].unit: only a monetary cell (data type 'm') has a unit",
        ),
        (
            _set(
                ["tables", 0],
                {
                    "code": "T",
                    "open_keys": [{"code": "unit"}],
                    "cells": [
                        {"id": "a", "datapoint": "dp1", "data_type": "m", "unit": True}
                    ],
                },
            ),
            "tables[0].open_keys[0].column: 'unit' is the unit column of the table",
        ),
        (
            _set(["decimals"], {"m": -7}),
            "decimals.m: expected -6 or more, as EBA filing rule 2.18 requires, got -7",
        ),
        (
            _set(["decimals"], {"p": 2}),
            "decimals.p: expected 4 or more, as EBA filing rule 2.18 requires, got 2",
        ),
        (
            _set(["decimals"], {"i": 2}),
            "decimals.i: expected 0, as EBA filing rule 2.18 requires, got 2",
        ),
        (
            _set(["decimals"], {"i": -1}),
            "decimals.i: expected 0, as EBA filing rule 2.18 requires, got -1",
        ),
        (_set(["tables"], _DELETE), "tables: required"),
        (_set(["tables"], {}), "tables: expected an array, got an object"),
        (_set(["tables"], []), "tables: at least one table is required"),
        (
            _set(["tables", 0], "T_01.00"),
            "tables[0]: expected an object, got the string 'T_01.00'",
        ),
        (_set(["tables", 0, "code"], _DELETE), "tables[0].code: required"),
        (
            _set(["tables", 0, "code"], "../evil"),
            "tables[0].code: '../evil' cannot name a table file",
        ),
        (
            _set(["tables", 0, "code"], "parameters"),
            "tables[0].code: 'parameters' cannot name a table file",
        ),
        (
            _set(["tables", 0, "cells"], []),
            "tables[0].cells: at least one cell is required",
        ),
        (_set(["tables", 0, "cells"], _DELETE), "tables[0].cells: required"),
        (
            _set(["tables", 0, "cells", 0, "datapoint"], _DELETE),
            "tables[0].cells[0].datapoint: required",
        ),
        (
            _set(["tables", 0, "cells", 0, "id"], 7),
            "tables[0].cells[0].id: expected a non-empty string, got the number 7",
        ),
        (
            _set(["tables", 0, "cells", 0, "data_type"], 1),
            "tables[0].cells[0].data_type: expected a string or null, got the number 1",
        ),
        (
            _set(["tables", 0, "cells", 0, "items"], "eba_AB:x1"),
            "tables[0].cells[0].items: expected an array of item qnames or null, got the string 'eba_AB:x1'",
        ),
        (
            _set(["tables", 0, "cells", 0, "items"], ["eba_AB:x1", None]),
            "tables[0].cells[0].items[1]: expected an item qname such as 'eba_AS:x1', got null",
        ),
        (
            _set(["tables", 0, "open_keys"], "qAB"),
            "tables[0].open_keys: expected an array, got the string 'qAB'",
        ),
        (
            _set(["tables", 0, "open_keys", 0, "code"], _DELETE),
            "tables[0].open_keys[0].code: required",
        ),
        (
            _set(["tables", 0, "open_keys", 0, "column"], "factValue"),
            "tables[0].open_keys[0].column: 'factValue' is a fact column of the table",
        ),
        (_set(["rules"], {"v1": "x"}), "rules: expected an array, got an object"),
        (_set(["rules", 0, "expression"], _DELETE), "rules[0].expression: required"),
        (
            _set(["rules", 0, "precondition"], False),
            "rules[0].precondition: expected a string or null, got a boolean",
        ),
        (
            _set(["rules", 0, "severity"], "blocking"),
            "rules[0].severity: expected 'error', 'warning' or null, "
            "got the string 'blocking'",
        ),
        (
            _set(["rules", 0, "active"], "yes"),
            "rules[0].active: expected a boolean or null, got the string 'yes'",
        ),
    ],
)
def test_malformed_documents_name_the_field(change, message) -> None:
    with pytest.raises(TemplateError) as raised:
        load_template(_broken(change))
    assert str(raised.value).startswith(message)


def test_duplicates_are_rejected() -> None:
    raw = document()
    raw["tables"].append(copy.deepcopy(raw["tables"][0]))
    raw["tables"][1]["code"] = "t_01.00"
    raw["tables"][1]["cells"][0]["id"] = "b"
    with pytest.raises(
        TemplateError, match=r"tables\[1\]\.code: 't_01.00' repeats tables\[0\]\.code"
    ):
        load_template(raw)
    raw["tables"][1]["code"] = "T_02.00"
    raw["tables"][1]["cells"][0]["id"] = "a"
    with pytest.raises(
        TemplateError,
        match=r"tables\[1\]\.cells\[0\]\.id: 'a' repeats tables\[0\]\.cells\[0\]\.id",
    ):
        load_template(raw)
    raw["tables"][1]["cells"][0]["id"] = "b"
    raw["tables"][1]["open_keys"].append({"code": "qCD", "column": "qAB"})
    with pytest.raises(TemplateError, match=r"open_keys\[1\]\.column: 'qAB' repeats"):
        load_template(raw)


@pytest.mark.parametrize("text", ["null", "[]", '"text"', "3"])
def test_document_must_be_an_object(tmp_path: Path, text: str) -> None:
    path = tmp_path / "template.json"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(TemplateError, match="template: expected an object"):
        load_template(path)


def test_unreadable_files(tmp_path: Path) -> None:
    with pytest.raises(
        TemplateError, match=r"missing\.json: cannot read: No such file"
    ):
        load_template(tmp_path / "missing.json")
    with pytest.raises(TemplateError, match="cannot read"):
        load_template(tmp_path)
    binary = tmp_path / "binary.json"
    binary.write_bytes(b"\xff\xfe\x00")
    with pytest.raises(TemplateError, match=r"binary\.json: cannot read"):
        load_template(binary)
    broken = tmp_path / "broken.json"
    broken.write_text('{"format": ', encoding="utf-8")
    with pytest.raises(
        TemplateError, match=r"broken.json: not JSON: Expecting value: line 1 column 12"
    ):
        load_template(broken)
    deep = tmp_path / "deep.json"
    deep.write_text("[" * 100_000 + "]" * 100_000, encoding="utf-8")
    with pytest.raises(
        # A large enough stack parses the array, which is then not an object.
        TemplateError,
        match=r"deep\.json: (JSON nested too deeply|not JSON)|expected an object",
    ):
        load_template(deep)


def test_template_error_is_a_value_error() -> None:
    assert issubclass(TemplateError, ValueError)


def test_huge_numbers_and_nul_paths(tmp_path: Path) -> None:
    huge = tmp_path / "huge.json"
    huge.write_text('{"format": ' + "9" * 5000 + "}", encoding="utf-8")
    with pytest.raises(TemplateError, match=r"huge\.json: not JSON: Exceeds the limit"):
        load_template(huge)
    with pytest.raises(TemplateError, match="cannot read: embedded null byte"):
        load_template(str(tmp_path / "a\x00b.json"))


@pytest.mark.parametrize(
    ("path", "where"),
    [
        (["entry_point"], "entry_point"),
        (["tables", 0, "filing_indicator"], "tables[0].filing_indicator"),
        (["tables", 0, "cells", 0, "datapoint"], "tables[0].cells[0].datapoint"),
        (["tables", 0, "open_keys", 0, "column"], "tables[0].open_keys[0].column"),
        (["rules", 0, "expression"], "rules[0].expression"),
    ],
)
def test_lone_surrogates_are_rejected(path, where) -> None:
    raw = _broken(_set(path, "x\ud800"))
    with pytest.raises(TemplateError) as raised:
        load_template(raw)
    assert str(raised.value) == (
        f"{where}: 'x\\ud800' cannot be written as UTF-8 "
        "(a lone surrogate at position 1)"
    )
    items = _broken(_set(["tables", 0, "cells", 0, "items"], ["eba_AB:\udc00"]))
    with pytest.raises(TemplateError, match=r"cells\[0\]\.items\[0\]: .* UTF-8"):
        load_template(items)


def test_repeated_rule_codes_are_rejected() -> None:
    raw = document()
    raw["rules"].append({"code": "v1", "expression": "{tT_01.00, c0010} < 0"})
    with pytest.raises(
        TemplateError, match=r"rules\[1\]\.code: 'v1' repeats rules\[0\]\.code"
    ):
        load_template(raw)
