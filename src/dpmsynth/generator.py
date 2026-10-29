"""Generate a report that satisfies a module's DPM-XL rules.

The generator is an evaluate-and-repair loop, not a complete constraint
solver:

1. Every cell gets a plausible value for its data type, and every open table
   gets a few key rows.
2. Single-cell sign rules become per-cell bounds, and every ``=`` rule with a
   single-cell side defines that cell; rules are ordered so the definitions
   of components run before the totals that use them.
3. All rules are evaluated with dpm-xl. For each failing record the first
   failing comparison is found through the evaluation trace and one cell is
   changed so the comparison holds. ``isnull``, ``in`` and ``match`` failures
   are repaired by clearing, choosing a member, or writing a matching
   identifier.
4. Step 3 repeats until no rule fails, a round changes nothing, or the
   failing count stops improving. Values are then rounded to the reporting
   decimals and every rule is evaluated once more.

How the loop works, and where it stops, is explained at
https://luukhopman.github.io/dpm-synth/concepts/repair-loop/.
"""

from __future__ import annotations

import math
import random
import re
import string
from collections.abc import Hashable, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, cast

from dpmxbrl import Fact, Report
from dpmxl import (
    CellQuery,
    DataPoint,
    DpmXlSyntaxError,
    Evaluation,
    Item,
    Number,
    Value,
    ValueSet,
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
    SetLiteral,
    Sub,
    Unary,
    Where,
    With,
    walk,
)

from .template import (
    _ENUMERATED_TYPES,
    ModuleTemplate,
    OpenKey,
    TemplateCell,
    TemplateTable,
)

DEFAULT_ENTITY = "SYNTHETICDPMXL000002"
"""The fictional LEI that reports are generated for unless told otherwise."""

DEFAULT_REFERENCE_DATE = date(2026, 12, 31)
"""The reference date of a template that gives none."""

MAX_OPEN_ROWS = 1000
"""The most key rows per open table that ``generate`` solves.

Every rule is evaluated on every key row in every round, so the time grows
with the rows; for larger tables, write a scaled package instead.
"""

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
# Repairs never write a number larger than this: past it a linearized product
# or ratio has diverged, and the value would only break other rules.
_LIMIT = Decimal(10) ** 15
_STORED = Decimal("1e-8")
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_RSCHEME = "https://eurofiling.info/eu/rs"

Slot = tuple[str, tuple[tuple[str, Any], ...]]


@dataclass(frozen=True)
class GenerationResult:
    """The generated report and how far the repair loop got.

    ``passed``, ``failed``, ``not_evaluated`` and ``not_applicable`` together
    count every rule of the template once.

    Attributes:
        report: The report, ready for ``dpmxbrl.write_xbrl_csv``.
        data: The generated values, a dpm-xl data provider; pass it to
            [`write_scaled_package`][dpmsynth.write_scaled_package] or
            evaluate rules on it.
        rules: Rules in the template.
        passed: Rules that pass on the final, rounded values.
        failed: Codes of the rules that still fail.
        not_evaluated: Rules dpm-xl could not evaluate, such as
            ``time_shift`` without a previous report, with the reason, by
            rule code.
        not_applicable: Codes of the rules whose precondition is false or
            that select no cell of the template.
        rounds: Evaluate-and-repair rounds run.
        repairs: Failing records repaired over all rounds.
        history: Failing rules at the start of each round.
    """

    report: Report
    data: SyntheticData
    rules: int
    passed: int
    failed: list[str]
    not_evaluated: dict[str, str]
    not_applicable: list[str]
    rounds: int
    repairs: int
    history: list[int] = field(default_factory=list)


