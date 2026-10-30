import json
import shutil
from pathlib import Path

import pytest
from dpmxbrl import read_report

from dpmsynth import __version__
from dpmsynth.cli import main
from tests.support import SAMPLES, cell, document


@pytest.fixture
def sample(tmp_path: Path) -> Path:
    return Path(shutil.copy(SAMPLES / "sample.json", tmp_path / "sample.json"))


def write(tmp_path: Path, raw) -> Path:
    path = tmp_path / "template.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return path


def test_generate_writes_the_package(tmp_path: Path, sample: Path, capsys) -> None:
    output = tmp_path / "report.zip"
    assert main(["generate", str(sample), "-o", str(output), "--seed", "5"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == ("rules: 9, passed: 8, failed: 0, unsupported: 1")
    assert lines[1].startswith("rounds: ")
    assert lines[2].startswith("rule prior-period (unsupported): The rule compares")
    assert lines[-1] == f"wrote {output} (20 facts)"
    report = read_report(output)
    assert len(report.facts) == 20
    assert report.entity_id == "SYNTHETICDPMXL000002.CON"


def test_options(tmp_path: Path, sample: Path) -> None:
    output = tmp_path / "report.zip"
    arguments = ["generate", str(sample), "-o", str(output)]
    options = [
        "--entity", "SYNTHETICDPMXL000002",
        "--level", "IND",
        "--reference-date", "2025-06-30",
        "--open-rows", "1",
        "--max-rounds", "10",
        "--currency", "SEK",
    ]  # fmt: skip
    assert main([*arguments, *options]) == 0
    report = read_report(output)
    assert report.entity_id == "SYNTHETICDPMXL000002.IND"
    assert str(report.reference_date) == "2025-06-30"
    assert report.base_currency == "iso4217:SEK"
    assert len([fact for fact in report.facts if fact.template == "s_03.00"]) == 1


def test_json_summary(tmp_path: Path, sample: Path, capsys) -> None:
    output = tmp_path / "report.zip"
    assert main(["generate", str(sample), "-o", str(output), "--json"]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert list(summary) == [
        "schema_version",
        "tool",
        "version",
        "summary",
        "output",
        "release",
        "module",
        "seed",
        "rounds",
        "history",
        "repairs",
        "results",
    ]
    assert summary["schema_version"] == 2
    assert summary["tool"] == "dpm-synth"
    assert summary["version"] == __version__
    assert summary["summary"] == {
        "rules": 9,
        "passed": 8,
        "failed": 0,
        "not_applicable": 0,
        "error": 0,
        "unsupported": 1,
        "skipped": 0,
        "facts": 20,
    }
    assert summary["module"] == "SAMPLE"
    results = {result["rule"]: result for result in summary["results"]}
    assert len(results) == 9
    assert results["rows"] == {
        "rule": "rows",
        "severity": "error",
        "status": "passed",
        "message": None,
    }
    assert results["prior-period"]["status"] == "unsupported"
    assert "time_shift" in results["prior-period"]["message"]


def test_failing_rules_exit_with_status_1(tmp_path: Path, capsys) -> None:
    template = write(
        tmp_path,
        document(
            [cell("0010", "0010", 1)],
            ["{tT, r0010, c0010} > 10", "{tT, r0010, c0010} < 5"],
        ),
    )
    output = tmp_path / "report.zip"
    assert main(["generate", str(template), "-o", str(output)]) == 1
    assert "still failing: r" in capsys.readouterr().out
    assert output.exists()


def test_scale_rows(tmp_path: Path, sample: Path, capsys) -> None:
    output = tmp_path / "big.zip"
    status = main(["generate", str(sample), "-o", str(output), "--scale-rows", "50"])
    assert status == 0  # the status is that of the unscaled report
    assert capsys.readouterr().out.splitlines()[-1] == f"wrote {output} (68 facts)"
    assert len(read_report(output).facts) == 68


@pytest.mark.parametrize(
    "text",
    [
        '{"format": "other"}',
        "not json",
        '{"format": "dpm-synth-template/1", "release": "1", "module": "M", "tables": []}',
        '{"format": "dpm-synth-template/1", "release": "1", "module": "M", '
        '"tables": [{"code": "T", "cells": [{"id": "a", "datapoint": "dp1"}]}], '
        '"rules": [{"code": "v1", "expression": "{tT, c0010} >"}]}',
    ],
)
def test_invalid_templates_exit_with_status_3(tmp_path: Path, capsys, text) -> None:
    path = tmp_path / "bad.json"
    path.write_text(text, encoding="utf-8")
    assert main(["generate", str(path), "-o", str(tmp_path / "x.zip")]) == 3
    error = capsys.readouterr().err
    assert error.startswith("error: ")
    assert "Traceback" not in error
    assert not (tmp_path / "x.zip").exists()


def test_missing_template_exits_with_status_3(tmp_path: Path, capsys) -> None:
    status = main(
        ["generate", str(tmp_path / "nope.json"), "-o", str(tmp_path / "x.zip")]
    )
    assert status == 3
    assert (
        "nope.json: cannot read: No such file or directory" in capsys.readouterr().err
    )


def test_unwritable_output_exits_with_status_3(
    tmp_path: Path, sample: Path, capsys
) -> None:
    output = tmp_path / "missing" / "report.zip"
    assert main(["generate", str(sample), "-o", str(output)]) == 3
    assert f"error: {output}: cannot write: No such file or directory" in (
        capsys.readouterr().err
    )


@pytest.mark.parametrize(
    "options",
    [
        [],
        ["generate"],
        ["generate", "t.json"],
        ["generate", "t.json", "-o", "report.csv"],
        ["generate", "t.json", "-o", "r.zip", "--open-rows", "0"],
        ["generate", "t.json", "-o", "r.zip", "--open-rows", "1001"],
        ["generate", "t.json", "-o", "r.zip", "--scale-rows", "10000000000"],
        ["generate", "t.json", "-o", "r.zip", "--reference-date", "20261231"],
        ["generate", "t.json", "-o", "r.zip", "--max-rounds", "-1"],
        ["generate", "t.json", "-o", "r.zip", "--scale-rows", "many"],
        ["generate", "t.json", "-o", "r.zip", "--reference-date", "31/12/2026"],
        ["generate", "t.json", "-o", "r.zip", "--entity", "not an lei"],
        ["generate", "t.json", "-o", "r.zip", "--level", "SUB"],
        ["generate", "t.json", "-o", "r.zip", "--currency", "eur"],
        ["generate", "t.json", "-o", "r.zip", "--seed", "x"],
        ["inspect"],
    ],
)
def test_usage_errors_exit_with_status_2(options, capsys) -> None:
    with pytest.raises(SystemExit) as raised:
        main(options)
    assert raised.value.code == 2
    assert "usage: dpm-synth" in capsys.readouterr().err


def test_version_and_help(capsys) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["--version"])
    assert raised.value.code == 0
    assert capsys.readouterr().out == f"dpm-synth {__version__}\n"
    with pytest.raises(SystemExit):
        main(["--help"])
    help_text = capsys.readouterr().out
    assert "examples:" in help_text
    assert "dpm-synth generate template.json -o report.zip --seed 7" in help_text
    assert "exit statuses:" in help_text
    # Failing warnings exit with status 0 unless --fail-on warning.
    assert "every evaluable rule passes" not in help_text
    assert "failing warnings exit 0" in help_text


def test_any_write_failure_exits_with_status_3(
    tmp_path: Path, sample: Path, capsys, monkeypatch
) -> None:
    def fail(*args, **kwargs):
        raise UnicodeEncodeError("utf-8", "\ud800", 0, 1, "surrogates not allowed")

    monkeypatch.setattr("dpmsynth.cli.write_xbrl_csv", fail)
    output = tmp_path / "report.zip"
    assert main(["generate", str(sample), "-o", str(output)]) == 3
    error = capsys.readouterr().err
    assert error.startswith(f"error: {output}: cannot write: ")
    assert "Traceback" not in error


def test_severity_and_inactive_rules(tmp_path: Path, capsys) -> None:
    rules = [
        {"code": "low", "expression": "{tT, r0010, c0010} > 10", "severity": "warning"},
        {"code": "high", "expression": "{tT, r0010, c0010} < 5", "severity": "warning"},
        {"code": "off", "expression": "{tT, r0010, c0010} = 7", "active": False},
    ]
    template = write(tmp_path, document([cell("0010", "0010", 1)], rules))
    arguments = ["generate", str(template), "-o", str(tmp_path / "report.zip")]
    # Failing warnings fail the run only with --fail-on warning.
    assert main(arguments) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].endswith("skipped: 1")
    assert lines[2] in {"still failing: low (warning)", "still failing: high (warning)"}
    assert main([*arguments, "--fail-on", "warning"]) == 1
    capsys.readouterr()
    assert main([*arguments, "--json"]) == 0
    results = json.loads(capsys.readouterr().out)["results"]
    assert results[2] == {
        "rule": "off",
        "severity": "error",
        "status": "skipped",
        "message": None,
    }
    assert {result["severity"] for result in results[:2]} == {"warning"}


def test_failing_errors_fail_with_either_threshold(tmp_path: Path) -> None:
    rules = ["{tT, r0010, c0010} > 10", "{tT, r0010, c0010} < 5"]
    template = write(tmp_path, document([cell("0010", "0010", 1)], rules))
    arguments = ["generate", str(template), "-o", str(tmp_path / "report.zip")]
    assert main([*arguments, "--fail-on", "error"]) == 1
    assert main([*arguments, "--fail-on", "warning"]) == 1


def test_rules_that_cannot_be_evaluated(tmp_path: Path, capsys) -> None:
    # An error rule fails the run like a failing rule; unsupported never does.
    rules = [
        {"code": "bad", "expression": '{tT, r0010, c0010} + "a" > 0'},
        {"code": "new", "expression": "unknownfn({tT, r0010, c0010}) > 0"},
    ]
    template = write(tmp_path, document([cell("0010", "0010", 1)], rules))
    arguments = ["generate", str(template), "-o", str(tmp_path / "report.zip")]
    assert main(arguments) == 1
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "rules: 2, passed: 0, failed: 0, error: 1, unsupported: 1"
    assert "rule bad (error): + needs numbers, found string" in lines
    del rules[0]
    template = write(tmp_path, document([cell("0010", "0010", 1)], rules))
    assert main(arguments) == 0
    warning = [{"code": "bad", "expression": '{tT, r0010, c0010} + "a" > 0',
                "severity": "warning"}]  # fmt: skip
    template = write(tmp_path, document([cell("0010", "0010", 1)], warning))
    assert main(arguments) == 0
    assert main([*arguments, "--fail-on", "warning"]) == 1


def test_size_and_fill(tmp_path: Path, sample: Path) -> None:
    full, sparse = tmp_path / "full.zip", tmp_path / "sparse.zip"
    assert main(["generate", str(sample), "-o", str(full)]) == 0
    options = ["--size", "large", "--fill", "0.4"]
    assert main(["generate", str(sample), "-o", str(sparse), *options]) == 0
    assert len(read_report(sparse).facts) < len(read_report(full).facts)


@pytest.mark.parametrize("option", [["--fill", "0"], ["--fill", "x"], ["--size", "xl"]])
def test_bad_size_and_fill_are_usage_errors(tmp_path: Path, sample, option) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["generate", str(sample), "-o", str(tmp_path / "r.zip"), *option])
    assert raised.value.code == 2


def test_messages_are_capped_like_the_failing_rules(tmp_path: Path, capsys) -> None:
    rules = [
        {"code": f"bad{n:02}", "expression": '{tT, r0010, c0010} + "a" > 0'}
        for n in range(25)
    ]
    template = write(tmp_path, document([cell("0010", "0010", 1)], rules))
    assert main(["generate", str(template), "-o", str(tmp_path / "report.zip")]) == 1
    lines = capsys.readouterr().out.splitlines()
    shown = [line for line in lines if line.startswith("rule bad")]
    expected = [
        f"rule bad{n:02} (error): + needs numbers, found string" for n in range(20)
    ]
    assert shown == expected
    assert lines[lines.index(shown[-1]) + 1] == "and 5 more rules"
