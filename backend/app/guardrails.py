"""Post-checks on AI-written explanations, using the rule check as ground truth.

Each explanation is compared with the criterion statuses it was written from:
  - unsafe:          claims of eligibility or advice to enroll                 -> sentence removed
  - contradiction:   "why it may fit" cites a concept the check marked a conflict -> item removed
  - false_unknown:   "unclear whether X" when the patient answered X            -> item removed
  - missed_conflict: a conflict the explanation never mentions                 -> item added
Also computes a reading grade (Flesch-Kincaid) for the evaluation.
"""
from __future__ import annotations

import re
from typing import Dict, List, Set

from .vocab import CONCEPTS

UNSAFE = re.compile(
    r"\byou(?:'re| are| will be)? (?:definitely |likely |probably )?(?:eligible|qualif(?:y|ied))\b|"
    r"\byou should (?:enroll|join|sign up|participate)\b|\bguarantee|\bwill cure\b|\bstop (?:taking|your) ",
    re.I,
)
UNCERTAIN = re.compile(r"\b(?:unclear|unknown|not sure|uncertain|not known|did(?:n't| not) (?:say|mention|report))\b", re.I)
_SENT = re.compile(r"(?<=[.!?])\s+")
LIST_KEYS = ["why_it_may_fit", "things_to_check", "questions_for_your_doctor"]


_HEDGE = re.compile(r"\b(?:whether|if|confirm|determine|decide|check|only the study team|cannot say)\b", re.I)


def is_unsafe(text: str) -> bool:
    """Eligibility claims and advice, ignoring hedged mentions ("the team will confirm whether you are eligible")."""
    for m in UNSAFE.finditer(text):
        if not _HEDGE.search(text[max(0, m.start() - 45):m.start()]):
            return True
    return False


def concepts_in(text: str) -> Set[str]:
    return {cid for cid, c in CONCEPTS.items() if c.profile_field and any(p.search(text) for p in c.compiled)}


def _by_status(criteria: List[dict]) -> Dict[str, Set[str]]:
    out: Dict[str, Set[str]] = {}
    for c in criteria:
        out.setdefault(c["status"], set()).add(c["concept"])
    return out


def audit(body: Dict, criteria: List[dict]) -> Dict[str, List]:
    """Find problems without changing anything (used by the evaluation)."""
    status = _by_status(criteria)
    conflicts = status.get("not_met", set())
    clear_conflicts = conflicts - status.get("met", set())  # ambiguous when a concept also has a met rule
    answered = status.get("met", set()) | conflicts | status.get("caution", set())
    issues: Dict[str, List] = {"unsafe": [], "contradiction": [], "false_unknown": [], "missed_conflict": []}
    texts = [body.get("summary", "")] + [t for k in LIST_KEYS for t in body.get(k, [])]
    issues["unsafe"] = [t for t in texts if is_unsafe(t)]
    for item in body.get("why_it_may_fit", []):
        hit = concepts_in(item) & clear_conflicts
        if hit:
            issues["contradiction"].append({"text": item, "concepts": sorted(hit)})
    for item in body.get("things_to_check", []):
        if UNCERTAIN.search(item):
            hit = concepts_in(item) & (answered - status.get("unknown", set()))
            # only flag when every concept it calls unclear was actually answered
            if hit and not (concepts_in(item) & status.get("unknown", set())):
                issues["false_unknown"].append({"text": item, "concepts": sorted(hit)})
    mentioned = set().union(*[concepts_in(t) for t in texts]) if texts else set()
    issues["missed_conflict"] = sorted(conflicts - mentioned - {"diagnosis"})
    return issues


def apply(body: Dict, criteria: List[dict]) -> Dict:
    """Repair an explanation in place and record what was changed."""
    issues = audit(body, criteria)
    removed = 0
    sentences = [s for s in _SENT.split(body.get("summary", "")) if s]
    kept = [s for s in sentences if not is_unsafe(s)]
    removed += len(sentences) - len(kept)
    body["summary"] = " ".join(kept)
    bad_items = {d["text"] for d in issues["contradiction"]} | {d["text"] for d in issues["false_unknown"]}
    for key in LIST_KEYS:
        before = body.get(key, [])
        body[key] = [t for t in before if t not in bad_items and not is_unsafe(t)]
        removed += len(before) - len(body[key])
    added = 0
    reasons = {c["concept"]: c["reason"] for c in criteria if c["status"] == "not_met"}
    for concept in issues["missed_conflict"]:
        if concept in reasons:
            body.setdefault("things_to_check", []).insert(0, reasons[concept])
            added += 1
    body["guardrail"] = {"removed": removed, "added": added}
    return body


def _syllables(word: str) -> int:
    word = word.lower()
    groups = re.findall(r"[aeiouy]+", word)
    n = len(groups) - (1 if word.endswith("e") and len(groups) > 1 else 0)
    return max(1, n)


def reading_grade(text: str) -> float:
    words = re.findall(r"[A-Za-z']+", text)
    sentences = max(1, len(re.findall(r"[.!?]+", text)))
    if not words:
        return 0.0
    syll = sum(_syllables(w) for w in words)
    return round(0.39 * len(words) / sentences + 11.8 * syll / len(words) - 15.59, 1)
