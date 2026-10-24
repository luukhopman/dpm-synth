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
        TemplateRule("v1", "{tT_01.00, c0010} >= 0", None, "eba"),
    )
    assert template.reference_date is None
    assert template.entry_point is None
    assert template.decimals == {}


def test_optional_fields_and_unknown_fields() -> None:
    raw = document()
    raw["decimals"] = {"m": -3, "p": 6}
    raw["reference_date"] = "2025-06-30"
    raw["generator"] = "a newer export"  # unknown fields are ignored
    raw["tables"][0]["filing_indicator"] = "T_01"
    raw["tables"][0]["open_keys"][0]["column"] = "c0010"
    raw["tables"][0]["cells"][0].update(row="0010", column="0010", sheet="*")
    raw["tables"][0]["cells"].append(
        {"id": "b", "datapoint": "dp2", "data_type": "e", "items": []}
    )
    raw["rules"][0].update(precondition="{v_T_01}", source="own")
    snapshot = copy.deepcopy(raw)
    template = load_template(raw)
    assert raw == snapshot  # the document is not changed
    assert template.decimals == {"m": -3, "p": 6}
    assert template.reference_date == date(2025, 6, 30)
    table = template.tables[0]
    assert table.filing_indicator == "T_01"
    assert table.open_keys[0].column == "c0010"
    assert table.cells[0].sheet == "*"
    assert table.cells[1].items is None  # an empty list allows anything
    assert template.rules[0].precondition == "{v_T_01}"
    assert template.rules[0].source == "own"


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
            "format: expected 'dpm-synth-template/1', got 'dpm-synth-template/2'",
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
        TemplateError, match=r"deep\.json: (JSON nested too deeply|not JSON)"
    ):
        load_template(deep)


def test_template_error_is_a_value_error() -> None:
    assert issubclass(TemplateError, ValueError)
