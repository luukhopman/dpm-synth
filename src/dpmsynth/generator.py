"""Generate a report that satisfies a module's DPM-XL rules.

The generator is a repair loop, not a complete constraint solver:

1. Every cell gets a plausible random value for its data type, and every open
   table gets a few key rows.
2. All rules are evaluated with :mod:`dpmxl`. For each failing record the
   first failing comparison is located through the evaluation trace and one
   operand is reassigned so the comparison holds: a single cell takes the
   other side's value, or one term of a sum absorbs the difference.
   ``isnull``, ``in`` and ``match`` failures are repaired by clearing, choosing
   a member, or synthesizing a matching identifier.
3. Steps 2 repeats until no rule fails or a round changes nothing.

Totals propagate up hierarchies over successive rounds, so most EBA modules
converge in a few rounds. Rules that still fail (contradictory constraints,
``time_shift``, regular expressions it cannot satisfy) are reported in
:class:`GenerationResult`.
"""

from __future__ import annotations

import random
import re
import string
from collections.abc import Hashable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, cast

from dpmxl import (
    CellQuery,
    DataPoint,
    Evaluation,
    Item,
    Number,
    Value,
    axis_matches,
    evaluate_rule,
    iter_points,
    parse,
)
from dpmxl.ast import (
    Binary,
    Call,
    If,
    In,
    Literal_,
    Node,
    Selection,
    Sub,
    Unary,
    Where,
    With,
    walk,
)
from xbrlreport import Fact, Report

from .template import ModuleTemplate, TemplateCell, TemplateTable

_NUMERIC = {"m", "p", "i", "r"}
_DEFAULT_DECIMALS = {"m": 0, "p": 4, "i": 0, "r": 2}
_DECIMALS_PARAMETERS = {
    "m": "decimalsMonetary",
    "p": "decimalsPercentage",
    "i": "decimalsInteger",
    "r": "decimalsDecimal",
}
_COMPARISONS = {"=", "!=", "<", "<=", ">", ">="}
_NEGATED = {"=": "!=", "!=": "=", "<": ">=", "<=": ">", ">": "<=", ">=": "<"}
_MIRRORED = {"=": "=", "!=": "!=", "<": ">", "<=": ">=", ">": "<", ">=": "<="}

Slot = tuple[str, tuple[tuple[str, Any], ...]]


@dataclass
class GenerationResult:
    """The generated report and how far the repair loop got."""

    report: Report
    rounds: int
    rules: int
    passed: int
    failed: list[str]
    not_evaluated: dict[str, str]
    repairs: int
    history: list[int] = field(default_factory=list)
    data: SyntheticData | None = None


