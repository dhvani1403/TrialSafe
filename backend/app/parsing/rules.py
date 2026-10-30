"""Deterministic baseline parser: section splitting, dictionary matching,
NegEx-style negation and numeric threshold extraction."""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

from ..vocab import CONCEPTS, NUM
from .schema import Criterion, CriterionLine, ParsedEligibility

_HEADER = re.compile(
    r"^\s*(?:\*\*)?\s*(?:key\s+|main\s+|general\s+|additional\s+)?(inclusion|exclusion)\s*(?:criteria)?\b[^\n]{0,40}:?\s*(?:\*\*)?\s*$",
    re.I,
)
_BULLET = re.compile(r"^\s*(?:[*\-•·]|\d{1,2}[.)]|[a-z][.)]|\([a-z0-9]{1,2}\))\s+", re.I)
_UNESCAPE = re.compile(r"\\([<>\[\]()*_#+\-.!~|])")

_NEG_CUE = re.compile(
    r"\b(?:no|not|without|never|absence of|free of|must not|cannot|can't|negative for|denies|none|"
    r"(?:do|does|did|is|are|was|were|has|have|had)n['’]t)\b",
    re.I,
)
# phrases that contain a negation word but are really quantity limits
_PSEUDO_NEG = re.compile(
    r"\b(?:no|not)\s+(?:more|greater|less|fewer|later|earlier|sooner|longer|higher|lower)\s+than\b|\bnot\s+exceed",
    re.I,
)
_POST_NEG = re.compile(r"^[^.;:]{0,20}\b(?:negative|free|not detected|undetectable)\b", re.I)
_CLAUSE_BREAK = re.compile(r"[;:]|\bbut\b|\bexcept\b|\bunless\b|\bother than\b", re.I)
_TIMEFRAME = re.compile(
    r"\b(?:within|in the (?:last|past|previous)|during the (?:last|past)|<|≤)\s*(?:the\s+)?(\d+|one|two|three|four|six|twelve)\s*(day|week|month|year)s?\b",
    re.I,
)

_NUM = r"(\d+(?:\.\d+)?)"
_RANGE = re.compile(rf"(?:between\s+)?{_NUM}\s*(?:%|years?|kg/m2|kg/m²)?\s*(?:-|–|—|to|and|or|through)\s*{_NUM}", re.I)
_GE = re.compile(
    rf"(?:≥|>=|=>|>|at least|greater than or equal to|greater than|more than|above|over|older than|minimum(?: of)?|aged?)\s*(?:of\s+)?{_NUM}",
    re.I,
)
_LE = re.compile(
    rf"(?:≤|<=|=<|<|less than or equal to|less than|below|under|up to|younger than|no more than|not more than|not exceed(?:ing)?|maximum(?: of)?)\s*(?:of\s+)?{_NUM}",
    re.I,
)
_SUFFIX = re.compile(rf"{_NUM}\s*(?:%|years?|kg/m2|kg/m²)?\s*(or (?:less|lower|below|younger)|or (?:more|greater|higher|above|older))", re.I)
_SINGLE = re.compile(rf"(?:of|=|:)\s*{_NUM}\b", re.I)


def clean(text: str) -> str:
    return _UNESCAPE.sub(r"\1", text or "").replace("\u2265", "≥").replace("\u2264", "≤")


def split_lines(text: str) -> List[CriterionLine]:
    """Split CT.gov free text into bullet-level lines tagged inclusion/exclusion."""
    kind = "inclusion"
    out: List[CriterionLine] = []
    buf: List[str] = []

    def flush() -> None:
        if buf:
            line = " ".join(s.strip() for s in buf).strip()
            if len(line) > 3:
                out.append(CriterionLine(index=len(out), kind=kind, text=line))
            buf.clear()

    for raw in clean(text).splitlines():
        if not raw.strip():
            flush()
            continue
        h = _HEADER.match(raw)
        if h:
            flush()
            kind = h.group(1).lower()
            continue
        if _BULLET.match(raw):
            flush()
            buf.append(_BULLET.sub("", raw, count=1))
        else:
            buf.append(raw)
    flush()
    return out