class SyntheticData:
    """Generated values for a template, readable as a dpm-xl data provider.

    [`generate`][dpmsynth.generate] creates and repairs one; it is
    [`GenerationResult.data`][dpmsynth.GenerationResult]. It implements the
    ``dpmxl.DataProvider`` protocol, with the optional ``open_keys``, so
    ``dpmxl.evaluate_rule(expression, data)`` evaluates any rule on the
    generated values.

    Attributes:
        template: The template, with the reference date the report uses.
        values: Cell values by ``(datapoint, keys)``, where ``keys`` is a
            tuple of ``(key code, value)`` pairs of an open table's row, and
            ``()`` for a closed table. Numbers are ``dpmxl.Number``,
            enumerated values ``dpmxl.Item``.
        key_rows: Key rows by table code; ``[()]`` for a closed table.
        entity: The LEI of the reporting entity.
        reporting_level: ``CON`` or ``IND``, the suffix of the entity
            identifier and the ``ReportingLevel`` parameter.
        decimals: Reporting decimals by data type code.
    """

    def __init__(
        self,
        template: ModuleTemplate,
        rng: random.Random,
        open_rows: int,
        *,
        entity: str = DEFAULT_ENTITY,
        reporting_level: str = "CON",
    ) -> None:
        """Create initial values and open-table key rows.

        Args:
            template: Module template.
            rng: Random source.
            open_rows: Key rows to generate per open table.
            entity: LEI of the reporting entity.
            reporting_level: Suffix of the entity identifier.
        """
        self.template = template
        self.rng = rng
        self.entity = entity
        self.reporting_level = reporting_level
        self.decimals: dict[str, int] = {**_DEFAULT_DECIMALS, **template.decimals}
        self.values: dict[Slot, Value] = {}
        self.key_rows: dict[str, list[tuple[tuple[str, Any], ...]]] = {}
        self._cells: dict[str, TemplateCell] = {}
        self._query_cells: dict[CellQuery, list[TemplateCell]] = {}
        # Slot -> (lower, upper) from single-cell sign rules such as {x} >= 0.
        self._bounds: dict[Slot, tuple[Decimal | None, Decimal | None]] = {}
        # Item -> the qname the template wrote, for the written report.
        self._item_names: dict[Item, str] = {}
        for table in template.tables:
            for name in [
                *(item for key in table.open_keys for item in key.items or ()),
                *(item for cell in table.cells for item in cell.items or ()),
            ]:
                self._item_names.setdefault(Item.parse(name), name.strip())
        for table in template.tables:
            rows = self._key_rows(table, open_rows) if table.open_keys else [()]
            self.key_rows[table.code] = rows
            for cell in table.cells:
                self._cells.setdefault(cell.datapoint, cell)
                for keys in rows:
                    self.values.setdefault((cell.datapoint, keys), self._initial(cell))

    def _key_rows(
        self, table: TemplateTable, count: int
    ) -> list[tuple[tuple[str, Any], ...]]:
        if not any(not key.items for key in table.open_keys):
            # Only enumerated keys: row i takes item i of each key, so the
            # rows repeat after the least common multiple of the item counts.
            count = min(
                count, math.lcm(*(len(key.items or ()) for key in table.open_keys))
            )
        reference = self.template.reference_date or DEFAULT_REFERENCE_DATE
        rows = []
        for index in range(count):
            row = []
            for key in table.open_keys:
                if key.items:
                    value: Any = Item.parse(key.items[index % len(key.items)])
                else:
                    value = _typed_key(key, index, reference) or _lei(self.rng)
                row.append((key.code, value))
            rows.append(tuple(row))
        return list(dict.fromkeys(rows))

    def _initial(self, cell: TemplateCell) -> Value:
        """Return a random starting value for a cell's data type."""
        kind = cell.data_type
        if kind == "m":
            return self._number(cell, Decimal(self.rng.randint(1, 1000) * 1000))
        if kind == "p":
            return self._number(cell, Decimal(self.rng.randint(1, 99)) / 100)
        if kind == "i":
            return self._number(cell, Decimal(self.rng.randint(1, 50)))
        if kind == "r":
            return self._number(cell, Decimal(self.rng.randint(100, 999)) / 100)
        if kind in _ENUMERATED_TYPES:
            # An enumeration set (es) is written as a set of one item.
            return Item.parse(cell.items[0]) if cell.items else None
        if kind == "b":
            return True
        if kind == "d":
            return self.template.reference_date or DEFAULT_REFERENCE_DATE
        return _lei(self.rng)

    def _cell(self, slot: object) -> TemplateCell | None:
        if not isinstance(slot, tuple) or slot not in self.values:
            return None
        return self._cells.get(slot[0])

    def _numeric_slot(self, slot: object) -> bool:
        # Whether a slot holds a numeric cell that repairs may change.
        cell = self._cell(slot)
        return cell is not None and cell.data_type in _NUMERIC

    def _quantum(self, cell: TemplateCell | None) -> Decimal:
        # The smallest step a cell's value is reported in.
        decimals = self.decimals.get(cell.data_type or "", 2) if cell else 2
        return Decimal(1).scaleb(-decimals)

    def _assign(self, slot: Slot, value: Decimal) -> bool:
        """Set an unrounded numeric value, clamped into the slot's bounds.

        Returns:
            bool: Whether the stored value changed.
        """
        lower, upper = self._bounds.get(slot, (None, None))
        if lower is not None and value < lower:
            value = lower
        if upper is not None and value > upper:
            value = upper
        if abs(value) > _LIMIT:
            return False
        value = value.quantize(_STORED)
        current = self.values.get(slot)
        if isinstance(current, Number) and current.value == value:
            return False
        self.values[slot] = Number(value)
        return True

    def _round_all(self) -> None:
        """Round every numeric value to its reporting decimals."""
        for slot, value in self.values.items():
            cell = self._cells.get(slot[0])
            if isinstance(value, Number) and cell is not None:
                self.values[slot] = self._number(cell, value.value)

    def _within_bounds(self, slot: Slot, value: Decimal) -> bool:
        # Whether a value respects the slot's sign-rule bounds.
        lower, upper = self._bounds.get(slot, (None, None))
        return (lower is None or value >= lower) and (upper is None or value <= upper)

    def _apply_bounds(self) -> None:
        """Move initial values inside their sign-rule bounds.

        A value on the wrong side of zero changes sign, so that a cell that
        must not be positive keeps a magnitude like its neighbours'; a value
        still outside its bounds takes the nearest bound.
        """
        for slot, (lower, upper) in self._bounds.items():
            current = self.values.get(slot)
            if not isinstance(current, Number):
                continue
            value = current.value
            if upper is not None and value > upper:
                value = -abs(value) if upper <= 0 else upper
                value = min(value, upper)
            if lower is not None and value < lower:
                value = abs(value) if lower >= 0 else lower
                value = max(value, lower)
            self.values[slot] = Number(value)

    def _number(self, cell: TemplateCell | None, value: Decimal) -> Number:
        # Round a value to the cell type's reporting decimals.
        try:
            rounded = value.quantize(self._quantum(cell), rounding=ROUND_HALF_UP)
        except InvalidOperation:  # too many digits to round; never written
            rounded = value
        return Number(rounded + 0)  # + 0 turns -0 into 0

    def _text(self, value: object) -> str:
        """Return the lexical form of a value, as written to the package."""
        if isinstance(value, Number):
            number = value.value
            return format(number.copy_abs() if number.is_zero() else number, "f")
        if isinstance(value, Item):
            known = self._item_names.get(value)
            if known is not None:
                return known
            return (
                f"eba_{value.category}:{value.code}" if value.category else value.code
            )
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, date):
            return value.isoformat()
        return str(value)

    # DataProvider -----------------------------------------------------------

    def select(self, query: CellQuery) -> Sequence[DataPoint]:
        """Return the selected cells for every key row of the table.

        Numbers carry their reporting decimals, so rules are judged with the
        same tolerance as the written report.

        Returns:
            Sequence[DataPoint]: Points whose ``ref`` is the
            ``(datapoint, keys)`` slot.

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
        """Whether a table or filing indicator is in the template.

        Every table of the template is reported.

        Returns:
            bool | None: Whether a table code, a filing indicator or a table
            under a template code such as ``C_07.00`` matches, ignoring case.
        """
        folded = table.casefold()
        return any(
            item.code.casefold() == folded
            or item.filing_indicator.casefold() == folded
            or item.code.casefold().startswith(f"{folded}.")
            for item in self.template.tables
        )

    def parameter(self, name: str) -> Value:
        """Return a report parameter.

        Returns:
            Value: ``refPeriod`` (the reference date) or ``ReportingLevel``
            (``con`` or ``ind``); otherwise ``None``.
        """
        folded = name.casefold()
        if folded == "refperiod":
            return self.template.reference_date or DEFAULT_REFERENCE_DATE
        if folded == "reportinglevel":
            return self.reporting_level.casefold()
        return None

    def open_keys(self, table: str) -> tuple[str, ...]:
        """Return the open key codes of a table.

        Returns:
            tuple[str, ...]: Key codes; empty for a closed or unknown table.
        """
        found = self.template.table(table)
        return tuple(key.code for key in found.open_keys) if found else ()


_FIRST_KEY_DATE = date(1900, 1, 1)


def _typed_key(key: OpenKey, number: int, reference: date) -> Value:
    """Return the value of row ``number`` of an integer or date typed key.

    Integers count from 1; dates count back from the reference date, day by
    day, and start again at it after 1900-01-01.

    Returns:
        Value: A number or a date; ``None`` for a key of any other type.
    """
    if key.data_type == "i":
        return Number(Decimal(number + 1))
    if key.data_type == "d":
        return reference - timedelta(days=number % _key_dates(reference))
    return None


def _key_dates(reference: date) -> int:
    """Return how many distinct dates a date typed key takes."""
    return max((reference - _FIRST_KEY_DATE).days + 1, 1)


def _selected(code: str | None, selector: Any) -> bool:
    if selector is None or selector.wildcard:
        return True
    if code in (None, "*"):
        return False
    return axis_matches(code, selector)


_LEI_ALPHABET = string.ascii_uppercase + string.digits

LEI_PREFIX = "SYNTH"
"""The prefix of every LEI-shaped identifier dpm-synth generates.

