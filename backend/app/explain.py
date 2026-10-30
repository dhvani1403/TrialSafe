"""Plain-language "why this trial?" explanations: LLM when budget allows, template otherwise."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Dict, List

from . import guardrails
from .db import execute, fetch_one, jsonb
from .llm import LLMUnavailable, chat_json
from .matching import PatientProfile

SYSTEM = """You help patients understand whether a clinical trial might be worth asking their doctor about.
Write at an 8th-grade reading level, warm and plain. Never tell someone they are eligible or should enroll;
only the study team can decide. Do not give medical advice. Base everything ONLY on the information given.
Return a JSON object with exactly these four keys, each list a JSON array of short strings:
{"summary": str (2 sentences: what the study tests and who it is for),
"why_it_may_fit": [str, ...] (max 3), "things_to_check": [str, ...] (max 4, include unmet or unknown items),
"questions_for_your_doctor": [str, ...] (max 3)}"""

SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "why_it_may_fit": {"type": "array", "items": {"type": "string"}},
        "things_to_check": {"type": "array", "items": {"type": "string"}},
        "questions_for_your_doctor": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "why_it_may_fit", "things_to_check", "questions_for_your_doctor"],
    "additionalProperties": False,
}


_LIST_KEYS = ["why_it_may_fit", "things_to_check", "questions_for_your_doctor"]
_SECTION = re.compile(r"(?:\\n|\s)*(why_it_may_fit|things_to_check|questions_for_your_doctor)\b\s*:\s*", re.I)


def _split_items(text: str, questions: bool) -> List[str]:
    text = text.replace("\\n", "\n").strip()
    parts = re.split(r"\n+|^\s*[-*•]\s*", text, flags=re.M)
    if len(parts) <= 1:
        parts = re.findall(r"[^?]+\?", text) if questions else re.split(r"(?<=\.)\s+(?=[A-Z])", text)
    return [p.strip(" -*•\n") for p in parts if p and p.strip(" -*•\n")][:4]


def normalise(body: Dict) -> Dict:
    """Free models sometimes pack every section into `summary`; split them back out."""
    summary = str(body.get("summary") or "")
    if _SECTION.search(summary):
        chunks = _SECTION.split(summary)
        body["summary"] = chunks[0].replace("\\n", " ").strip()
        for key, val in zip(chunks[1::2], chunks[2::2]):
            key = key.lower()
            if not body.get(key):
                body[key] = _split_items(val, questions=key.startswith("questions"))
    for key in _LIST_KEYS:
        val = body.get(key) or []
        if isinstance(val, str):
            val = _split_items(val, questions=key.startswith("questions"))
        body[key] = [str(v).strip() for v in val if str(v).strip()]
    body["summary"] = summary_clean(body.get("summary", ""))
    return body


def summary_clean(text: str) -> str:
    return re.sub(r"\s+", " ", str(text).replace("\\n", " ")).strip()


def _profile_key(profile: PatientProfile) -> Dict:
    # no location: explanations don't depend on it, and we avoid storing it
    return profile.model_dump(exclude={"location", "max_distance_mi"})


def _cache_key(nct_id: str, criteria_hash: str, profile: PatientProfile) -> str:
    raw = json.dumps([nct_id, criteria_hash, _profile_key(profile)], sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def _patient_line(p: PatientProfile) -> str:
    bits = [f"{p.age}-year-old {p.sex}"]
    if p.conditions:
        bits.append("with " + ", ".join(p.conditions))
    if p.ecog is not None:
        bits.append(f"ECOG {p.ecog}")
    for name in ("comorbidities", "treatments", "medications"):
        v = getattr(p, name)
        if v:
            bits.append(f"{name}: {', '.join(v)}")
    return "; ".join(bits)


def template(trial: dict, criteria: List[dict]) -> Dict:
    met = [c["reason"] for c in criteria if c["status"] == "met" and c["concept"] != "diagnosis"][:3]
    check = [c["reason"] for c in criteria if c["status"] in ("not_met", "caution")][:3]
    unknown = [c["label"] for c in criteria if c["status"] == "unknown"][:3]
    if unknown:
        check.append("Not enough information yet about: " + ", ".join(u.lower() for u in unknown) + ".")
    summary = (trial.get("summary") or trial["title"]).split(". ")
    return {
        "summary": ". ".join(summary[:2]).strip().rstrip(".") + ".",
        "why_it_may_fit": met or ["It studies a condition that matches what you entered."],
        "things_to_check": check or ["The study team will confirm the full eligibility list at screening."],
        "questions_for_your_doctor": [
            "Would this study be a reasonable option alongside my current care?",
            "Are there lab tests or records the study team would need from me?",
            "What would participating involve in terms of visits and travel?",
        ],
        "source": "template",
    }


def explain(trial: dict, criteria: List[dict], profile: PatientProfile) -> Dict:
    key = _cache_key(trial["nct_id"], trial.get("criteria_hash") or "", profile)
    cached = fetch_one("SELECT body FROM explanations WHERE cache_key = %s", (key,))
    if cached:
        return {**guardrails.apply(normalise(dict(cached["body"])), criteria), "cached": True}

    try:
        body = generate(trial, criteria, profile)
    except LLMUnavailable as exc:
        body = template(trial, criteria)
        body["note"] = f"AI explanation unavailable ({exc}); showing an automatic summary."
        return body
    # cache the model's own words; guardrails run on every read so rule changes apply retroactively
    execute("INSERT INTO explanations (cache_key, nct_id, body) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
            (key, trial["nct_id"], jsonb(body)))
    return guardrails.apply(dict(body), criteria)


def prompt_for(trial: dict, criteria: List[dict], profile: PatientProfile) -> str:
    # spell out answered "no"s so the model doesn't call them unclear
    lines = [f"- [{c['status']}] {c['label']}: {c['reason']}" for c in criteria if c["status"] != "review"][:25]
    return (f"STUDY: {trial['title']}\nSUMMARY: {(trial.get('summary') or '')[:1200]}\n"
            f"PATIENT: {_patient_line(profile)}\n"
            "CRITERIA CHECK (automated, may contain errors). [met] and [not_met] items were answered by the "
            "patient; only [unknown] items are unanswered:\n" + "\n".join(lines))


def generate(trial: dict, criteria: List[dict], profile: PatientProfile) -> Dict:
    """One LLM call, normalised but not yet guarded. Raises LLMUnavailable."""
    body, model = chat_json("explain", SYSTEM, prompt_for(trial, criteria, profile), schema=SCHEMA,
                            max_tokens=900, temperature=0.3)
    if not isinstance(body, dict) or "summary" not in body:
        raise LLMUnavailable("malformed explanation")
    body = normalise({k: body.get(k, []) for k in SCHEMA["properties"]})
    if not any(body[k] for k in _LIST_KEYS):
        raise LLMUnavailable("explanation had no list items")
    body["source"] = "llm"
    body["model"] = model
    return body