def _negated(line: str, start: int, end: int) -> bool:
    window = line[max(0, start - 60):start]
    # only consider the clause the concept is in
    parts = _CLAUSE_BREAK.split(window)
    clause = parts[-1] if parts else window
    clause = _PSEUDO_NEG.sub(" ", clause)
    if _NEG_CUE.search(clause):
        return True
    return bool(_POST_NEG.match(line[end:end + 40]))


def _numeric(segment: str) -> Tuple[str, Optional[float], Optional[float]]:
    m = _RANGE.search(segment)
    if m:
        a, b = float(m.group(1)), float(m.group(2))
        if a <= b:
            return "between", a, b
    m = _SUFFIX.search(segment)
    if m:
        v = float(m.group(1))
        return ("<=", None, v) if re.search(r"less|lower|below|younger", m.group(2), re.I) else (">=", v, None)
    ge, le = _GE.search(segment), _LE.search(segment)
    if ge and le:
        return "between", float(ge.group(1)), float(le.group(1))
    if le:
        return "<=", None, float(le.group(1))
    if ge:
        return ">=", float(ge.group(1)), None
    m = _SINGLE.search(segment)
    if m:
        v = float(m.group(1))
        return "between", v, v
    return "present", None, None


def _sanity(concept: str, op: str, lo: Optional[float], hi: Optional[float]) -> bool:
    bounds = {"age": (0, 120), "ecog": (0, 5), "karnofsky": (10, 100), "bmi": (10, 80),
              "hba1c": (3, 20), "egfr_lab": (5, 200), "life_expectancy": (1, 120)}
    if concept not in bounds or op == "present":
        return True
    a, b = bounds[concept]
    return all(v is None or a <= v <= b for v in (lo, hi))


def parse_line(line: CriterionLine) -> List[Criterion]:
    text = line.text
    found: List[Criterion] = []
    seen = set()
    for c in CONCEPTS.values():
        for pat in c.compiled:
            m = pat.search(text)
            if not m or c.id in seen:
                continue
            seen.add(c.id)
            op, lo, hi = "present", None, None
            if c.kind == NUM:
                op, lo, hi = _numeric(text[m.start():m.start() + 90])
                if op == "present":  # number written before the keyword, e.g. "≥ 18 years of age"
                    op, lo, hi = _numeric(text[max(0, m.start() - 25):m.end()])
                if not _sanity(c.id, op, lo, hi):
                    op, lo, hi = "present", None, None
                if c.id == "age" and op == "present":
                    seen.discard(c.id)   # bare mention of "age" carries no rule
                    break
            elif _negated(text, m.start(), m.end()):
                op = "absent"
            tf = _TIMEFRAME.search(text)
            if op == "between":
                value, value_max = lo, hi
            elif op == "<=":
                value, value_max = hi, None
            else:
                value, value_max = lo, None
            found.append(Criterion(
                line=line.index, text=text, kind=line.kind, concept=c.id, category=c.category,
                operator=op, value=value, value_max=value_max, unit=c.unit,
                timeframe=tf.group(0) if tf and c.category in ("prior_therapy", "medication", "comorbidity") else None,
            ))
            break
    ids = {f.concept for f in found}
    if "brain_metastases" in ids:
        found = [f for f in found if f.concept != "metastatic"]
    if "hba1c" in ids:
        found = [f for f in found if f.concept != "lab_values"]
    return found


def parse(text: str) -> ParsedEligibility:
    lines = split_lines(text)
    criteria: List[Criterion] = []
    for ln in lines:
        criteria.extend(parse_line(ln))
    min_age = max_age = None
    for c in criteria:
        if c.concept == "age" and c.kind == "inclusion":
            if c.operator in (">=", "between") and c.value is not None:
                min_age = c.value if min_age is None else min(min_age, c.value)
            if c.operator == "between" and c.value_max is not None:
                max_age = c.value_max if max_age is None else max(max_age, c.value_max)
            if c.operator == "<=" and c.value is not None:
                max_age = c.value if max_age is None else max(max_age, c.value)
    return ParsedEligibility(parser="rules", lines=lines, criteria=criteria, min_age=min_age, max_age=max_age)