class SyntheticData:
    """Mutable values for a template, exposed as a :class:`dpmxl.DataProvider`."""

    def __init__(
        self, template: ModuleTemplate, rng: random.Random, open_rows: int
    ) -> None:
        """Create initial values and open-table key rows.

        Args:
            template: Module template.
            rng: Random source.
            open_rows: Key rows to generate per open table.
        """
        self.template = template
        self.rng = rng
        self.decimals = {**_DEFAULT_DECIMALS, **template.decimals}
        self.values: dict[Slot, Value] = {}
        self.cells_by_datapoint: dict[str, TemplateCell] = {}
        self.key_rows: dict[str, list[tuple[tuple[str, Any], ...]]] = {}
        self._query_cells: dict[CellQuery, list[TemplateCell]] = {}
        # Slot -> (lower, upper) from single-cell sign rules such as {x} >= 0.
        self.bounds: dict[Slot, tuple[Decimal | None, Decimal | None]] = {}
        for table in template.tables:
            rows = self._key_rows(table, open_rows) if table.open_keys else [()]
            self.key_rows[table.code] = rows
            for cell in table.cells:
                self.cells_by_datapoint.setdefault(cell.datapoint, cell)
                for keys in rows:
                    self.values.setdefault((cell.datapoint, keys), self.initial(cell))

    def _key_rows(
        self, table: TemplateTable, count: int
    ) -> list[tuple[tuple[str, Any], ...]]:
        rows = []
        for index in range(count):
            row = []
            for key in table.open_keys:
                if key.items:
                    value: Any = Item.parse(key.items[index % len(key.items)])
                else:
                    value = lei(self.rng)
                row.append((key.code, value))
            rows.append(tuple(row))
        return list(dict.fromkeys(rows))

    def initial(self, cell: TemplateCell) -> Value:
        """Return a random starting value for a cell's data type.

        Returns:
            Value: The value.
        """
        kind = cell.data_type
        if kind == "m":
            return self.number(cell, Decimal(self.rng.randint(1, 1000) * 1000))
        if kind == "p":
            return self.number(cell, Decimal(self.rng.randint(1, 99)) / 100)
        if kind == "i":
            return self.number(cell, Decimal(self.rng.randint(1, 50)))
        if kind == "r":
            return self.number(cell, Decimal(self.rng.randint(100, 999)) / 100)
        if kind == "e":
            return Item.parse(cell.items[0]) if cell.items else Item("qx", "qx0")
        if kind == "b":
            return True
        if kind == "d":
            return self.template.reference_date or date(2026, 12, 31)
        return lei(self.rng)

    def numeric_slot(self, slot: Any) -> bool:
        """Whether a slot holds a numeric cell that repairs may change.

        Returns:
            bool: ``True`` for numeric data types.
        """
        if not isinstance(slot, tuple) or slot not in self.values:
            return False
        cell = self.cells_by_datapoint.get(slot[0])
        return cell is not None and cell.data_type in _NUMERIC

    def assign(self, slot: Slot, value: Decimal) -> bool:
        """Set an unrounded numeric value, clamped into the slot's bounds.

        Returns:
            bool: Whether the stored value changed.
        """
        lower, upper = self.bounds.get(slot, (None, None))
        if lower is not None and value < lower:
            value = lower
        if upper is not None and value > upper:
            value = upper
        value = value.quantize(Decimal("1e-8"))
        current = self.values.get(slot)
        if isinstance(current, Number) and current.value == value:
            return False
        self.values[slot] = Number(value)
        return True

    def round_all(self) -> None:
        """Round every numeric value to its reporting decimals."""
        for slot, value in self.values.items():
            cell = self.cells_by_datapoint.get(slot[0])
            if isinstance(value, Number) and cell is not None:
                self.values[slot] = self.number(cell, value.value)

    def within_bounds(self, slot: Slot, value: Decimal) -> bool:
        """Whether a value respects the slot's sign-rule bounds.

        Returns:
            bool: ``True`` when no recorded bound is violated.
        """
        lower, upper = self.bounds.get(slot, (None, None))
        return (lower is None or value >= lower) and (upper is None or value <= upper)

    def apply_bounds(self) -> None:
        """Flip or clamp initial values into their sign-rule bounds."""
        for slot, (lower, upper) in self.bounds.items():
            current = self.values.get(slot)
            if not isinstance(current, Number):
                continue
            value = current.value
            if upper is not None and value > upper:
                value = -abs(value) if upper <= 0 else upper
            if lower is not None and value < lower:
                value = abs(value) if lower >= 0 else lower
            self.values[slot] = Number(value)

    def number(self, cell: TemplateCell | None, value: Decimal) -> Number:
        """Round a value to the cell type's reporting decimals.

        Returns:
            Number: An exact number.
        """
        decimals = self.decimals.get(cell.data_type or "", 2) if cell else 2
        quantum = Decimal(1).scaleb(-decimals)
        return Number(value.quantize(quantum, rounding=ROUND_HALF_UP))

    # DataProvider -----------------------------------------------------------

    def select(self, query: CellQuery) -> Sequence[DataPoint]:
        """Return selected cells for every key row of the table.

        Returns:
            Sequence[DataPoint]: Points referencing ``(datapoint, keys)`` slots.

        Raises:
            LookupError: If the table is not in the template.
        """
        table = self.template.table(query.table)
        if table is None:
            raise LookupError(
                f"table {query.table} is not in module {self.template.module}"
            )
        cells = self._query_cells.get(query)
        if cells is None:
            cells = [
                cell
                for cell in table.cells
                if _selected(cell.row, query.rows)
                and _selected(cell.column, query.columns)
                and _selected(cell.sheet, query.sheets)
            ]
            self._query_cells[query] = cells
        points = []
        for keys in self.key_rows[table.code]:
            for cell in cells:
                slot = (cell.datapoint, keys)
                value = self.values.get(slot)
                if isinstance(value, Number):
                    # Reported facts carry their decimals as a tolerance.
                    value = Number.of(
                        value.value, self.decimals.get(cell.data_type or "", 2)
                    )
                points.append(
                    DataPoint(
                        table=table.code,
                        row=cell.row,
                        column=cell.column,
                        sheet=cell.sheet,
                        keys=dict(keys),
                        value=value,
                        ref=slot,
                    )
                )
        return points

    def table_reported(self, table: str) -> bool | None:
        """Every template table is reported.

        Returns:
            bool | None: Whether a table or filing indicator matches.
        """
        folded = table.casefold()
        return any(
            item.code.casefold() == folded
            or item.filing_indicator.casefold() == folded
            or item.code.casefold().startswith(f"{folded}.")
            for item in self.template.tables
        )

    def parameter(self, name: str) -> Value:
        """Return report parameters.

        Returns:
            Value: ``refPeriod`` or ``ReportingLevel``; otherwise ``None``.
        """
        folded = name.casefold()
        if folded == "refperiod":
            return self.template.reference_date or date(2026, 12, 31)
        if folded == "reportinglevel":
            return "con"
        return None


