"""Write packages, read them back with dpm-xbrl and evaluate with dpm-xl.

The provider here reads only the written package, so these tests check what
a downstream validator sees, not dpm-synth's own values.
"""

from pathlib import Path

import pytest
from dpmxbrl import read_report, write_xbrl_csv
from dpmxl import evaluate_rule

from dpmsynth import generate, load_template
from tests.support import SAMPLES, PackageProvider

TEMPLATES = sorted(SAMPLES.glob("*.json"))


@pytest.mark.parametrize("path", TEMPLATES, ids=lambda path: path.name)
@pytest.mark.parametrize("seed", [0, 1, 2])
def test_written_package_satisfies_the_rules(
    tmp_path: Path, path: Path, seed: int
) -> None:
    template = load_template(path)
    result = generate(template, seed=seed)
    output = tmp_path / "report.zip"
    write_xbrl_csv(result.report, output)

    report = read_report(output)
    assert not [finding for finding in report.filing if finding.severity == "error"]
    assert _facts(report) == _facts(result.report)
    provider = PackageProvider(template, report)
    statuses = {
        rule.code: evaluate_rule(
            rule.expression, provider, precondition=rule.precondition
        ).status
        for rule in template.rules
    }
    assert [code for code, status in statuses.items() if status == "failed"] == (
        result.failed
    )
    assert sum(status == "passed" for status in statuses.values()) == result.passed
    assert sorted(
        code for code, status in statuses.items() if status == "not_applicable"
    ) == sorted(result.not_applicable)


def test_every_sample_template_passes(tmp_path: Path) -> None:
    for path in TEMPLATES:
        result = generate(load_template(path), seed=7)
        assert result.failed == [], path.name


def test_scaled_package_keeps_row_wise_rules(tmp_path: Path) -> None:
    from dpmsynth import write_scaled_package

    template = load_template(SAMPLES / "sample.json")
    result = generate(template, seed=2)
    output = tmp_path / "scaled.zip"
    write_scaled_package(result.data, output, rows=25)
    provider = PackageProvider(template, read_report(output))
    rule = next(rule for rule in template.rules if rule.code == "lei")
    outcome = evaluate_rule(rule.expression, provider)
    assert outcome.status == "passed"
    assert len(outcome.outcomes) == 25


def _facts(report):
    return sorted(
        (fact.template, fact.datapoint, fact.value, sorted(fact.keys.items()))
        for fact in report.facts
    )
