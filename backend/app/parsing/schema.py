"""Structured eligibility representation shared by all parsers."""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

# "present"/"absent" for yes/no concepts; comparisons for numeric ones.
OPERATORS = ["present", "absent", ">=", "<=", "between"]


class Criterion(BaseModel):
    line: int = Field(description="index of the source line")
    text: str
    kind: str = Field(description="inclusion | exclusion")
    concept: str
    category: str
    operator: str = "present"
    value: Optional[float] = None
    value_max: Optional[float] = None
    unit: Optional[str] = None
    timeframe: Optional[str] = Field(None, description='e.g. "within 4 weeks"; makes history checks soft')


class CriterionLine(BaseModel):
    index: int
    kind: str
    text: str


class ParsedEligibility(BaseModel):
    parser: str
    model: Optional[str] = None
    lines: List[CriterionLine]
    criteria: List[Criterion]
    min_age: Optional[float] = None
    max_age: Optional[float] = None