def _selected(code: str | None, selector: Any) -> bool:
    if selector is None or selector.wildcard:
        return True
    if code in (None, "*"):
        return False
    return axis_matches(code, selector)


def lei(rng: random.Random) -> str:
    """Return a random identifier shaped like an LEI.

    Returns:
        str: 18 upper-case alphanumerics followed by two digits.
    """
    alphabet = string.ascii_uppercase + string.digits
    return (
        "".join(rng.choice(alphabet) for _ in range(18)) + f"{rng.randint(0, 99):02d}"
    )


# Repair ---------------------------------------------------------------------


class _Repairer:
    def __init__(
        self,
        data: SyntheticData,
        evaluation: Evaluation,
        key: dict[str, Hashable],
        *,
        rule: str = "",
        owners: dict[Any, set[str]] | None = None,
    ) -> None:
        self.data = data
        self.evaluation = evaluation
        self.key = key
        self.rule = rule
        self.owners = owners or {}

    def value(self, node: Node) -> Value | None:
        records = self.evaluation.value_at(node, self.key)
        return records[0].value if len(records) == 1 else None

    def points(self, node: Node) -> list[DataPoint]:
        return [
            point
            for record in self.evaluation.value_at(node, self.key)
            for point in iter_points(record.points)
        ]

    def fix(self, node: Node, desired: bool) -> bool:
        while isinstance(node, With):
            node = node.body
        current = self.value(node)
        if current is desired:
            return False
        match node:
            case Unary(op="not", operand=operand):
                return self.fix(operand, not desired)
            case Binary(op="and", left=left, right=right):
                if desired:
                    changed = self.fix(left, True)
                    return self.fix(right, True) or changed
                return self.fix(left, False)
            case Binary(op="or", left=left, right=right):
                if desired:
                    return self.fix(left, True) or self.fix(right, True)
                changed = self.fix(left, False)
                return self.fix(right, False) or changed
            case Binary(op=op) if op in _COMPARISONS:
                return self.comparison(node, op if desired else _NEGATED[op])
            case If(condition=condition, then=then, otherwise=otherwise):
                verdict = self.value(condition)
                if verdict is True:
                    return self.fix(then, desired)
                if verdict is False and otherwise is not None:
                    return self.fix(otherwise, desired)
                return False
            case In(operand=operand, values=values) if desired:
                member = (
                    self.evaluation.value_at(values.items[0], {})
                    if values.items
                    else []
                )
                target = _literal(values.items[0]) if values.items else None
                if target is None and member:
                    target = member[0].value
                return self.assign_all(operand, target)
            case Call(name="isnull", args=(operand,)):
                if desired:
                    return self.assign_all(operand, None)
                return self.fill(operand)
            case Call(name="match", args=(operand, pattern)) if desired:
                text = _matching_text(_literal(pattern), self.data.rng)
                return text is not None and self.assign_all(operand, text)
        return False

    def assign_all(self, node: Node, value: Value) -> bool:
        changed = False
        for point in self.points(node):
            changed = self.put(point.ref, value) or changed
        return changed

    def fill(self, node: Node) -> bool:
        changed = False
        for point in self.points(node):
            slot = cast(Slot, point.ref)
            if self.data.values.get(slot) is None:
                cell = self.data.cells_by_datapoint.get(slot[0])
                if cell is not None:
                    changed = self.put(slot, self.data.initial(cell)) or changed
        return changed

    def put(self, slot: Any, value: Value) -> bool:
        if not isinstance(slot, tuple) or slot not in self.data.values:
            return False
        cell = self.data.cells_by_datapoint.get(slot[0])
        if isinstance(value, Number) and cell is not None:
            if cell.data_type not in _NUMERIC:
                return False
            value = self.data.number(cell, value.value)
            if not self.data.within_bounds(slot, value.value):
                return False
        if self.data.values.get(slot) == value:
            return False
        self.data.values[slot] = value
        return True

    def comparison(self, node: Binary, op: str) -> bool:
        left, right = self.value(node.left), self.value(node.right)
        numeric = isinstance(left, Number | type(None)) and isinstance(
            right, Number | type(None)
        )
        if numeric and (left is not None or right is not None):
            return self.linear(node, op)
        if op == "=" and right is not None:
            return self.assign_all(node.left, right)
        if op == "=" and left is not None:
            return self.assign_all(node.right, left)
        return False

    def linear(self, node: Binary, op: str) -> bool:
        """Solve ``left op right`` by moving one cell of the linearized difference.

        ``left - right`` is expanded into terms ``coefficient * cell``; products
        of two cells are linearized at the current values. The chosen cell is
        the first one no other rule defines and whose new value respects its
        sign bounds, so a total owned by one rule is not pulled around by rules
        that merely use it.

        Returns:
            bool: Whether a value changed.
        """
        difference = _value(self.value(node.left)) - _value(self.value(node.right))
        goal = _goal(op, difference)
        if goal is None:
            return False
        terms = self.terms(node.left, Decimal(1)) + self.terms(node.right, Decimal(-1))
        owners = self.owners

        def rank(item: tuple[int, tuple[Any, Decimal]]) -> tuple[int, int]:
            index, (slot, _coefficient) = item
            others = owners.get(slot, set()) - {self.rule}
            return (1 if others else 0, index)

        for _index, (slot, coefficient) in sorted(enumerate(terms), key=rank):
            if not coefficient or not self.data.numeric_slot(slot):
                continue
            current = self.data.values.get(slot)
            base = current.value if isinstance(current, Number) else Decimal(0)
            value = base + (goal - difference) / coefficient
            if self.data.within_bounds(slot, value) and self.data.assign(slot, value):
                return True
        return False

    def terms(self, node: Node, coefficient: Decimal) -> list[tuple[Any, Decimal]]:
        """Expand an arithmetic node into ``(slot, coefficient)`` terms.

        Returns:
            list[tuple[Any, Decimal]]: Cells whose change moves the node linearly.
        """
        node = _unwrap(node)
        match node:
            case Binary(op="+", left=left, right=right):
                return self.terms(left, coefficient) + self.terms(right, coefficient)
            case Binary(op="-", left=left, right=right):
                return self.terms(left, coefficient) + self.terms(right, -coefficient)
            case Unary(op="-", operand=operand):
                return self.terms(operand, -coefficient)
            case Unary(op="+", operand=operand):
                return self.terms(operand, coefficient)
            case Binary(op="*", left=left, right=right):
                return self.terms(
                    left, coefficient * _value(self.value(right))
                ) + self.terms(right, coefficient * _value(self.value(left)))
            case Binary(op="/", left=left, right=right):
                divisor = _value(self.value(right))
                return self.terms(left, coefficient / divisor) if divisor else []
            case Call(name="sum") | Selection() | Where() | Sub():
                return [
                    (point.ref, coefficient)
                    for point in reversed(self.points(node))
                    if isinstance(point.ref, tuple)
                ]
            case Call(name="abs", args=(operand,)):
                sign = Decimal(-1) if _value(self.value(operand)) < 0 else Decimal(1)
                return self.terms(operand, coefficient * sign)
        return []


