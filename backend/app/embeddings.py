"""Trial / query embeddings for semantic search and "trials like this one".

Two interchangeable 384-d providers:
  - fastembed (BAAI/bge-small-en-v1.5, ONNX) when the package is installed (Docker image)
  - LSA (TF-IDF -> truncated SVD) fitted on the trial corpus, needing only scikit-learn
"""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import List

import numpy as np

from .config import settings
from .db import connect, fetch_all, fetch_one, jsonb

log = logging.getLogger(__name__)
DIM = 384
_LSA_PATH = settings.artifacts_dir / "lsa.joblib"


def trial_document(t: dict) -> str:
    parts = [t.get("title") or "", " ".join(t.get("conditions") or []), " ".join(t.get("mesh_terms") or []),
             " ".join(t.get("keywords") or []), " ".join(i.get("name") or "" for i in t.get("interventions") or []),
             (t.get("summary") or "")[:1500]]
    return "\n".join(p for p in parts if p)


class _FastEmbed:
    name = "bge-small"

    def __init__(self) -> None:
        from fastembed import TextEmbedding  # type: ignore
        self.model = TextEmbedding("BAAI/bge-small-en-v1.5")

    def fit(self, docs: List[str]) -> None:
        pass

    def encode(self, texts: List[str]) -> np.ndarray:
        return np.array(list(self.model.embed(texts)), dtype=np.float32)


class _LSA:
    name = "lsa"

    def __init__(self) -> None:
        self.pipe = None
        self._mtime = 0.0
        self._maybe_reload()

    def _maybe_reload(self) -> None:
        # the worker may (re)fit the model after this process started
        if _LSA_PATH.exists() and _LSA_PATH.stat().st_mtime != self._mtime:
            import joblib
            self.pipe = joblib.load(_LSA_PATH)
            self._mtime = _LSA_PATH.stat().st_mtime

    def fit(self, docs: List[str]) -> None:
        import joblib
        from sklearn.decomposition import TruncatedSVD
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import Normalizer

        n = min(DIM, max(2, len(docs) - 1))
        self.pipe = make_pipeline(
            TfidfVectorizer(sublinear_tf=True, ngram_range=(1, 2), min_df=2, max_df=0.6, stop_words="english"),
            TruncatedSVD(n_components=n, random_state=7),
            Normalizer(copy=False),
        )
        self.pipe.fit(docs)
        settings.artifacts_dir.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.pipe, _LSA_PATH)
        self._mtime = _LSA_PATH.stat().st_mtime

    def encode(self, texts: List[str]) -> np.ndarray:
        self._maybe_reload()
        if self.pipe is None:
            raise RuntimeError("LSA model not fitted; run `python -m scripts.cli embed`")
        v = self.pipe.transform(texts).astype(np.float32)
        if v.shape[1] < DIM:
            v = np.pad(v, ((0, 0), (0, DIM - v.shape[1])))
        return v


@lru_cache(maxsize=1)
def provider():
    if settings.embedding_provider in ("auto", "fastembed"):
        try:
            return _FastEmbed()
        except Exception as exc:  # ImportError or model download failure
            if settings.embedding_provider == "fastembed":
                raise
            log.info("fastembed unavailable (%s); using LSA embeddings", type(exc).__name__)
    return _LSA()


def encode(texts: List[str]) -> np.ndarray:
    return provider().encode(texts)


def embed_all_trials() -> int:
    rows = fetch_all("SELECT nct_id, title, conditions, mesh_terms, keywords, interventions, summary FROM trials")
    if not rows:
        return 0
    docs = [trial_document(r) for r in rows]
    p = provider()
    p.fit(docs)
    vecs = np.vstack([p.encode(docs[i:i + 256]) for i in range(0, len(docs), 256)])
    with connect() as conn, conn.cursor() as cur:
        for r, v in zip(rows, vecs):
            cur.execute("UPDATE trials SET embedding = %s WHERE nct_id = %s", (v, r["nct_id"]))
        # record which model produced the stored vectors so queries never mix spaces
        cur.execute(
            """INSERT INTO eval_reports (kind, report) VALUES ('embedding', %s)
               ON CONFLICT (kind) DO UPDATE SET report = EXCLUDED.report, created_at = now()""",
            (jsonb({"provider": p.name, "trials": len(rows)}),),
        )
    return len(rows)


def stored_provider() -> str:
    row = fetch_one("SELECT report->>'provider' AS p FROM eval_reports WHERE kind = 'embedding'")
    return row["p"] if row else ""