Generated identifiers are ``SYNTH`` followed by 13 letters and digits and
two ISO 17442 check digits, so they pass LEI validation but are visibly
fictional and cannot coincide with an entity's real LEI by chance.
"""


def _lei(rng: random.Random) -> str:
    """Return a random, checksum-valid, visibly fictional LEI-shaped identifier.

    ``SYNTH``, thirteen random upper-case letters and digits, and the two
    ISO 17442 check digits, so validators that check LEIs accept it while
    the prefix marks it as synthetic.

    Returns:
        str: The identifier.
    """
    body = "".join(rng.choice(_LEI_ALPHABET) for _ in range(18 - len(LEI_PREFIX)))
    return _with_check_digits(LEI_PREFIX + body)


def _with_check_digits(base: str) -> str:
    """Append the ISO 17442 (ISO 7064 MOD 97-10) check digits to 18 characters.

    Returns:
        str: The 20-character identifier.
    """
    number = int("".join(str(int(character, 36)) for character in base + "00"))
    return f"{base}{98 - number % 97:02d}"


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
        node = _unwrap(node)
        while isinstance(node, Unary) and node.op == "not":
            node, desired = _unwrap(node.operand), not desired
        current = self.value(node)
        if current is desired:
            return False
        match node:
            case Binary(op="and" | "or" as op):
                # Chains such as a and b and c are flattened, so a long chain
                # does not recurse once per operand.
                operands = _operands(node, op)
                if (op == "and") == desired:  # every operand must change
                    changed = False
                    for operand in operands:
                        changed = self.fix(operand, desired) or changed
                    return changed
                # One operand suffices: the first that can be changed.
                return any(self.fix(operand, desired) for operand in operands)
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
                return any(
                    self.assign_all(operand, member) for member in self.members(values)
                )
            case Call(name="isnull", args=(operand,)):
                if desired:
                    return self.assign_all(operand, None)
                return self.fill(operand)
            case Call(name="match", args=(operand, pattern)) if desired:
                text = _matching_text(_literal(pattern), self.data)
                return text is not None and self.assign_all(operand, text)
        return False

    def members(self, node: Node) -> list[Value]:
        """Return the members of the set on the right of ``in``, in order.

        A set literal ``{a, b}`` gives its items; any other operand (a
        ``set-*`` parameter, ``union(...)``, a selection of cells) gives the
        members of the set it evaluated to, or the values it selected.

        Returns:
            list[Value]: Candidate values, without nulls.
        """
        if isinstance(node, SetLiteral):
            values = []
            for item in node.items:
                value = _literal(item)
                if value is None:
                    records = self.evaluation.value_at(
                        item, self.key
                    ) or self.evaluation.value_at(item, {})
                    value = records[0].value if records else None
                values.append(value)
        else:
            records = self.evaluation.value_at(node, self.key)
            if not records:
                recordset = self.evaluation.trace.get(id(node))
                records = list(recordset.records.values()) if recordset else []
            values = []
            for record in records:
                if isinstance(record.value, ValueSet):
                    values.extend(record.value.members)
                else:
                    values.append(record.value)
        return [value for value in values if value is not None]

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
                cell = self.data._cell(slot)
                if cell is not None:
                    changed = self.put(slot, self.data._initial(cell)) or changed
        return changed

    def put(self, slot: object, value: Value) -> bool:
        cell = self.data._cell(slot)
        if cell is None:
            return False
        slot = cast(Slot, slot)
        if value is not None and (cell.data_type in _NUMERIC) != isinstance(
            value, Number
        ):
            # Numbers go in numeric cells only, and nothing else does.
            return False
        if isinstance(value, Number):
            if abs(value.value) > _LIMIT:
                return False
            value = self.data._number(cell, value.value)
            if not self.data._within_bounds(slot, value.value):
                return False
        if self.data.values.get(slot) == value:
            return False
        self.data.values[slot] = value
        return True

    def comparison(self, node: Binary, op: str) -> bool:
        left, right = self.value(node.left), self.value(node.right)
        numeric = isinstance(left, Number | None) and isinstance(right, Number | None)
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
        that merely use it. A strict inequality is met by one reporting step
        of the chosen cell.

        Returns:
            bool: Whether a value changed.
        """
        difference = _value(self.value(node.left)) - _value(self.value(node.right))
        terms = self.terms(node.left, Decimal(1)) + self.terms(node.right, Decimal(-1))
        owners = self.owners

        def rank(item: tuple[int, tuple[Any, Decimal, Decimal]]) -> tuple[int, int]:
            index, (slot, _coefficient, _seen) = item
            others = owners.get(slot, set()) - {self.rule}
            return (1 if others else 0, index)

        for _index, (slot, coefficient, seen) in sorted(enumerate(terms), key=rank):
            if not coefficient or not self.data._numeric_slot(slot):
                continue
            step = self.data._quantum(self.data._cell(slot)) * abs(coefficient)
            goal = _goal(op, step)
            # The difference is the one the evaluation saw, so the cell moves
            # from the value the evaluation saw too: an earlier repair of the
            # same record (a and b on one cell) is not added twice.
            base = seen
            try:
                value = base + (goal - difference) / coefficient
            except ArithmeticError:
                continue
            if self.data._within_bounds(slot, value) and self.data._assign(slot, value):
                return True
        return False

    def terms(
        self, node: Node, coefficient: Decimal
    ) -> list[tuple[Any, Decimal, Decimal]]:
        """Expand an arithmetic node into ``(slot, coefficient, value)`` terms.

        The value is the cell's value as the evaluation saw it. Sums and
        differences are expanded with a stack, so a long chain such as
        ``a + b + ... + z`` does not recurse once per term.

        Returns:
            list[tuple[Any, Decimal, Decimal]]: Cells whose change moves the
            node linearly.
        """
        found: list[tuple[Any, Decimal, Decimal]] = []
        stack = [(node, coefficient)]
        while stack:
            node, coefficient = stack.pop()
            node = _unwrap(node)
            match node:
                case Binary(op="+" | "-" as op, left=left, right=right):
                    stack.append((right, coefficient if op == "+" else -coefficient))
                    stack.append((left, coefficient))
                case Unary(op="-", operand=operand):
                    stack.append((operand, -coefficient))
                case Unary(op="+", operand=operand):
                    stack.append((operand, coefficient))
                case Binary(op="*", left=left, right=right):
                    stack.append((right, coefficient * _value(self.value(left))))
                    stack.append((left, coefficient * _value(self.value(right))))
                case Binary(op="/", left=left, right=right):
                    divisor = _value(self.value(right))
                    if divisor:
                        stack.append((left, coefficient / divisor))
                case Call(name="sum") | Selection() | Where() | Sub():
                    found.extend(
                        (point.ref, coefficient, _value(point.value))
                        for point in reversed(self.points(node))
                        if isinstance(point.ref, tuple)
                    )
                case Call(name="abs", args=(operand,)):
                    negative = _value(self.value(operand)) < 0
                    stack.append((operand, -coefficient if negative else coefficient))
        return found