def _unwrap(node: Node) -> Node:
    while isinstance(node, With):
        node = node.body
    return node


def _value(value: Value | None) -> Decimal:
    return value.value if isinstance(value, Number) else Decimal(0)


def _goal(op: str, difference: Decimal) -> Decimal | None:
    """Return the ``left - right`` difference that satisfies ``op``.

    Returns:
        Decimal | None: The nearest satisfying difference.
    """
    match op:
        case "=" | "<=" | ">=":
            return Decimal(0)
        case ">" | "!=":
            return Decimal(1)
        case "<":
            return Decimal(-1)
    return None


def _literal(node: Node) -> Value:
    if isinstance(node, Literal_):
        if node.kind == "number" and isinstance(node.value, Decimal):
            return Number(node.value)
        return cast(Value, node.value)
    return None


_LEI_PATTERN = re.compile(r"\[A-Z0-9\]\{18\}\[0-9\]\{2\}")


def _matching_text(pattern: Value, rng: random.Random) -> str | None:
    if not isinstance(pattern, str):
        return None
    if _LEI_PATTERN.search(pattern):
        return lei(rng)
    date_like = re.fullmatch(
        r"\^?\[0-9\]\{2\}\[/\]\{1\}\[0-9\]\{2\}\[/\]\{1\}\[0-9\]\{4\}\$?", pattern
    )
    if date_like:
        return "31/12/2026"
    return None


