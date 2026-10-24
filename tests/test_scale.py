import zipfile
from pathlib import Path

import pytest
from dpmxbrl import read_report

from dpmsynth import generate, load_template, write_scaled_package
from tests.support import SAMPLES, cell, document


@pytest.fixture(scope="module")
def result():
    return generate(load_template(SAMPLES / "sample.json"), seed=5)


def test_scaled_package_repeats_solved_rows_under_unique_keys(
    tmp_path: Path, result
) -> None:
    path = tmp_path / "scaled.zip"
    written = write_scaled_package(result.data, path, rows=50)
    # Typed keys get one fresh value per row; enumerated keys cap the rows.
    assert written == {"S_01.00": 14, "S_02.00.a": 4, "S_03.00": 50}
    report = read_report(path)
    typed = [fact for fact in report.facts if fact.template == "s_03.00"]
    assert len({fact.keys["c0010"] for fact in typed}) == 50
    keyed = [fact for fact in report.facts if fact.template == "s_02.00.a"]
    assert {fact.keys["qEBB"] for fact in keyed} == {"eba_qEC:qx16", "eba_qEC:qx23"}
    assert len(report.facts) == sum(written.values())
    for fact in typed:
        assert fact.keys["c0010"].startswith("SYNTHERI")
        digits = int("".join(str(int(c, 36)) for c in fact.keys["c0010"]))
        assert digits % 97 == 1


def test_scaled_package_is_written_as_dpm_xbrl_writes_it(
    tmp_path: Path, result
) -> None:
    from dpmxbrl import write_xbrl_csv

    scaled, plain = tmp_path / "scaled.zip", tmp_path / "plain.zip"
    # Rows as generated: the same files as the unscaled writer's, except
    # that typed keys (S_03.00) get fresh identifiers.
    write_scaled_package(result.data, scaled, rows={})
    write_xbrl_csv(result.report, plain)
    with zipfile.ZipFile(scaled) as first, zipfile.ZipFile(plain) as second:
        names = [name.split("/", 1)[1] for name in first.namelist()]
        assert names == [name.split("/", 1)[1] for name in second.namelist()]
        assert first.namelist()[0].startswith("scaled/")
        for name in names:
            if name != "reports/s_03.00.csv":
                assert first.read(f"scaled/{name}") == second.read(f"plain/{name}"), (
                    name
                )
    read = read_report(scaled)
    assert len(read.facts) == len(read_report(plain).facts)
    assert read.entity_id == "SYNTHETICDPMXL000002.CON"
    assert read.entity_scheme == "https://eurofiling.info/eu/rs"
    assert read.reference_date is not None
    assert read.reference_date.isoformat() == "2026-12-31"
    # Only the file name, which is not an EBA submission name, is flagged.
    assert [finding.code for finding in read.filing] == ["invalidFileName"]
    assert not [warning for warning in read.warnings if "reportPackage" in warning]


def test_rows_per_table(tmp_path: Path, result) -> None:
    written = write_scaled_package(
        result.data, tmp_path / "scaled.zip", rows={"S_03.00": 7}
    )
    assert written["S_03.00"] == 7
    assert written["S_02.00.a"] == 4  # the generated rows


@pytest.mark.parametrize("rows", [0, -1, True, {"S_03.00": 0}, 10**10])
def test_invalid_rows(tmp_path: Path, result, rows) -> None:
    with pytest.raises(ValueError, match="from 1 to 9_999_999_999"):
        write_scaled_package(result.data, tmp_path / "scaled.zip", rows=rows)


def test_several_typed_and_enumerated_keys(tmp_path: Path) -> None:
    template = load_template(
        document(
            [cell("0010", "0010", 1)],
            [],
            open_keys=[
                {"code": "qAB", "items": ["eba_AB:x1", "eba_AB:x2", "eba_AB:x3"]},
                {"code": "a-b", "column": "c0005"},
            ],
        )
    )
    data = generate(template).data
    path = tmp_path / "keys.zip"
    assert write_scaled_package(data, path, rows=4) == {"T": 4}
    facts = read_report(path).facts
    assert [fact.keys["qAB"] for fact in facts] == [
        "eba_AB:x1",
        "eba_AB:x2",
        "eba_AB:x3",
        "eba_AB:x1",
    ]
    assert [fact.keys["c0005"][:8] for fact in facts] == ["SYNTHABX"] * 4
    assert len({fact.keys["c0005"] for fact in facts}) == 4


def test_large_package_streams(tmp_path: Path, result) -> None:
    path = tmp_path / "large.zip"
    written = write_scaled_package(result.data, path, rows=100_000)
    assert written["S_03.00"] == 100_000
    with zipfile.ZipFile(path) as archive:
        info = archive.getinfo("large/reports/s_03.00.csv")
        assert info.file_size > 4_000_000
