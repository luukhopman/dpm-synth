---
description: Reproduce a synthetic report byte for byte with seeds - what the output depends on, how to vary it, and how to keep test fixtures stable across upgrades.
---

# Reproduce a report with seeds

Every random choice dpm-synth makes, starting values and generated
identifiers alike, comes from one random generator seeded with `--seed`
(default 0). The written package has fixed ZIP timestamps and a fixed order
of files and facts, so:

--8<-- "docs/.snippets/reproducible.md"


```python
import hashlib
from pathlib import Path

from dpmxbrl import write_xbrl_csv

from dpmsynth import generate, load_template

template = load_template("sample.json")
for folder, seed in (("first", 7), ("second", 7), ("other", 8)):
    Path(folder).mkdir()
    write_xbrl_csv(generate(template, seed=seed).report, f"{folder}/report.zip")


def digest(folder):
    return hashlib.sha256(Path(folder, "report.zip").read_bytes()).hexdigest()


print(digest("first") == digest("second"))
print(digest("first") == digest("other"))
```

```text
True
False
```

## What the output depends on

In detail, the package is a function of:

- the template, including the order of its tables, cells and rules;
- the seed and the other options: `--open-rows`, `--max-rounds`,
  `--entity`, `--level`, `--reference-date`, `--currency`, `--size`,
  `--fill` and `--scale-rows`;
- the package's file name, which names its root folder (the example
  writes each package as `report.zip`, in its own folder);
- the versions of dpm-synth, dpm-xl and dpm-xbrl.

It does not depend on the machine, the time, the working directory or
Python's hash seed. A patch or minor release of any of the three packages
may change the values generated for a seed, for example when a repair or a
rule's evaluation improves; the [changelog](../project/changelog.md) says
so when it does.

## Several different reports

Use different seeds for reports that differ, such as one report per test
case or a set of reports for a performance test:

```console
$ dpm-synth generate minimal.json -o report-1.zip --seed 1
rules: 2, passed: 2, failed: 0
rounds: 1 (failing rules per round: 0)
wrote report-1.zip (3 facts)
$ dpm-synth generate minimal.json -o report-2.zip --seed 2
rules: 2, passed: 2, failed: 0
rounds: 1 (failing rules per round: 0)
wrote report-2.zip (3 facts)
```

The values differ; on a large module, the number of rounds and the rules
that still fail may differ from seed to seed too.

## Stable test fixtures

To keep a test fixture stable across upgrades, commit the generated package
rather than regenerating it in every test run, and regenerate it on
purpose, with the same seed, when you upgrade. A test that only needs a
valid report of a module can regenerate it each time and check the rule
results instead of the bytes.