# Driver ---------------------------------------------------------------------


def generate(
    template: ModuleTemplate,
    *,
    seed: int = 0,
    open_rows: int = 2,
    max_rounds: int = 40,
    entity: str = "SYNTHETICDPMXL000002",
    reporting_level: str = "CON",
    reference_date: date | None = None,
) -> GenerationResult:
    """Generate a report for ``template`` that satisfies as many rules as possible.

    Args:
        template: Module template.
        seed: Random seed; the same seed and template give the same report.
        open_rows: Key rows per open table.
        max_rounds: Upper bound on evaluate-and-repair rounds.
        entity: LEI of the reporting entity.
        reporting_level: ``CON`` or ``IND`` suffix of the entity identifier.
        reference_date: Overrides the template's reference date.

    Returns:
        GenerationResult: The report and the final rule status.
    """
    if reference_date is not None:
        template = _with_reference_date(template, reference_date)
    rng = random.Random(seed)  # ruff: ignore[suspicious-non-cryptographic-random-usage] - reproducible test data, not secrets
    data = SyntheticData(template, rng, open_rows)
    parsed = []
    for rule in template.rules:
        try:
            parsed.append((rule, parse(rule.expression), rule.precondition))
        except ValueError:
            continue
    owners = _definitions(parsed, data)
    data.apply_bounds()
    history: list[int] = []
    repairs = 0
    rounds = 0
    for rounds in range(1, max_rounds + 1):  # ruff: ignore[unused-loop-control-variable] - reported after the loop
        failing, changed = 0, 0
        for rule, node, precondition in parsed:
            result = evaluate_rule(node, data, precondition=precondition)
            if result.status != "failed" or result.evaluation is None:
                continue
            failing += 1
            for outcome in result.failures:
                repairer = _Repairer(
                    data,
                    result.evaluation,
                    dict(outcome.key),
                    rule=rule.code,
                    owners=owners,
                )
                if repairer.fix(result.evaluation.root, True):
                    changed += 1
        history.append(failing)
        repairs += changed
        if not failing or not changed or _stalled(history):
            break
    data.round_all()
    passed = 0
    failed: list[str] = []
    not_evaluated: dict[str, str] = {}
    for rule, node, precondition in parsed:
        result = evaluate_rule(node, data, precondition=precondition, trace=False)
        if result.status == "passed":
            passed += 1
        elif result.status == "failed":
            failed.append(rule.code)
        elif result.status in {"error", "unsupported"}:
            not_evaluated[rule.code] = result.message or result.status
    return GenerationResult(
        report=build_report(
            template, data, entity=entity, reporting_level=reporting_level
        ),
        rounds=rounds,
        rules=len(template.rules),
        passed=passed,
        failed=failed,
        not_evaluated=not_evaluated,
        repairs=repairs,
        history=history,
        data=data,
    )