def _operands(node: Node, op: str) -> list[Node]:
    """Return the operands of a chain of ``op``, such as ``a and b and c``."""
    operands = []
    stack = [node]
    while stack:
        current = _unwrap(stack.pop())
        if isinstance(current, Binary) and current.op == op:
            stack.extend((current.right, current.left))
        else:
            operands.append(current)
    return operands


def _unwrap(node: Node) -> Node:
    while isinstance(node, With):
        node = node.body
    return node


def _value(value: Value | None) -> Decimal:
    return value.value if isinstance(value, Number) else Decimal(0)


def _goal(op: str, step: Decimal) -> Decimal:
    """Return the ``left - right`` difference that satisfies ``op``.

    Returns:
        Decimal: Zero, or one step to the required side of it.
    """
    if op in {">", "!="}:
        return step
    if op == "<":
        return -step
    return Decimal(0)


def _literal(node: Node) -> Value:
    if isinstance(node, Literal_):
        if node.kind == "number" and isinstance(node.value, Decimal):
            return Number(node.value)
        return cast(Value, node.value)
    return None


_LEI_PATTERN = re.compile(r"\[A-Z0-9\]\{18\}\[0-9\]\{2\}")
_DATE_PATTERN = re.compile(
    r"\^?\[0-9\]\{2\}\[/\]\{1\}\[0-9\]\{2\}\[/\]\{1\}\[0-9\]\{4\}\$?"
)


