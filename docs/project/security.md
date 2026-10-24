---
description: How to report a security vulnerability in dpm-synth, and what counts as one.
---

# Security policy

dpm-synth reads templates and writes report packages. Templates are
usually exported by your own tools, but they may come from elsewhere, so
bugs in reading them can matter.

## Supported versions

Security fixes are released for the latest minor version of the latest
major version.

## Reporting a vulnerability

Please report vulnerabilities privately, not in a public issue: use
[GitHub's private vulnerability reporting](https://github.com/luukhopman/dpm-synth/security/advisories/new)
for the repository, or e-mail github@luukhopman.nl. Include the dpm-synth,
dpm-xl, dpm-xbrl and Python versions, and, if you can, a small template that
shows the problem.

The fix is released as a patch version and described in the changelog.

## What counts

- Loading a template raises anything other than `TemplateError`, or the
  command line prints a traceback, for any template file.
- Generating writes files other than the output package, makes a network
  request, or runs code from the template. Rules are DPM-XL, evaluated by
  dpm-xl, never Python.
- A written package lets a reader escape its root folder, for example
  through a table code; table codes are restricted to safe file names.

Generation time grows with the size of a template and its rules, and
scaled packages are as large as asked for; bound `--scale-rows` and the
template size when they come from untrusted sources. Problems in reading or
writing packages, or in evaluating rules, belong to
[dpm-xbrl](https://luukhopman.github.io/dpm-xbrl/project/security/) and
[dpm-xl](https://luukhopman.github.io/dpm-xl/project/security/).
