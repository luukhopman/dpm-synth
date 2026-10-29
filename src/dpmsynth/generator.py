"""Generate a report that satisfies a module's DPM-XL rules.

The generator solves the linear rules jointly and then runs an
evaluate-and-repair loop; it is not a complete constraint solver:

1. Every cell gets a plausible value for its data type, and every open table
   gets a few key rows.
2. Single-cell sign rules become per-cell bounds, every ``=`` rule with a
   single-cell side defines that cell, and every comparison of sums of
   cells times constants (``abs`` included) becomes a linear constraint.
3. The linear constraints are solved together: Gaussian elimination for the
   equalities, then projections for the inequalities and bounds.
4. All rules are evaluated with dpm-xl. For each failing record the first
   failing comparison is found through the evaluation trace and one cell is
   changed so the comparison holds. ``isnull``, ``in`` and ``match`` failures
   are repaired by clearing, choosing a member, or writing a matching
   identifier.
5. Step 4 repeats until no rule fails, a round changes nothing, or the
   failing count stops improving; if rules still fail, steps 3 and 4 run
   once more. Values are then rounded to the reporting decimals and every
   rule is evaluated once more.

How the loop works, and where it stops, is explained at
https://luukhopman.github.io/dpm-synth/concepts/repair-loop/.
"""

from __future__ import annotations

import math
import random
import re
import string
from collections import deque
from collections.abc import Hashable, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
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
_CURRENCY = re.compile(r"[A-Z]{3}")
_RSCHEME = "https://eurofiling.info/eu/rs"
_LEI_SCHEME = "http://standards.iso.org/iso/17442"
# Reporting subjects carry a suffix from this reference date, except in
# modules whose code has _con or _ind (EBA filing rule 3.6).
_SUFFIX_FROM = date(2022, 12, 31)
_LEVEL_MODULE = re.compile(r"_(con|ind)(_|$)", re.IGNORECASE)

Slot = tuple[str, tuple[tuple[str, Any], ...]]


STATUSES = ("passed", "failed", "not_applicable", "error", "unsupported", "skipped")
"""The statuses a rule can end with, in the order summaries list them.

The first five are dpm-xl's: ``not_applicable`` when the precondition is
false or the rule selects no cell, ``error`` when the rule cannot be
evaluated, such as a selection of a table the template does not have, and
``unsupported`` for a construct dpm-xl does not evaluate on one report, such
as ``time_shift``. ``skipped`` is an inactive rule, which is not evaluated.
"""


