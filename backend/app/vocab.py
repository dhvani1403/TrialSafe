"""Shared eligibility concept vocabulary.

Every parser (rules or LLM) maps a criterion line onto these concept ids, and the
matcher knows how to evaluate each concept against a patient profile. Keeping a
single vocabulary is what makes parser outputs comparable in the evaluation.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Pattern

# kind of value a concept carries
BOOL = "bool"
NUM = "num"


@dataclass(frozen=True)
class Concept:
    id: str
    label: str
    category: str
    kind: str
    patterns: List[str]
    # profile attribute this concept is evaluated against; None = not assessable from a profile
    profile_field: Optional[str] = None
    unit: Optional[str] = None
    description: str = ""
    compiled: List[Pattern] = field(default_factory=list, compare=False, hash=False)


CATEGORIES = {
    "demographic": "Age & demographics",
    "diagnosis": "Diagnosis & disease stage",
    "performance": "Performance status",
    "reproductive": "Pregnancy & reproduction",
    "comorbidity": "Other health conditions",
    "prior_therapy": "Treatment history",
    "medication": "Current medications",
    "lifestyle": "Lifestyle & body measures",
    "lab": "Lab values (needs your care team)",
    "administrative": "Study logistics",
}

_C = [
    # demographic
    Concept("age", "Age", "demographic", NUM,
            [r"\bage[sd]?\b", r"\byears? (?:of age|old)\b", r"\b(?:≥|>=|>|\\>)\s*\d{2}\s*years\b"],
            "age", "years", "Age limits written in the criteria text."),
    # diagnosis
    Concept("diagnosis", "Confirmed diagnosis", "diagnosis", BOOL,
            [r"\bdiagnos(?:is|ed)\b", r"\bhistologically\b", r"\bcytologically\b", r"\bconfirmed\b.*\b(?:cancer|carcinoma|disease|disorder)\b"],
            "condition_match", None, "A required diagnosis of the study's condition."),
    Concept("metastatic", "Metastatic (stage IV) disease", "diagnosis", BOOL,
            [r"\bmetasta(?:tic|ses|sis)\b(?!.*\b(?:brain|cns|central nervous|leptomeningeal)\b)", r"\bstage\s*(?:iv|4)\b"],
            "metastatic", None, "Cancer that has spread / stage IV."),
    Concept("brain_metastases", "Brain / CNS metastases", "diagnosis", BOOL,
            [r"\b(?:brain|cns|central nervous system|leptomeningeal)\b[^.;]{0,30}\bmetasta", r"\bleptomeningeal\b"],
            "brain_metastases", None, "Cancer that has spread to the brain or spinal cord."),
    Concept("measurable_disease", "Measurable tumor (RECIST)", "diagnosis", BOOL,
            [r"\bmeasurable disease\b", r"\brecist\b", r"\bmeasurable lesion"],
            None, None, "Tumour measurable on imaging; your oncologist can confirm."),
    # performance
    Concept("ecog", "ECOG performance status", "performance", NUM,
            [r"\becog\b", r"\beastern cooperative oncology group\b", r"\b(?:who|zubrod) performance status\b"],
            "ecog", "score", "0 = fully active ... 4 = completely disabled."),
    Concept("karnofsky", "Karnofsky performance status", "performance", NUM,
            [r"\bkarnofsky\b", r"\bkps\b", r"\blansky\b"],
            "ecog", "%", "Karnofsky 100 = normal activity; mapped from ECOG."),
    Concept("life_expectancy", "Life expectancy", "performance", NUM,
            [r"\blife expectancy\b"], None, "months", "Clinician estimate; not assessable from a profile."),
    # reproductive
    Concept("pregnancy", "Pregnancy", "reproductive", BOOL,
            [r"\bpregnan(?:t|cy|cies)\b"], "pregnant", None, "Currently pregnant."),
    Concept("breastfeeding", "Breastfeeding", "reproductive", BOOL,
            [r"\bbreast[- ]?feeding\b", r"\blactating\b", r"\bnursing\b"], "breastfeeding", None, "Currently breastfeeding."),
    Concept("contraception", "Contraception requirement", "reproductive", BOOL,
            [r"\bcontracepti", r"\bbirth control\b", r"\babstinen"], None, None, "Agreement to use birth control during the study."),
    # comorbidities
    Concept("hiv", "HIV", "comorbidity", BOOL,
            [r"\bhiv\b", r"\bhuman immunodeficiency virus\b", r"\baids\b"], "hiv"),
    Concept("hepatitis", "Hepatitis B or C", "comorbidity", BOOL,
            [r"\bhepatitis\s*(?:b|c)\b", r"\bhbv\b", r"\bhcv\b", r"\bhbsag\b"], "hepatitis"),
    Concept("heart_disease", "Heart disease", "comorbidity", BOOL,
            [r"\bmyocardial infarction\b", r"\bheart (?:failure|disease|attack)\b", r"\bnyha\b", r"\bunstable angina\b",
             r"\b(?:cardiac|cardiovascular|coronary) (?:disease|event|arrhythmia)", r"\barrhythmia\b", r"\bqtc\b"],
            "heart_disease"),
    Concept("stroke", "Stroke", "comorbidity", BOOL,
            [r"\bstroke\b", r"\bcerebrovascular\b", r"\btransient ischemic attack\b", r"\btia\b"], "stroke"),
    Concept("diabetes", "Diabetes", "comorbidity", BOOL,
            [r"\bdiabet(?:es|ic)\b", r"\bt[12]dm?\b"], "diabetes"),
    Concept("kidney_disease", "Kidney disease", "comorbidity", BOOL,
            [r"\brenal (?:impairment|insufficiency|failure|disease)\b", r"\bkidney disease\b", r"\bdialysis\b",
             r"\besrd\b", r"\bend[- ]stage renal\b"], "kidney_disease"),
    Concept("liver_disease", "Liver disease", "comorbidity", BOOL,
            [r"\bcirrhosis\b", r"\bhepatic (?:impairment|insufficiency|disease|failure)\b", r"\bliver disease\b"],
            "liver_disease"),
    Concept("autoimmune_disease", "Autoimmune disease", "comorbidity", BOOL,
            [r"\bautoimmune\b", r"\blupus\b", r"\binflammatory bowel disease\b"], "autoimmune_disease"),
    Concept("active_infection", "Active infection", "comorbidity", BOOL,
            [r"\b(?:active|uncontrolled|serious|systemic) (?:\w+ )?infection", r"\btuberculosis\b"], "active_infection"),
    Concept("other_malignancy", "Another cancer", "comorbidity", BOOL,
            [r"\b(?:other|another|prior|previous|second|additional|concurrent) (?:\w+ )?(?:malignan\w*|cancer|primary)\b(?!\s*(?:therap|treatment|drug|agent|regimen|directed|site))",
             r"\bhistory of (?:\w+ )?malignan"], "other_malignancy"),
    Concept("seizure", "Seizures / epilepsy", "comorbidity", BOOL,
            [r"\bseizures?\b", r"\bepilep"], "seizure"),
    Concept("psychiatric", "Serious psychiatric illness", "comorbidity", BOOL,
            [r"\bpsychiatric\b", r"\bschizophreni", r"\bbipolar\b", r"\bsuicid", r"\bpsychosis\b"], "psychiatric"),
    Concept("substance_use", "Alcohol or drug misuse", "comorbidity", BOOL,
            [r"\b(?:alcohol|drug|substance) (?:abuse|use disorder|dependence|misuse)", r"\billicit drug"], "substance_use"),
    Concept("transplant", "Organ or stem cell transplant", "comorbidity", BOOL,
            [r"\b(?:organ|allogeneic|solid organ|stem cell|bone marrow) transplant", r"\btransplant recipient"], "transplant"),
    # prior therapy
    Concept("prior_chemotherapy", "Prior chemotherapy", "prior_therapy", BOOL,
            [r"\bchemotherap", r"\bcytotoxic\b", r"\bplatinum\b"], "chemotherapy"),
    Concept("prior_immunotherapy", "Prior immunotherapy", "prior_therapy", BOOL,
            [r"\bimmunotherap", r"\bcheckpoint inhibitor", r"\banti[- ]?(?:pd-?1|pd-?l1|ctla-?4)\b", r"\bpd-?(?:l)?1\b",
             r"\bpembrolizumab\b", r"\bnivolumab\b", r"\batezolizumab\b", r"\bcar[- ]?t\b"], "immunotherapy"),
    Concept("prior_radiation", "Prior radiation", "prior_therapy", BOOL,
            [r"\bradiotherap", r"\bradiation\b", r"\birradiation\b"], "radiation"),
    Concept("prior_surgery", "Recent or planned surgery", "prior_therapy", BOOL,
            [r"\bsurgery\b", r"\bsurgical\b", r"\bresection\b"], "surgery"),
    Concept("prior_targeted_therapy", "Prior targeted therapy", "prior_therapy", BOOL,
            [r"\btyrosine kinase inhibitor", r"\btki\b", r"\bcdk ?4/6\b", r"\bparp inhibitor", r"\btargeted therap",
             r"\begfr inhibitor"], "targeted_therapy"),
    Concept("prior_hormone_therapy", "Prior hormone therapy", "prior_therapy", BOOL,
            [r"\b(?:endocrine|hormon(?:e|al)) therap", r"\bandrogen deprivation\b", r"\badt\b", r"\btamoxifen\b",
             r"\baromatase inhibitor"], "hormone_therapy"),
    # medications
    Concept("insulin", "Insulin use", "medication", BOOL,
            [r"\binsulin\b"], "insulin"),
    Concept("anticoagulant", "Blood thinners", "medication", BOOL,
            [r"\banticoagula", r"\bwarfarin\b", r"\bblood thinner"], "anticoagulant"),
    Concept("steroids", "Steroids / immunosuppressants", "medication", BOOL,
            [r"\b(?:systemic )?corticosteroid", r"\bsteroids?\b", r"\bimmunosuppress", r"\bprednisone\b"], "steroids"),
    Concept("investigational_drug", "In another clinical trial", "medication", BOOL,
            [r"\binvestigational (?:agent|drug|product|device|therapy)", r"\b(?:another|other) (?:clinical|interventional) (?:trial|study)",
             r"\bparticipat\w* in (?:a|an|any) (?:\w+ )?(?:clinical )?(?:trial|study)"], "in_other_trial"),
    # lifestyle / measures
    Concept("smoking", "Smoking", "lifestyle", BOOL,
            [r"\bsmok(?:e|er|ers|ing|es)\b", r"\btobacco\b", r"\bcigarette", r"\bnicotine\b"], "smoker"),
    Concept("bmi", "Body mass index", "lifestyle", NUM,
            [r"\bbmi\b", r"\bbody mass index\b"], "bmi", "kg/m²"),
    Concept("hba1c", "HbA1c", "lab", NUM,
            [r"\bhba1c\b", r"\ba1c\b", r"\bhemoglobin a1c\b", r"\bglycated ha?emoglobin\b"], "hba1c", "%"),
    Concept("egfr_lab", "Kidney function (eGFR)", "lab", NUM,
            [r"\begfr\b(?![^.;]{0,40}\b(?:mutation|mutant|mutated|inhibitor|tki|exon|positive|negative|amplif|activating|altera|wild))", r"\bglomerular filtration\b",
             r"\bcreatinine clearance\b"], "egfr", "mL/min/1.73m²"),
    Concept("lab_values", "Blood counts / organ function labs", "lab", BOOL,
            [r"\badequate (?:organ|bone marrow|hematologic|hepatic|renal) function", r"\banc\b", r"\bneutrophil",
             r"\bplatelet", r"\bha?emoglobin\b(?! a1c)", r"\bbilirubin\b", r"\b(?:ast|alt)\b", r"\buln\b"],
            None, None, "Lab thresholds your care team checks at screening."),
    # administrative
    Concept("informed_consent", "Able to give consent", "administrative", BOOL,
            [r"\binformed consent\b", r"\bwilling (?:and|&) able\b", r"\bable to (?:understand|comply)\b", r"\bcomply with\b"],
            None, None, "Willing to sign consent and follow the study schedule."),
]

CONCEPTS: Dict[str, Concept] = {}
for c in _C:
    object.__setattr__(c, "compiled", [re.compile(p, re.I) for p in c.patterns])
    CONCEPTS[c.id] = c

CONCEPT_IDS = list(CONCEPTS) + ["other"]

# Patient-facing checklist options (shown in the intake form).
COMORBIDITY_OPTIONS = [
    "diabetes", "heart_disease", "stroke", "kidney_disease", "liver_disease", "hiv", "hepatitis",
    "autoimmune_disease", "active_infection", "other_malignancy", "seizure", "psychiatric",
    "substance_use", "transplant",
]
TREATMENT_OPTIONS = [
    "chemotherapy", "immunotherapy", "radiation", "surgery", "targeted_therapy", "hormone_therapy",
]
MEDICATION_OPTIONS = ["insulin", "anticoagulant", "steroids"]


def concept_catalog() -> List[dict]:
    return [
        {"id": c.id, "label": c.label, "category": c.category, "kind": c.kind,
         "assessable": c.profile_field is not None, "unit": c.unit, "description": c.description}
        for c in CONCEPTS.values()
    ]
