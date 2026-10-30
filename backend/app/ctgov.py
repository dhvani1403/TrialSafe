"""ClinicalTrials.gov API v2 client and record normalisation."""
from __future__ import annotations

import hashlib
import re
import time
from datetime import date
from typing import Any, Dict, Iterator, List, Optional

import httpx

API = "https://clinicaltrials.gov/api/v2/studies"
OPEN_STATUSES = "RECRUITING|NOT_YET_RECRUITING|ENROLLING_BY_INVITATION"

_AGE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(year|month|week|day|hour|minute)", re.I)
_UNIT_YEARS = {"year": 1.0, "month": 1 / 12, "week": 1 / 52, "day": 1 / 365, "hour": 1 / 8760, "minute": 1 / 525600}


def age_to_years(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    m = _AGE_RE.search(value)
    if not m:
        return None
    return round(float(m.group(1)) * _UNIT_YEARS[m.group(2).lower()], 3)


def _date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    parts = value.split("-")
    try:
        y, mth = int(parts[0]), int(parts[1]) if len(parts) > 1 else 1
        d = int(parts[2]) if len(parts) > 2 else 1
        return date(y, mth, d)
    except (ValueError, IndexError):
        return None


def criteria_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode()).hexdigest()[:16]


def iter_studies(condition: str, limit: int, client: httpx.Client) -> Iterator[Dict[str, Any]]:
    """Yield raw study records for open US trials matching a condition."""
    token: Optional[str] = None
    seen = 0
    while seen < limit:
        params = {
            "query.cond": condition,
            "query.locn": "United States",
            "filter.overallStatus": OPEN_STATUSES,
            "pageSize": min(100, limit - seen),
            "sort": "LastUpdatePostDate:desc",
        }
        if token:
            params["pageToken"] = token
        for attempt in range(4):
            try:
                resp = client.get(API, params=params, timeout=30)
                resp.raise_for_status()
                break
            except httpx.HTTPError:
                if attempt == 3:
                    raise
                time.sleep(2 ** attempt)
        payload = resp.json()
        for study in payload.get("studies", []):
            seen += 1
            yield study
        token = payload.get("nextPageToken")
        if not token:
            return


def normalise(study: Dict[str, Any]) -> Dict[str, Any]:
    p = study.get("protocolSection", {})
    ident = p.get("identificationModule", {})
    status = p.get("statusModule", {})
    sponsor = p.get("sponsorCollaboratorsModule", {}).get("leadSponsor", {})
    desc = p.get("descriptionModule", {})
    cond = p.get("conditionsModule", {})
    design = p.get("designModule", {})
    arms = p.get("armsInterventionsModule", {})
    elig = p.get("eligibilityModule", {})
    contacts = p.get("contactsLocationsModule", {})
    browse = study.get("derivedSection", {}).get("conditionBrowseModule", {})

    phases = design.get("phases") or []
    criteria = elig.get("eligibilityCriteria") or ""
    central = (contacts.get("centralContacts") or [None])[0]

    sites: List[Dict[str, Any]] = []
    for loc in contacts.get("locations", []) or []:
        geo = loc.get("geoPoint") or {}
        site_contact = next((c for c in loc.get("contacts", []) if c.get("phone") or c.get("email")), None)
        sites.append({
            "facility": loc.get("facility"),
            "city": loc.get("city"),
            "state": loc.get("state"),
            "zip": loc.get("zip"),
            "country": loc.get("country"),
            "status": loc.get("status"),
            "lat": geo.get("lat"),
            "lon": geo.get("lon"),
            "contact": site_contact,
        })

    return {
        "nct_id": ident.get("nctId"),
        "title": ident.get("briefTitle") or ident.get("officialTitle") or ident.get("nctId"),
        "official_title": ident.get("officialTitle"),
        "summary": desc.get("briefSummary"),
        "status": status.get("overallStatus"),
        "phase": "/".join(phases) if phases else "NA",
        "study_type": design.get("studyType"),
        "sponsor": sponsor.get("name"),
        "sponsor_class": sponsor.get("class"),
        "conditions": cond.get("conditions") or [],
        "keywords": cond.get("keywords") or [],
        "mesh_terms": [m["term"] for m in browse.get("meshes", []) if m.get("term")],
        "mesh_ancestors": [m["term"] for m in browse.get("ancestors", []) if m.get("term")],
        "interventions": [
            {"type": i.get("type"), "name": i.get("name")} for i in arms.get("interventions", []) or []
        ],
        "sex": elig.get("sex") or "ALL",
        "min_age_years": age_to_years(elig.get("minimumAge")),
        "max_age_years": age_to_years(elig.get("maximumAge")),
        "healthy_volunteers": elig.get("healthyVolunteers"),
        "eligibility_text": criteria,
        "criteria_hash": criteria_hash(criteria),
        "enrollment": (design.get("enrollmentInfo") or {}).get("count"),
        "start_date": _date((status.get("startDateStruct") or {}).get("date")),
        "last_update": _date((status.get("lastUpdatePostDateStruct") or {}).get("date")),
        "central_contact": central,
        "sites": sites,
    }