@dataclass(frozen=True)
class GenerationResult:
    """The generated report and how far the repair loop got.

    Attributes:
        report: The report, ready for ``dpmxbrl.write_xbrl_csv``.
        data: The generated values, a dpm-xl data provider; pass it to
            [`write_scaled_package`][dpmsynth.write_scaled_package] or
            evaluate rules on it.
        statuses: The status of every rule on the final, rounded values, by
            rule code, in template order: one of
            [`STATUSES`][dpmsynth.STATUSES].
        messages: Why a rule is ``error`` or ``unsupported``, by rule code,
            in template order.
        rounds: Evaluate-and-repair rounds run.
        repairs: Failing records repaired over all rounds.
        history: Failing rules at the start of each round.
    """

    report: Report
    data: SyntheticData
    statuses: dict[str, str]
    messages: dict[str, str] = field(default_factory=dict)
    rounds: int = 0
    repairs: int = 0
    history: list[int] = field(default_factory=list)

    @property
    def failed(self) -> list[str]:
        """Codes of the rules that still fail, in template order.

        Returns:
            list[str]: Rule codes; empty when every evaluated rule passes.
        """
        return [code for code, status in self.statuses.items() if status == "failed"]

    @property
    def summary(self) -> dict[str, int]:
        """Count the rules by status.

        Returns:
            dict[str, int]: ``rules``, the number of rules, then a count for
            each of [`STATUSES`][dpmsynth.STATUSES]; the counts add up to
            ``rules``.

        Examples:
            >>> from dpmsynth import load_template
            >>> summary = generate(load_template("minimal.json"), seed=7).summary
            >>> summary["rules"], summary["passed"], summary["failed"]
            (2, 2, 0)
        """
        counts = dict.fromkeys(STATUSES, 0)
        for status in self.statuses.values():
            counts[status] += 1
        return {"rules": len(self.statuses), **counts}


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
            rounded = value.quantize(self._quantum(cell), rounding=ROUND_HALF_EVEN)
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
        if isinstance(left, date) and isinstance(right, date):
            return self.dates(node, op, left, right)
        numeric = isinstance(left, Number | None) and isinstance(right, Number | None)
        if numeric and (left is not None or right is not None):
            return self.linear(node, op)
        if op == "=" and right is not None:
            return self.assign_all(node.left, right)
        if op == "=" and left is not None:
            return self.assign_all(node.right, left)
        return False

    def dates(self, node: Binary, op: str, left: date, right: date) -> bool:
        """Repair a comparison of two dates by moving one side.

        The earlier side moves, so dates do not move past the reference
        date: ``a < b`` sets ``a`` to the day before ``b``; ``a > b`` sets
        ``b`` to the day before ``a``; ``a = b`` copies ``b`` into ``a``.

        Returns:
            bool: Whether a value changed.
        """
        day = timedelta(days=1)
        if op in {"<", "<=", "!="}:
            return self.assign_all(node.left, right if op == "<=" else right - day)
        if op in {">", ">="}:
            return self.assign_all(node.right, left if op == ">=" else left - day)
        return self.assign_all(node.left, right)

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

        ordered = [
            (slot, coefficient, seen)
            for _index, (slot, coefficient, seen) in sorted(enumerate(terms), key=rank)
            if coefficient and self.data._numeric_slot(slot)
        ]
        for slot, coefficient, seen in ordered:
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
        return self.spread(ordered, difference, op)

    def spread(
        self, terms: list[tuple[Any, Decimal, Decimal]], difference: Decimal, op: str
    ) -> bool:
        """Share a difference that no single cell can absorb within its bounds.

        Cells move in turn, each as far as its bounds allow, until the
        comparison holds: ``a = b + c`` with every cell between 0 and 1 is
        met by lowering ``b`` and ``c`` once ``a`` is at 1.

        Returns:
            bool: Whether a value changed; the comparison may still fail.
        """
        if not terms:
            return False
        step = max(
            self.data._quantum(self.data._cell(slot)) * abs(coefficient)
            for slot, coefficient, _seen in terms
        )
        remaining = _goal(op, step) - difference
        changed = False
        for slot, coefficient, seen in terms:
            if not remaining:
                break
            lower, upper = self.data._bounds.get(slot, (None, None))
            value = seen + remaining / coefficient
            if lower is not None:
                value = max(value, lower)
            if upper is not None:
                value = min(value, upper)
            if value != seen and self.data._assign(slot, value):
                changed = True
                remaining -= coefficient * (value - seen)
        return changed

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
    currency: str | None = None,
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
            initial values only, without the joint solve of linear rules.
        entity: LEI of the reporting entity.
        reporting_level: Suffix of the entity identifier, such as ``CON`` or
            ``IND``, from the reference date 2022-12-31 and for a module
            without ``_con`` or ``_ind`` in its code; also the
            ``ReportingLevel`` parameter, in lower case.
        reference_date: Overrides the template's reference date.
        currency: Overrides the template's reporting currency, an ISO 4217
            code such as ``SEK``.

    Returns:
        GenerationResult: The report and the final rule status.

    Raises:
        ValueError: If ``open_rows`` or ``max_rounds`` is out of range,
            ``entity`` or ``reporting_level`` is not an identifier, or
            ``currency`` is not an ISO 4217 code.

    Examples:
        >>> from dpmsynth import load_template
        >>> result = generate(load_template("minimal.json"), seed=7)
        >>> result.summary["passed"], result.failed
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
    if currency is not None:
        if not isinstance(currency, str) or not _CURRENCY.fullmatch(currency):
            raise ValueError(
                f"currency must be an ISO 4217 code such as 'EUR': {currency!r}"
            )
        template = replace(template, currency=currency)
    if reference_date is not None:
        template = replace(template, reference_date=reference_date)
    rng = random.Random(seed)  # ruff: ignore[suspicious-non-cryptographic-random-usage] - reproducible test data, not secrets
    data = SyntheticData(
        template, rng, open_rows, entity=entity, reporting_level=reporting_level
    )
    parsed = []
    messages: dict[str, str] = {}
    for rule in template.rules:
        if not rule.active:
            continue
        try:
            parsed.append((rule, parse(rule.expression), rule.precondition))
        except DpmXlSyntaxError as error:
            messages[rule.code] = f"syntax error: {error}"
        except RecursionError:
            messages[rule.code] = "expression too deeply nested"
    constraints: list[_Constraint] = []
    owners = _definitions(parsed, data, constraints)
    data._apply_bounds()
    history: list[int] = []
    repairs = 0
    # The linear rules are solved jointly, then the loop repairs the rest;
    # when rules still fail, a second solve restores the linear rules its
    # repairs broke, and the loop runs again.
    for _phase in range(2):
        if len(history) >= max_rounds:
            break
        _project(constraints, data)
        # The loop repairs what rounding to the reporting decimals breaks.
        data._round_all()
        start = len(history)
        changes, failing = _repair(parsed, data, owners, max_rounds - start, history)
        repairs += changes
        if not failing:
            break
    rounds = len(history)
    data._round_all()
    found: dict[str, str] = dict.fromkeys(messages, "error")
    found.update((rule.code, "skipped") for rule in template.rules if not rule.active)
    for rule, node, precondition in parsed:
        result = evaluate_rule(node, data, precondition=precondition, trace=False)
        found[rule.code] = result.status
        if result.status in {"error", "unsupported"}:
            messages[rule.code] = result.message or result.status
    return GenerationResult(
        report=build_report(data),
        data=data,
        statuses={rule.code: found[rule.code] for rule in template.rules},
        messages={
            rule.code: messages[rule.code]
            for rule in template.rules
            if rule.code in messages
        },
        rounds=rounds,
        repairs=repairs,
        history=history,
    )