def _stalled(history: list[int], window: int = 6) -> bool:
    """Whether the failing-rule count stopped improving (an oscillation).

    Returns:
        bool: ``True`` when the last ``window`` rounds found no new minimum.
    """
    if len(history) <= window:
        return False
    return min(history[-window:]) >= min(history[:-window])


def _definitions(
    parsed: list[tuple[Any, Node, str | None]], data: SyntheticData
) -> dict[Any, set[str]]:
    """Map each cell to the rules whose equality defines it.

    A rule defines a cell when one side of an ``=`` comparison is that single
    cell, preferring the left side.

    Returns:
        dict[Any, set[str]]: Slot to rule codes.
    """
    owners: dict[Any, set[str]] = {}
    inputs: dict[str, set[Any]] = {}
    for rule, node, precondition in parsed:
        result = evaluate_rule(node, data, precondition=precondition)
        evaluation = result.evaluation
        if evaluation is None:
            continue
        _record_bounds(_unwrap(node), evaluation, data)
        for comparison in walk(node):
            if not (isinstance(comparison, Binary) and comparison.op == "="):
                continue
            for side, other in (
                (comparison.left, comparison.right),
                (comparison.right, comparison.left),
            ):
                side = _unwrap(side)
                if not isinstance(side, Selection | Where | Sub):
                    continue
                recordset = evaluation.trace.get(id(side))
                if recordset is None:
                    continue
                for record in recordset.records.values():
                    if len(record.points) == 1:
                        owners.setdefault(record.points[0].ref, set()).add(rule.code)
                used = evaluation.trace.get(id(_unwrap(other)))
                if used is not None:
                    inputs.setdefault(rule.code, set()).update(
                        point.ref
                        for record in used.records.values()
                        for point in iter_points(record.points)
                    )
                break
    _order_by_depth(parsed, owners, inputs)
    return owners


def _order_by_depth(
    parsed: list[tuple[Any, Node, str | None]],
    owners: dict[Any, set[str]],
    inputs: dict[str, set[Any]],
) -> None:
    """Sort rules so definitions of components run before their totals.

    A rule's depth is one more than the deepest rule defining any of its
    inputs; cycles are cut after a fixed number of relaxation passes.
    """
    depth: dict[str, int] = {}
    for _ in range(25):
        changed = False
        for rule, _node, _precondition in parsed:
            value = 1 + max(
                (
                    depth.get(owner, 0)
                    for slot in inputs.get(rule.code, ())
                    for owner in owners.get(slot, ())
                    if owner != rule.code
                ),
                default=0,
            )
            if depth.get(rule.code) != value:
                depth[rule.code] = value
                changed = True
        if not changed:
            break
    parsed.sort(key=lambda item: depth.get(item[0].code, 0))


