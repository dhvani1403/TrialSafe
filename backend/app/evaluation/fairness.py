"""Match-disparity audit: who gets fewer trial matches?

For a grid of synthetic patients (condition x age x sex x home location) we count the trials that
are condition-relevant, open to that age and sex, and have a site within 100 miles. Groups are
compared with a four-fifths style ratio (group mean / best group mean); ratios under 0.8 are flagged.
This measures access to *listed* trials, not clinical eligibility.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List

import numpy as np

from ..db import execute, fetch_all, jsonb
from ..geo import AUDIT_LOCATIONS
from ..matching import PatientProfile
from ..ranking import features as F
from ..search import retrieve

AUDIT_CONDITIONS = ["breast cancer", "lung cancer", "prostate cancer", "type 2 diabetes", "heart failure",
                    "alzheimer disease", "depression", "asthma", "HIV", "chronic kidney disease"]
AGES = [("18–34", 25), ("35–49", 42), ("50–64", 57), ("65–74", 70), ("75–84", 80), ("85+", 88)]
SEXES = ["female", "male"]
RADIUS_MI = 100.0


def _miles(lat: np.ndarray, lon: np.ndarray, lat0: float, lon0: float) -> np.ndarray:
    p1, p2 = np.radians(lat0), np.radians(lat)
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(np.radians(lon - lon0) / 2) ** 2
    return 3958.8 * 2 * np.arcsin(np.sqrt(a))


def _ratio_table(values: Dict[str, List[float]]) -> List[dict]:
    means = {k: float(np.mean(v)) for k, v in values.items()}
    best = max(means.values()) or 1.0
    return [{"group": k, "mean_matches": round(m, 2), "ratio": round(m / best, 3), "flag": m / best < 0.8}
            for k, m in means.items()]


def run_fairness_audit() -> Dict:
    heat: Dict[str, Dict[str, float]] = {}
    by_age, by_sex, by_region, by_setting, by_loc = (defaultdict(list) for _ in range(5))
    age_caps = []

    for condition in AUDIT_CONDITIONS:
        probe = PatientProfile(conditions=[condition], age=50, sex="female")
        ids = list(retrieve(probe))
        trials = fetch_all(
            """SELECT nct_id, title, conditions, mesh_terms, mesh_ancestors, sex, min_age_years, max_age_years
               FROM trials WHERE nct_id = ANY(%s)""", (ids,))
        relevant = [t for t in trials if F.condition_match([condition], t)["condition_score"] >= 0.6]
        rel_ids = [t["nct_id"] for t in relevant]
        sites = fetch_all("SELECT nct_id, lat, lon FROM sites WHERE nct_id = ANY(%s) AND lat IS NOT NULL", (rel_ids,))
        per_trial: Dict[str, List] = defaultdict(list)
        for s in sites:
            per_trial[s["nct_id"]].append((s["lat"], s["lon"]))
        # trial -> set of audit locations with a site in range
        reach = {}
        for t in relevant:
            pts = np.array(per_trial.get(t["nct_id"], []), dtype=float)
            reach[t["nct_id"]] = {
                loc[0] for loc in AUDIT_LOCATIONS
                if len(pts) and (_miles(pts[:, 0], pts[:, 1], loc[1], loc[2]) <= RADIUS_MI).any()
            }

        maxes = [t["max_age_years"] for t in relevant]
        age_caps.append({
            "condition": condition, "trials": len(relevant),
            "pct_cap_under_65": round(100 * sum(1 for m in maxes if m is not None and m < 65) / max(1, len(relevant)), 1),
            "pct_cap_under_75": round(100 * sum(1 for m in maxes if m is not None and m < 75) / max(1, len(relevant)), 1),
            "pct_sex_restricted": round(100 * sum(1 for t in relevant if t["sex"] != "ALL") / max(1, len(relevant)), 1),
        })

        heat[condition] = {}
        for band, age in AGES:
            band_counts = []
            for sex in SEXES:
                for label, lat, lon, setting, region in AUDIT_LOCATIONS:
                    n = sum(
                        1 for t in relevant
                        if (t["min_age_years"] is None or age >= t["min_age_years"])
                        and (t["max_age_years"] is None or age <= t["max_age_years"])
                        and (t["sex"] == "ALL" or t["sex"].lower() == sex)
                        and label in reach[t["nct_id"]]
                    )
                    band_counts.append(n)
                    by_age[band].append(n)
                    by_sex[sex].append(n)
                    by_region[region].append(n)
                    by_setting[setting].append(n)
                    by_loc[label].append(n)
            heat[condition][band] = round(float(np.mean(band_counts)), 1)

    loc_meta = {l[0]: {"lat": l[1], "lon": l[2], "setting": l[3], "region": l[4]} for l in AUDIT_LOCATIONS}
    locations = [{"label": k, **loc_meta[k], "mean_matches": round(float(np.mean(v)), 2)} for k, v in by_loc.items()]
    report = {
        "params": {"radius_mi": RADIUS_MI, "conditions": AUDIT_CONDITIONS, "ages": [a for a, _ in AGES],
                   "locations": len(AUDIT_LOCATIONS)},
        "by_age": _ratio_table(by_age),
        "by_sex": _ratio_table(by_sex),
        "by_region": _ratio_table(by_region),
        "by_setting": _ratio_table(by_setting),
        "heatmap": heat,
        "locations": sorted(locations, key=lambda d: -d["mean_matches"]),
        "age_caps": age_caps,
    }
    report["headline"] = _headline(report)
    execute(
        """INSERT INTO eval_reports (kind, report) VALUES ('fairness', %s)
           ON CONFLICT (kind) DO UPDATE SET report = EXCLUDED.report, created_at = now()""",
        (jsonb(report),),
    )
    return report


def _headline(r: Dict) -> List[str]:
    out = []
    ages = {d["group"]: d for d in r["by_age"]}
    young = max(r["by_age"], key=lambda d: d["mean_matches"])
    if "85+" in ages:
        out.append(f"Patients aged 85+ see {ages['85+']['mean_matches']:.1f} matches on average vs "
                   f"{young['mean_matches']:.1f} for {young['group']} ({ages['85+']['ratio']:.0%} of the best group).")
    setting = {d["group"]: d for d in r["by_setting"]}
    if "rural" in setting and "urban" in setting:
        out.append(f"Rural reference towns average {setting['rural']['mean_matches']:.1f} reachable trials within "
                   f"{int(r['params']['radius_mi'])} mi vs {setting['urban']['mean_matches']:.1f} in large cities.")
    worst_region = min(r["by_region"], key=lambda d: d["ratio"])
    out.append(f"Lowest region: {worst_region['group']} at {worst_region['ratio']:.0%} of the best-served region.")
    capped = sorted(r["age_caps"], key=lambda d: -d["pct_cap_under_75"])[0]
    out.append(f"{capped['pct_cap_under_75']:.0f}% of {capped['condition']} trials exclude people over 75.")
    return out
