"""Turn a free-text description of a patient into a (partial) PatientProfile.

Deterministic on purpose: it costs no LLM quota, so it powers both the "describe it in your own
words" intake and the TREC benchmark, where the patients arrive as clinical notes.
  - age / sex: patterns ("58-year-old man", "she")
  - conditions: n-gram lookup against condition names and MeSH terms used in the trial corpus,
    longest match wins, ranked by rarity
  - history: each sentence goes through the same concept reader used on eligibility criteria,
    so negation ("no history of HIV") is handled the same way
"""
from __future__ import annotations

import math
import re
from collections import Counter
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

from .db import fetch_all
from .parsing.rules import parse_line
from .parsing.schema import CriterionLine
from .vocab import CONCEPTS

_AGE = [
    re.compile(r"\b(\d{1,3})[- ](?:year|yr)s?[- ]old\b", re.I),
    re.compile(r"\b(\d{1,3})\s*(?:yo|y/o|y\.o\.)\b", re.I),
    re.compile(r"\baged?\s*(\d{1,3})\b", re.I),
    re.compile(r"\bI(?:'m| am)\s*(\d{1,3})\b", re.I),
    re.compile(r"\b(?:is|turned)\s+(\d{2,3})\b(?!\s*(?:%|mg|kg|cm|mm|days?|weeks?|months?|lbs?|pounds?|units?))", re.I),
]
_INFANT = re.compile(r"\b(\d{1,2})[- ](?:month|week)s?[- ]old\b", re.I)
_MALE = re.compile(r"\b(man|male|boy|gentleman|he|his|him|husband|father)\b", re.I)
_FEMALE = re.compile(r"\b(woman|female|girl|lady|she|her|hers|wife|mother|pregnant)\b", re.I)
_SENTENCE = re.compile(r"(?<=[.!?;])\s+|\n+")
_WORD = re.compile(r"[a-z0-9][a-z0-9'\-]*")
# names too generic to count as "the condition"
_GENERIC = {"disease", "diseases", "syndrome", "disorder", "pain", "cancer", "neoplasms", "tumor", "infection",
            "infections", "healthy", "healthy volunteers", "inflammation", "fatigue", "obesity", "hypertension",
            "chronic disease", "chronic pain", "carcinoma", "depression", "anxiety", "stress", "death", "aging",
            "quality of life", "smoking", "surgery", "fever", "cough", "edema", "weight loss", "nausea"}
_LIST_FIELDS = {
    "comorbidities": {"diabetes", "heart_disease", "stroke", "kidney_disease", "liver_disease", "hiv", "hepatitis",
                      "autoimmune_disease", "active_infection", "other_malignancy", "seizure", "psychiatric",
                      "substance_use", "transplant"},
    "treatments": {"chemotherapy", "immunotherapy", "radiation", "surgery", "targeted_therapy", "hormone_therapy"},
    "medications": {"insulin", "anticoagulant", "steroids"},
}


@lru_cache(maxsize=1)
def _condition_vocab() -> Tuple[Dict[str, str], Dict[str, float], int]:
    """lowercase term -> display form, plus a rarity weight per term."""
    rows = fetch_all("SELECT conditions, mesh_terms FROM trials")
    df: Counter = Counter()
    display: Dict[str, str] = {}
    for r in rows:
        terms = {t.strip() for t in (r["conditions"] or []) + (r["mesh_terms"] or []) if t and 3 < len(t) < 60}
        for t in terms:
            key = t.lower()
            df[key] += 1
            display.setdefault(key, t)
    n = max(1, len(rows))
    vocab = {k: display[k] for k, c in df.items() if c >= 2 and k not in _GENERIC and len(k.split()) <= 6}
    idf = {k: math.log((n + 1) / (df[k] + 1)) for k in vocab}
    max_words = max((len(k.split()) for k in vocab), default=1)
    return vocab, idf, max_words


def reset_vocab_cache() -> None:
    _condition_vocab.cache_clear()


def find_conditions(text: str, limit: int = 4) -> List[Dict]:
    vocab, idf, max_words = _condition_vocab()
    words = [(m.group(0), m.start(), m.end()) for m in _WORD.finditer(text.lower())]
    found: List[Tuple[int, int, str]] = []
    i = 0
    while i < len(words):
        hit = None
        for n in range(min(max_words, len(words) - i), 0, -1):  # longest match first
            phrase = " ".join(w for w, _, _ in words[i:i + n])
            if phrase in vocab:
                hit = (words[i][1], words[i + n - 1][2], phrase, n)
                break
        if hit:
            found.append(hit[:3])
            i += hit[3]
        else:
            i += 1
    seen, out = set(), []
    for start, end, key in sorted(found, key=lambda f: -idf.get(f[2], 0)):
        if key in seen:
            continue
        seen.add(key)
        out.append({"term": vocab[key], "start": start, "end": end})
    return out[:limit]


def extract(text: str) -> Dict:
    text = (text or "").strip()
    profile: Dict = {}
    evidence: List[Dict] = []

    for rx in _AGE:
        m = rx.search(text)
        if m and 0 < int(m.group(1)) < 120:
            profile["age"] = int(m.group(1))
            evidence.append({"field": "age", "value": profile["age"], "start": m.start(), "end": m.end()})
            break
    if "age" not in profile and _INFANT.search(text):
        profile["age"] = 0

    male, female = len(_MALE.findall(text)), len(_FEMALE.findall(text))
    if male != female:
        profile["sex"] = "male" if male > female else "female"

    conds = find_conditions(text)
    if conds:
        profile["conditions"] = [c["term"] for c in conds]
        evidence += [{"field": "conditions", "value": c["term"], "start": c["start"], "end": c["end"]} for c in conds]

    lists: Dict[str, set] = {k: set() for k in _LIST_FIELDS}
    offset = 0
    for i, sentence in enumerate(_SENTENCE.split(text)):
        start = text.find(sentence, offset)
        offset = max(offset, start)
        for c in parse_line(CriterionLine(index=i, kind="inclusion", text=sentence)):
            concept = CONCEPTS.get(c.concept)
            field = concept.profile_field if concept else None
            if not field or field in ("age", "condition_match"):
                continue
            value: Optional[object]
            if concept.kind == "num":
                value = c.value if c.value is not None and c.operator in ("between", ">=", "<=") else None
                if field == "ecog" and value is not None:
                    value = int(value)
            else:
                value = c.operator != "absent"
            if value is None:
                continue
            list_name = next((k for k, members in _LIST_FIELDS.items() if field in members), None)
            if list_name:
                if value:
                    lists[list_name].add(field)
            elif field not in profile:
                profile[field] = value
            evidence.append({"field": field, "value": value, "start": start, "end": start + len(sentence)})
    for k, v in lists.items():
        if v:
            profile[k] = sorted(v)
    if profile.get("sex") == "male":
        profile.pop("pregnant", None)
        profile.pop("breastfeeding", None)
    return {"profile": profile, "evidence": evidence}