def _record_bounds(node: Node, evaluation: Evaluation, data: SyntheticData) -> None:
    """Record ``{cells} op constant`` sign rules as per-cell bounds."""
    if not (isinstance(node, Binary) and node.op in {">=", ">", "<=", "<"}):
        return
    left, right, op = _unwrap(node.left), _unwrap(node.right), node.op
    if isinstance(left, Literal_):
        left, right, op = right, left, _MIRRORED[op]
    constant = _literal(right)
    if not isinstance(constant, Number) or not isinstance(
        left, Selection | Where | Sub
    ):
        return
    recordset = evaluation.trace.get(id(left))
    if recordset is None:
        return
    for record in recordset.records.values():
        for point in iter_points(record.points):
            lower, upper = data.bounds.get(cast(Slot, point.ref), (None, None))
            if op in {">=", ">"}:
                bound = constant.value + (1 if op == ">" else 0)
                lower = bound if lower is None else max(lower, bound)
            else:
                bound = constant.value - (1 if op == "<" else 0)
                upper = bound if upper is None else min(upper, bound)
            data.bounds[cast(Slot, point.ref)] = (lower, upper)


def _with_reference_date(template: ModuleTemplate, value: date) -> ModuleTemplate:
    return ModuleTemplate(
        release=template.release,
        module=template.module,
        entry_point=template.entry_point,
        tables=template.tables,
        rules=template.rules,
        reference_date=value,
        decimals=template.decimals,
    )


def build_report(
    template: ModuleTemplate,
    data: SyntheticData,
    *,
    entity: str,
    reporting_level: str,
) -> Report:
    """Turn generated values into an xBRL-CSV style report.

    Returns:
        Report: Datapoint facts per table, filing indicators and parameters.
    """
    facts: list[Fact] = []
    emitted: set[tuple[str, Slot]] = set()
    for table in template.tables:
        for keys in data.key_rows[table.code]:
            for cell in table.cells:
                slot = (cell.datapoint, keys)
                value = data.values.get(slot)
                if value is None or (table.code, slot) in emitted:
                    continue
                emitted.add((table.code, slot))
                facts.append(
                    Fact(
                        _lexical(value),
                        datapoint=cell.datapoint,
                        template=table.code.lower(),
                        keys={
                            _column(table, name): _lexical(key) for name, key in keys
                        },
                    )
                )
    decimals = {**_DEFAULT_DECIMALS, **template.decimals}
    used_types = {cell.data_type for table in template.tables for cell in table.cells}
    return Report(
        format="xbrl-csv",
        entry_point=template.entry_point,
        # A subject with a suffix uses the reporting-subject scheme (EBA
        # filing rule 3.6).
        entity_scheme="https://eurofiling.info/eu/rs",
        entity_id=f"{entity}.{reporting_level}",
        reference_date=template.reference_date or date(2026, 12, 31),
        base_currency="iso4217:EUR",
        parameters={},
        decimals_parameters={
            parameter: decimals[kind]
            for kind, parameter in _DECIMALS_PARAMETERS.items()
            if kind in used_types
        },
        filing_indicators=dict.fromkeys(
            dict.fromkeys(t.filing_indicator for t in template.tables), True
        ),
        facts=tuple(facts),
        namespaces={
            "rs": "https://eurofiling.info/eu/rs",
            "iso4217": "http://www.xbrl.org/2003/iso4217",
        },
    )


def _column(table: TemplateTable, code: str) -> str:
    return next((key.column for key in table.open_keys if key.code == code), code)


def _lexical(value: Value | Any) -> str:
    if isinstance(value, Number):
        return format(value.value, "f")
    if isinstance(value, Item):
        return f"eba_{value.category}:{value.code}" if value.category else value.code
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def summarize(result: GenerationResult) -> Iterable[str]:
    """Yield human-readable summary lines.

    Yields:
        str: One line per fact.
    """
    failed = len(result.failed)
    yield f"rules: {result.rules}, passed: {result.passed}, failed: {failed}"
    yield f"rounds: {result.rounds} (failing rules per round: {result.history})"
    yield f"repairs: {result.repairs}, facts: {len(result.report.facts)}"
    if result.failed:
        yield f"still failing: {', '.join(result.failed[:20])}"
    if result.not_evaluated:
        yield f"not evaluated: {len(result.not_evaluated)}"


__all__ = [
    "GenerationResult",
    "SyntheticData",
    "build_report",
    "generate",
    "lei",
    "summarize",
]
