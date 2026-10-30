"""LLM parser: annotates the deterministic line split with concepts from the shared vocabulary."""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from ..llm import chat_json
from ..vocab import CONCEPT_IDS, CONCEPTS
from .rules import split_lines
from .schema import Criterion, CriterionLine, ParsedEligibility

SYSTEM = """You are a clinical research coordinator converting clinical-trial eligibility criteria into structured rules.
You receive numbered criterion lines, each tagged INCLUSION or EXCLUSION. For every line, list the concepts it
constrains, using ONLY these concept ids:

{catalog}

For each concept give an operator:
- "present": the line is about the patient HAVING this (e.g. exclusion "Known HIV" -> hiv present;
  inclusion "Prior treatment with an anti-PD-1" -> prior_immunotherapy present).
- "absent": the line requires the patient NOT having it, phrased inside the line (e.g. inclusion "No prior
  chemotherapy" -> prior_chemotherapy absent; inclusion "must not be pregnant" -> pregnancy absent).
- ">=", "<=", "between": numeric limits for age, ecog, karnofsky, bmi, hba1c, egfr_lab, life_expectancy.
  Use value (lower or single bound) and value_max (upper bound for between). "ECOG 0-1" -> between 0 and 1.
  For "<=" put the bound in value.
Rules:
- Do not flip polarity because a line is an exclusion; describe what the line literally refers to.
- Statements that something is ALLOWED/permitted ("steroids at physiologic doses are permitted") are not constraints: skip them.
- Use "diagnosis" for lines requiring a confirmed diagnosis of the study condition.
- Add timeframe (e.g. "within 4 weeks") when a history item is time-limited, else null.
- Skip lines with no concept from the list. Never invent concepts."""

_ITEM = {
    "type": "object",
    "properties": {
        "line": {"type": "integer"},
        "concept": {"type": "string", "enum": CONCEPT_IDS},
        "operator": {"type": "string", "enum": ["present", "absent", ">=", "<=", "between"]},
        "value": {"type": ["number", "null"]},
        "value_max": {"type": ["number", "null"]},
        "timeframe": {"type": ["string", "null"]},
    },
    "required": ["line", "concept", "operator", "value", "value_max", "timeframe"],
    "additionalProperties": False,
}
SCHEMA = {
    "type": "object",
    "properties": {"annotations": {"type": "array", "items": _ITEM}},
    "required": ["annotations"],
    "additionalProperties": False,
}


def _catalog() -> str:
    return "\n".join(f"- {c.id}: {c.label}" + (f" ({c.description})" if c.description else "")
                     for c in CONCEPTS.values())


CHUNK = 15  # long single calls time out on free models; ~15 lines returns in seconds


def annotate_lines(lines: List[CriterionLine], purpose: str = "parse") -> Tuple[List[Criterion], str]:
    annotations, models = [], []
    for start in range(0, len(lines), CHUNK):
        chunk = lines[start:start + CHUNK]
        user = "\n".join(f"[{ln.index}] {ln.kind.upper()}: {ln.text[:500]}" for ln in chunk)
        out, model = chat_json(purpose, SYSTEM.format(catalog=_catalog()), user, schema=SCHEMA, max_tokens=2500)
        models.append(model)
        if isinstance(out, dict):
            annotations.extend(out.get("annotations", []))
        elif isinstance(out, list):
            annotations.extend(out)
    model = max(set(models), key=models.count) if models else ""
    by_index: Dict[int, CriterionLine] = {ln.index: ln for ln in lines}
    criteria: List[Criterion] = []
    seen = set()
    for a in annotations:
        if not isinstance(a, dict):
            continue
        ln = by_index.get(a.get("line"))
        cid = a.get("concept")
        if ln is None or cid not in CONCEPTS or (ln.index, cid) in seen:
            continue
        seen.add((ln.index, cid))
        op = a.get("operator") if a.get("operator") in ("present", "absent", ">=", "<=", "between") else "present"
        criteria.append(Criterion(
            line=ln.index, text=ln.text, kind=ln.kind, concept=cid, category=CONCEPTS[cid].category,
            operator=op, value=_num(a.get("value")), value_max=_num(a.get("value_max")),
            unit=CONCEPTS[cid].unit, timeframe=a.get("timeframe") or None,
        ))
    return criteria, model


def _num(v) -> Optional[float]:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def parse(text: str, max_lines: int = 45) -> ParsedEligibility:
    lines = split_lines(text)[:max_lines]
    criteria, model = annotate_lines(lines)
    min_age = max_age = None
    for c in criteria:
        if c.concept == "age" and c.kind == "inclusion":
            if c.operator in (">=", "between"):
                min_age = c.value
            if c.operator == "between":
                max_age = c.value_max
            if c.operator == "<=":
                max_age = c.value
    return ParsedEligibility(parser="llm", model=model, lines=lines, criteria=criteria,
                             min_age=min_age, max_age=max_age)