def _matching_text(pattern: Value, data: SyntheticData) -> str | None:
    """Return text matching one of the two regular expressions EBA rules use."""
    if not isinstance(pattern, str):
        return None
    if _LEI_PATTERN.search(pattern):
        return _lei(data.rng)
    if _DATE_PATTERN.fullmatch(pattern):
        reference = data.template.reference_date or DEFAULT_REFERENCE_DATE
        return reference.strftime("%d/%m/%Y")
    return None


# Driver ---------------------------------------------------------------------


def generate(
    template: ModuleTemplate,
    *,
    seed: int = 0,
    open_rows: int = 2,
    max_rounds: int = 40,
    entity: str = DEFAULT_ENTITY,
    reporting_level: str = "CON",
    reference_date: date | None = None,
) -> GenerationResult:
    """Generate a report for ``template`` that satisfies as many rules as it can.

    Args:
        template: Module template, from [`load_template`][dpmsynth.load_template].
        seed: Random seed; the same seed, template, options and versions give
            the same report.
        open_rows: Key rows per open table, from 1 to ``MAX_OPEN_ROWS``
            (1,000). Enumerated keys take
            their allowed items in order, so a table whose keys allow fewer
            combinations gets fewer rows.
        max_rounds: Upper bound on evaluate-and-repair rounds; 0 evaluates the
            initial values only.
        entity: LEI of the reporting entity.
        reporting_level: Suffix of the entity identifier, such as ``CON`` or
            ``IND``; also the ``ReportingLevel`` parameter, in lower case.
        reference_date: Overrides the template's reference date.

    Returns:
        GenerationResult: The report and the final rule status.

    Raises:
        ValueError: If ``open_rows`` or ``max_rounds`` is out of range, or
            ``entity`` or ``reporting_level`` is not an identifier.

    Examples:
        >>> from dpmsynth import load_template
        >>> result = generate(load_template("minimal.json"), seed=7)
        >>> result.passed, result.failed
        (2, [])
        >>> result.report.entity_id
        'SYNTHETICDPMXL000002.CON'
    """
    if (
        isinstance(open_rows, bool)
        or not isinstance(open_rows, int)
        or not 1 <= open_rows <= MAX_OPEN_ROWS
    ):
        raise ValueError(
            f"open_rows must be a whole number from 1 to {MAX_OPEN_ROWS}: {open_rows!r}"
        )
    if (
        isinstance(max_rounds, bool)
        or not isinstance(max_rounds, int)
        or max_rounds < 0
    ):
        raise ValueError(
            f"max_rounds must be a whole number of 0 or more: {max_rounds!r}"
        )
    for name, value in (("entity", entity), ("reporting_level", reporting_level)):
        if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
            raise ValueError(
                f"{name} must be letters and digits, optionally with '.', '_' "
                f"and '-': {value!r}"
            )
    if reference_date is not None:
        template = replace(template, reference_date=reference_date)
    rng = random.Random(seed)  # ruff: ignore[suspicious-non-cryptographic-random-usage] - reproducible test data, not secrets
    data = SyntheticData(
        template, rng, open_rows, entity=entity, reporting_level=reporting_level
    )
    parsed = []
    not_evaluated: dict[str, str] = {}
    for rule in template.rules:
        try:
            parsed.append((rule, parse(rule.expression), rule.precondition))
        except DpmXlSyntaxError as error:
            not_evaluated[rule.code] = f"syntax error: {error}"
        except RecursionError:
            not_evaluated[rule.code] = "expression too deeply nested"
    owners = _definitions(parsed, data)
    data._apply_bounds()
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
                try:
                    if repairer.fix(result.evaluation.root, True):
                        changed += 1
                except RecursionError:
                    # Too deeply nested to follow (dpm-xl evaluated it); the
                    # rule keeps its status but is not repaired.
                    break
        history.append(failing)
        repairs += changed
        if not failing or not changed or _stalled(history):
            break
    data._round_all()
    passed = 0
    failed: list[str] = []
    not_applicable: list[str] = []
    for rule, node, precondition in parsed:
        result = evaluate_rule(node, data, precondition=precondition, trace=False)
        if result.status == "passed":
            passed += 1
        elif result.status == "failed":
            failed.append(rule.code)
        elif result.status == "not_applicable":
            not_applicable.append(rule.code)
        else:
            not_evaluated[rule.code] = result.message or result.status
    return GenerationResult(
        report=build_report(data),
        data=data,
        rules=len(template.rules),
        passed=passed,
        failed=failed,
        not_evaluated={
            rule.code: not_evaluated[rule.code]
            for rule in template.rules
            if rule.code in not_evaluated
        },
        not_applicable=not_applicable,
        rounds=rounds,
        repairs=repairs,
        history=history,
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
    cell, preferring the left side. Records sign-rule bounds on the way and
    orders ``parsed`` so definitions of components come first.

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
        try:
            # A sign rule may be one part of an and: {x} = ... and {x} >= 0.
            for part in _operands(node, "and"):
                _record_bounds(part, evaluation, data)
            comparisons = walk(node)
        except RecursionError:
            continue
        for comparison in comparisons:
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
    """Record ``{cells} op constant`` sign rules as per-cell bounds.

    A strict inequality bounds the cell one reporting step past the constant.
    """
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
            slot = cast(Slot, point.ref)
            step = data._quantum(data._cell(slot)) if op in {">", "<"} else 0
            lower, upper = data._bounds.get(slot, (None, None))
            if op in {">=", ">"}:
                bound = constant.value + step
                lower = bound if lower is None else max(lower, bound)
            else:
                bound = constant.value - step
                upper = bound if upper is None else min(upper, bound)
            data._bounds[slot] = (lower, upper)


def build_report(data: SyntheticData) -> Report:
    """Turn generated values into a report that dpm-xbrl can write.

    Facts follow the EBA xBRL-CSV convention: a ``datapoint`` and
    ``factValue`` per cell, with the open keys of the row. The entity is
    ``<entity>.<reporting level>`` in the reporting-subject scheme, every
    table's filing indicator is reported, and a ``decimals*`` parameter is
    set for each numeric data type the template uses.
    [`generate`][dpmsynth.generate] calls it; call it yourself after changing
    ``data.values``.

    Args:
        data: Generated values, ``GenerationResult.data``.

    Returns:
        Report: The report, for ``dpmxbrl.write_xbrl_csv``.

    Examples:
        >>> from dpmsynth import generate, load_template
        >>> data = generate(load_template("minimal.json"), seed=7).data
        >>> report = build_report(data)
        >>> [fact.datapoint for fact in report.facts]
        ['dp1001', 'dp1002', 'dp1003']
    """
    template = data.template
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
                        data._text(value),
                        datapoint=cell.datapoint,
                        template=table.code.lower(),
                        keys={
                            _column(table, name): data._text(key) for name, key in keys
                        },
                    )
                )
    used_types = {cell.data_type for table in template.tables for cell in table.cells}
    return Report(
        format="xbrl-csv",
        entry_point=template.entry_point,
        # A subject with a suffix uses the reporting-subject scheme (EBA
        # filing rule 3.6).
        entity_scheme=_RSCHEME,
        entity_id=f"{data.entity}.{data.reporting_level}",
        reference_date=template.reference_date or DEFAULT_REFERENCE_DATE,
        base_currency="iso4217:EUR",
        parameters={},
        decimals_parameters={
            parameter: data.decimals[kind]
            for kind, parameter in _DECIMALS_PARAMETERS.items()
            if kind in used_types
        },
        filing_indicators=dict.fromkeys(
            dict.fromkeys(table.filing_indicator for table in template.tables), True
        ),
        facts=tuple(facts),
        namespaces={
            "rs": _RSCHEME,
            "iso4217": "http://www.xbrl.org/2003/iso4217",
        },
    )


def _column(table: TemplateTable, code: str) -> str:
    return next((key.column for key in table.open_keys if key.code == code), code)


__all__ = [
    "DEFAULT_ENTITY",
    "DEFAULT_REFERENCE_DATE",
    "LEI_PREFIX",
    "MAX_OPEN_ROWS",
    "GenerationResult",
    "SyntheticData",
    "build_report",
    "generate",
]
