"""Loads the trained ranker (if present) and scores feature rows."""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Dict, List, Optional

import numpy as np

from ..config import settings
from .features import FEATURES

log = logging.getLogger(__name__)
MODEL_PATH = settings.artifacts_dir / "ranker.joblib"


@lru_cache(maxsize=1)
def load() -> Optional[dict]:
    if not MODEL_PATH.exists():
        return None
    import joblib
    bundle = joblib.load(MODEL_PATH)
    if bundle.get("features") != FEATURES:
        log.warning("ranker feature set changed; retrain with `python -m scripts.cli train`")
        return None
    return bundle


def reload() -> None:
    load.cache_clear()


def matrix(rows: List[Dict[str, float]]) -> np.ndarray:
    return np.array([[r[f] for f in FEATURES] for r in rows], dtype=np.float32)


def predict(rows: List[Dict[str, float]]) -> Optional[np.ndarray]:
    bundle = load()
    if bundle is None or not rows:
        return None
    return bundle["model"].predict(matrix(rows))