def _repair(
    parsed: list[tuple[Any, Node, str | None]],
    data: SyntheticData,
    owners: dict[Any, set[str]],
    rounds: int,
    history: list[int],
) -> tuple[int, int]:
    """Run up to ``rounds`` evaluate-and-repair rounds.

    Appends the failing rules at the start of each round to ``history``.

    Returns:
        tuple[int, int]: The records repaired, and the rules failing in the
        last round.
    """
    repairs, failing, start = 0, 0, len(history)
    for _round in range(rounds):
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
        if not failing or not changed or _stalled(history[start:]):
            break
    return repairs, failing


def _stalled(history: list[int], window: int = 6) -> bool:
    """Whether the failing-rule count stopped improving (an oscillation).

    Returns:
        bool: ``True`` when the last ``window`` rounds found no new minimum.
    """
    if len(history) <= window:
        return False
    return min(history[-window:]) >= min(history[:-window])


def _definitions(
    parsed: list[tuple[Any, Node, str | None]],
    data: SyntheticData,
    constraints: list[_Constraint] | None = None,
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
                if constraints is not None:
                    constraints.extend(_linear_constraints(part, evaluation, data))
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


# A linear comparison ``constant + sum(coefficient * cell) op 0`` of one record.
_Constraint = tuple[str, float, tuple[tuple[Slot, float], ...]]
_LINEAR_OPS = {"=", "<", "<=", ">", ">="}


def _constant(node: Node) -> bool:
    """Whether a node selects no cell, so its value does not change.

    Returns:
        bool: ``True`` for a node without selections.
    """
    return not any(isinstance(item, Selection | Where | Sub) for item in walk(node))


def _is_linear(node: Node) -> bool:
    """Whether a node is a sum of cells times constants, plus a constant.

    ``abs`` counts too: with its operand's sign kept, it is linear.

    Returns:
        bool: Whether the node's value is linear in its cells.
    """
    stack = [node]
    while stack:
        node = _unwrap(stack.pop())
        match node:
            case Binary(op="+" | "-", left=left, right=right):
                stack.extend((left, right))
            case Binary(op="*", left=left, right=right):
                if not _constant(left) and not _constant(right):
                    return False
                stack.extend((left, right))
            case Binary(op="/", left=left, right=right):
                if not _constant(right):
                    return False
                stack.append(left)
            case (
                Unary(op="+" | "-", operand=operand) | Call(name="abs", args=(operand,))
            ):
                stack.append(operand)
            case Call(name="sum", args=args):
                stack.extend(args)
            case Selection() | Where() | Sub() | Literal_():
                pass
            case _:
                return False
    return True


def _linear_constraints(
    node: Node, evaluation: Evaluation, data: SyntheticData
) -> list[_Constraint]:
    """Return the linear comparison of every record of a rule's part.

    Only a comparison whose sides are sums of cells times constants counts,
    so its coefficients do not depend on the values. An ``abs`` is the
    operand or its negation, by the operand's sign, which a further
    constraint keeps.

    Returns:
        list[_Constraint]: The constraints of every record; empty for
        anything else.
    """
    node = _unwrap(node)
    if not (
        isinstance(node, Binary)
        and node.op in _LINEAR_OPS
        and _is_linear(node.left)
        and _is_linear(node.right)
    ):
        return []
    recordset = evaluation.trace.get(id(node))
    if recordset is None:
        return []
    signs = [
        item for item in walk(node) if isinstance(item, Call) and item.name == "abs"
    ]
    found = []
    for key in recordset.records:
        repairer = _Repairer(
            data, evaluation, dict(zip(recordset.keys, key, strict=True))
        )
        left, right = repairer.value(node.left), repairer.value(node.right)
        if not (isinstance(left, Number | None) and isinstance(right, Number | None)):
            continue
        found.append(_linear(repairer, node.op, node.left, node.right))
        for call in signs:
            operand = call.args[0]
            negative = _value(repairer.value(operand)) < 0
            found.append(_linear(repairer, "<=" if negative else ">=", operand, None))
    return [constraint for constraint in found if constraint[2]]


def _linear(
    repairer: _Repairer, op: str, left: Node, right: Node | None
) -> _Constraint:
    """Return ``left - right op 0`` of one record as a linear constraint.

    Returns:
        _Constraint: The comparison, its constant and its numeric cells.
    """
    terms = repairer.terms(left, Decimal(1))
    constant = _value(repairer.value(left))
    if right is not None:
        terms += repairer.terms(right, Decimal(-1))
        constant -= _value(repairer.value(right))
    coefficients: dict[Slot, Decimal] = {}
    for slot, coefficient, seen in terms:
        if repairer.data._numeric_slot(slot):
            constant -= coefficient * seen
            coefficients[slot] = coefficients.get(slot, Decimal(0)) + coefficient
    return (
        op,
        float(constant),
        tuple(
            (slot, float(coefficient))
            for slot, coefficient in coefficients.items()
            if coefficient
        ),
    )


# A linear expression: a constant and coefficients by cell.
_Expression = tuple[float, dict[Slot, float]]


def _project(
    constraints: list[_Constraint],
    data: SyntheticData,
    passes: int = 40,
    relaxation: float = 1.5,
) -> None:
    """Move the numeric values onto every linear constraint at once.

    The repair loop changes one cell at a time, so a cell defined by two
    rules, such as a total of both its row and its column, moves back and
    forth between them. This solves the linear rules jointly first:

    1. A constraint on one cell is a bound of that cell.
    2. Gaussian elimination expresses one cell of each equality (its pivot)
       in the other cells, so every equality holds whatever they are.
    3. The inequalities and the bounds of the pivots, rewritten in the other
       cells, are met by projections (Kaczmarz's method, over-relaxed, with
       a work list), each changing the cells of one constraint as little as
       possible and keeping every cell inside its bounds.
    4. The pivots are computed from the other cells.

    Contradictory equalities are left to the repair loop, and the projections
    stop after ``passes`` times the number of inequalities.
    """
    limits: dict[Slot, list[float]] = {}

    def limit(slot: Slot) -> list[float]:
        found = limits.get(slot)
        if found is None:
            lower, upper = data._bounds.get(slot, (None, None))
            found = limits[slot] = [
                -math.inf if lower is None else float(lower),
                math.inf if upper is None else float(upper),
            ]
        return found

    equalities: list[tuple[float, tuple[tuple[Slot, float], ...]]] = []
    # Inequalities as constant + terms >= 0.
    inequalities: list[tuple[float, tuple[tuple[Slot, float], ...]]] = []
    for op, constant, terms in constraints:
        if len(terms) == 1:
            ((slot, coefficient),) = terms
            value = -constant / coefficient
            if op != "=" and coefficient < 0:
                op = _MIRRORED[op]
            bounds = limit(slot)
            if op in {"=", ">=", ">"}:
                bounds[0] = max(bounds[0], value)
            if op in {"=", "<=", "<"}:
                bounds[1] = min(bounds[1], value)
        elif op == "=":
            equalities.append((constant, terms))
        elif op in {">=", ">"}:
            inequalities.append((constant - (op == ">"), terms))
        else:
            negated = tuple((slot, -c) for slot, c in terms)
            inequalities.append((-constant - (op == "<"), negated))
    # A cleared cell (an isnull repair) stays cleared: it counts as 0.
    for _op, _constant, terms in constraints:
        for slot, _c in terms:
            if data.values.get(slot) is None:
                limit(slot)[:] = [0.0, 0.0]
    pivots = _eliminate(equalities)
    for slot, bounds in limits.items():
        if slot in pivots:
            if bounds[0] > -math.inf:
                inequalities.append((-bounds[0], ((slot, 1.0),)))
            if bounds[1] < math.inf:
                inequalities.append((bounds[1], ((slot, -1.0),)))
    rows = []
    for constant, terms in inequalities:
        expression = _substitute(constant, terms, pivots)
        if expression[1]:
            rows.append((expression[0], tuple(expression[1].items())))
    values: dict[Slot, float] = {}

    def start(slot: Slot) -> None:
        if slot not in values:
            value = float(_value(data.values.get(slot)))
            bounds = limits.get(slot)
            if bounds is not None and bounds[0] <= bounds[1] and slot not in pivots:
                value = min(max(value, bounds[0]), bounds[1])
            values[slot] = value

    for _constant, terms in rows:
        for slot, _c in terms:
            start(slot)
    for _constant, expression in pivots.values():
        for slot in expression:
            start(slot)
    for slot in [*limits, *pivots]:
        start(slot)
    original = {slot: float(_value(data.values.get(slot))) for slot in values}
    _feasible(
        rows,
        values,
        {s: b for s, b in limits.items() if s not in pivots},
        passes,
        relaxation,
    )
    for slot, (constant, expression) in pivots.items():
        values[slot] = constant + sum(values[s] * c for s, c in expression.items())
    for slot, value in values.items():
        if (
            value != original[slot]
            and math.isfinite(value)
            and data.values.get(slot) is not None
        ):
            data._assign(slot, Decimal(repr(value)))


def _eliminate(
    equalities: list[tuple[float, tuple[tuple[Slot, float], ...]]],
) -> dict[Slot, _Expression]:
    """Solve equalities for one cell each, by Gauss-Jordan elimination.

    Each equality, with the earlier pivots substituted, takes as its pivot
    the cell that the fewest earlier pivots use, so the expressions stay
    short; a pivot is then substituted into the expressions that use it.

    Returns:
        dict[Slot, _Expression]: Each pivot as an expression in cells that
        are not pivots. An equality that is redundant, or contradicts the
        earlier ones, gets none.
    """
    pivots: dict[Slot, _Expression] = {}
    # Cell -> the pivots whose expression uses it, as an ordered set.
    users: dict[Slot, dict[Slot, None]] = {}
    for constant, terms in equalities:
        constant, row = _substitute(constant, terms, pivots)
        if not row:
            continue
        pivot = min(row, key=lambda slot: (len(users.get(slot, ())), -abs(row[slot])))
        scale = -row.pop(pivot)
        solved = (constant / scale, {slot: c / scale for slot, c in row.items()})
        for user in users.pop(pivot, {}):
            used_constant, used = pivots[user]
            factor = used.pop(pivot)
            for slot, c in solved[1].items():
                value = used.get(slot, 0.0) + factor * c
                if abs(value) > 1e-12:
                    used[slot] = value
                    users.setdefault(slot, {})[user] = None
                elif slot in used:
                    del used[slot]
                    users[slot].pop(user, None)
            pivots[user] = (used_constant + factor * solved[0], used)
        pivots[pivot] = solved
        for slot in solved[1]:
            users.setdefault(slot, {})[pivot] = None
    return pivots


def _substitute(
    constant: float,
    terms: tuple[tuple[Slot, float], ...],
    pivots: dict[Slot, _Expression],
) -> _Expression:
    """Rewrite ``constant + terms`` in the cells that are not pivots.

    Returns:
        _Expression: The constant and the coefficients of the other cells.
    """
    row: dict[Slot, float] = {}
    for slot, c in terms:
        solved = pivots.get(slot)
        if solved is None:
            row[slot] = row.get(slot, 0.0) + c
            continue
        constant += c * solved[0]
        for other, factor in solved[1].items():
            row[other] = row.get(other, 0.0) + c * factor
    return constant, {slot: c for slot, c in row.items() if abs(c) > 1e-12}


def _feasible(
    rows: list[tuple[float, tuple[tuple[Slot, float], ...]]],
    values: dict[Slot, float],
    limits: dict[Slot, list[float]],
    passes: int,
    relaxation: float,
) -> None:
    """Move values until every ``constant + terms >= 0`` holds, if it can.

    A violated row is met by the smallest change of its cells that can move
    the way it needs, over-relaxed past the boundary so that rows sharing
    cells settle sooner, and clamped to the cells' bounds. A row is checked
    again only after one of its cells moved.
    """
    uses: dict[Slot, list[int]] = {}
    for index, (_constant, terms) in enumerate(rows):
        for slot, _c in terms:
            uses.setdefault(slot, []).append(index)
    queue = deque(range(len(rows)))
    queued = [True] * len(rows)
    budget = passes * len(rows)
    while queue and budget:
        budget -= 1
        index = queue.popleft()
        queued[index] = False
        constant, terms = rows[index]
        excess = constant + sum(values[slot] * c for slot, c in terms)
        if excess >= -0.01:
            continue
        movable = []
        for slot, c in terms:
            bounds = limits.get(slot)
            if bounds is None or (
                values[slot] < bounds[1] if c > 0 else values[slot] > bounds[0]
            ):
                movable.append((slot, c))
        norm = sum(c * c for _slot, c in movable)
        if not norm:
            continue
        step = relaxation * excess / norm
        for slot, c in movable:
            value = values[slot] - c * step
            bounds = limits.get(slot)
            if bounds is not None:
                value = min(max(value, bounds[0]), bounds[1])
            if value != values[slot]:
                values[slot] = value
                for other in uses[slot]:
                    if not queued[other]:
                        queued[other] = True
                        queue.append(other)


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
    ``factValue`` per cell, with the open keys of the row, and a ``unit``
    for a cell in its currency of denomination: the currency of a ``CUS``
    or ``CUA`` key, else the template's currency. The entity is
    ``<entity>.<reporting level>`` in the reporting-subject scheme; before
    the reference date 2022-12-31, or for a module whose code has ``_con``
    or ``_ind``, it is the bare LEI in the LEI scheme (EBA filing rule 3.6).
    Every table's filing indicator is reported as ``true`` and the
    template's other ``filing_indicators`` as ``false``. ``baseCurrency``
    is the template's currency when a monetary fact is reported, and a
    ``decimals*`` parameter is set for each numeric data type the template
    uses.
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
    # Monetary facts are in the base currency, unless they are in their
    # currency of denomination (EBA filing rule 3.1).
    base_currency = False
    for table in template.tables:
        # A table with a unit column has it in every row (EBA xBRL-CSV
        # header rule), empty for facts without a unit.
        units = any(cell.unit for cell in table.cells)
        for keys in data.key_rows[table.code]:
            for cell in table.cells:
                slot = (cell.datapoint, keys)
                value = data.values.get(slot)
                if value is None or (table.code, slot) in emitted:
                    continue
                emitted.add((table.code, slot))
                columns = {_column(table, name): data._text(key) for name, key in keys}
                if units:
                    columns["unit"] = _unit(data, keys) if cell.unit else ""
                if not cell.unit:
                    base_currency = base_currency or cell.data_type == "m"
                facts.append(
                    Fact(
                        data._text(value),
                        datapoint=cell.datapoint,
                        template=table.code.lower(),
                        keys=columns,
                    )
                )
    used_types = {cell.data_type for table in template.tables for cell in table.cells}
    reference_date = template.reference_date or DEFAULT_REFERENCE_DATE
    # A subject with a suffix uses the reporting-subject scheme, a bare LEI
    # the LEI scheme (EBA filing rule 3.6).
    if reference_date < _SUFFIX_FROM or _LEVEL_MODULE.search(template.module):
        prefix, scheme, entity_id = "lei", _LEI_SCHEME, data.entity
    else:
        prefix, scheme = "rs", _RSCHEME
        entity_id = f"{data.entity}.{data.reporting_level}"
    return Report(
        format="xbrl-csv",
        entry_point=template.entry_point,
        entity_scheme=scheme,
        entity_id=entity_id,
        reference_date=reference_date,
        # baseCurrency is written only when a fact refers to it (EBA filing
        # rules, the xBRL-CSV parameters file).
        base_currency=f"iso4217:{template.currency or 'EUR'}"
        if base_currency
        else None,
        parameters={},
        decimals_parameters={
            parameter: data.decimals[kind]
            for kind, parameter in _DECIMALS_PARAMETERS.items()
            if kind in used_types
        },
        filing_indicators=_filing_indicators(template),
        facts=tuple(facts),
        namespaces={
            prefix: scheme,
            "iso4217": "http://www.xbrl.org/2003/iso4217",
        },
    )


_CURRENCY_KEYS = {"CUS", "CUA"}


def _unit(data: SyntheticData, keys: tuple[tuple[str, Any], ...]) -> str:
    """Return the unit of a fact in its currency of denomination.

    The currency of a ``CUS`` or ``CUA`` key, such as ``eba_CU:USD``, when
    it is a currency code (EBA filing rule 3.1(c)); otherwise the reporting
    currency.

    Returns:
        str: An ``iso4217:`` unit.
    """
    for name, value in keys:
        if name in _CURRENCY_KEYS:
            code = data._text(value).rpartition(":")[2]
            if _CURRENCY.fullmatch(code):
                return f"iso4217:{code}"
    return f"iso4217:{data.template.currency or 'EUR'}"


def _filing_indicators(template: ModuleTemplate) -> dict[str, bool]:
    reported = dict.fromkeys(table.filing_indicator for table in template.tables)
    if not template.filing_indicators:
        return dict.fromkeys(reported, True)
    return {code: code in reported for code in template.filing_indicators}


def _column(table: TemplateTable, code: str) -> str:
    return next((key.column for key in table.open_keys if key.code == code), code)


__all__ = [
    "DEFAULT_ENTITY",
    "DEFAULT_REFERENCE_DATE",
    "LEI_PREFIX",
    "MAX_OPEN_ROWS",
    "STATUSES",
    "GenerationResult",
    "SyntheticData",
    "build_report",
    "generate",
]
