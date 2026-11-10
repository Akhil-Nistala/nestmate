"""
Discover lifestyle personas in a joining cohort with K-means.

Pipeline: answers -> StandardScaler -> multiply by sqrt(weight) -> KMeans -> PCA(2D)

WHY this order matters:
  1. StandardScaler first puts every trait on the same footing (a 1..5 trait and
     a 1..3 trait would otherwise contribute unequally just because of range).
  2. THEN we multiply by sqrt(weight). K-means uses squared Euclidean distance,
     so scaling a column by sqrt(w) makes its contribution to distance exactly
     w * diff^2. If we weighted before scaling, StandardScaler would undo it.
"""
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

from core.encode import to_matrix
from core.schema import TRAITS, WEIGHTS, QUESTIONS

K_RANGE = range(3, 9)
RANDOM_STATE = 42  # fixed seed -> same personas every demo run

# Readable labels for "low" and "high" ends of each trait, used to auto-name personas.
TRAIT_POLES = {
    "sleep_time": ("Early sleeper", "Night-owl"),
    "wake_time": ("Early riser", "Late riser"),
    "cleanliness": ("Easy-going about mess", "Neat"),
    "noise_tolerance": ("Quiet-seeker", "Noise-tolerant"),
    "guests_frequency": ("Private", "Host"),
    "food": ("Veg", "Non-veg"),
    "cooking": ("Orders in", "Home cook"),
    "smoking": ("Smoke-free", "Smoke-tolerant"),
    "drinking": ("Teetotal", "Social drinker"),
    "work_mode": ("Office-goer", "WFH"),
    "social_level": ("Reserved", "Social"),
}


def weighted_features(df):
    """Return (scaled+weighted matrix, unweighted z-scores)."""
    X = to_matrix(df)
    Z = StandardScaler().fit_transform(X)
    w = np.sqrt(np.array([WEIGHTS[t] for t in TRAITS]))
    return Z * w, Z


def choose_k(Xw):
    """Silhouette for k=3..8. WHY silhouette: it rewards tight, well-separated
    clusters without needing ground-truth labels, which we won't have in production."""
    scores = {}
    for k in K_RANGE:
        labels = KMeans(n_clusters=k, n_init=10, random_state=RANDOM_STATE).fit_predict(Xw)
        scores[k] = float(silhouette_score(Xw, labels))
    best_k = max(scores, key=scores.get)
    return best_k, scores


def name_persona(z_centroid, used):
    """Name a cluster from its 2 most extreme traits vs the cohort mean (z=0)."""
    order = np.argsort(-np.abs(z_centroid))
    if abs(z_centroid[order[0]]) < 0.4:
        # nothing stands out -> it's the middle-of-the-road group
        name = "Easygoing · Balanced"
    else:
        parts = []
        for idx in order:
            t = TRAITS[idx]
            parts.append(TRAIT_POLES[t][1] if z_centroid[idx] > 0 else TRAIT_POLES[t][0])
            if len(parts) >= 2 and " · ".join(parts) not in used:
                break
        name = " · ".join(parts)
    while name in used:  # guarantee unique names
        name += "+"
    return name


def describe_persona(raw_centroid, z_centroid):
    """One-line description using the 3 most distinctive traits in human labels."""
    bits = []
    for idx in np.argsort(-np.abs(z_centroid))[:3]:
        t = TRAITS[idx]
        val = int(round(raw_centroid[idx]))
        bits.append(f"{QUESTIONS[t]['label'].rstrip('?').lower()}: {QUESTIONS[t]['options'][val]}")
    return "Typically — " + "; ".join(bits) + "."


def run_clustering(df):
    """Full pipeline. Returns a dict the UI and grouping step can use directly."""
    Xw, Z = weighted_features(df)
    best_k, scores = choose_k(Xw)
    km = KMeans(n_clusters=best_k, n_init=10, random_state=RANDOM_STATE).fit(Xw)
    labels = km.labels_

    raw = to_matrix(df)
    personas = {}
    used = set()
    for c in range(best_k):
        mask = labels == c
        zc = Z[mask].mean(axis=0)
        name = name_persona(zc, used)
        used.add(name)
        personas[c] = {
            "name": name,
            "size": int(mask.sum()),
            "description": describe_persona(raw[mask].mean(axis=0), zc),
            "centroid": dict(zip(TRAITS, np.round(raw[mask].mean(axis=0), 2))),
        }

    # PCA only for visualisation; clustering itself uses all 11 dimensions.
    pca = PCA(n_components=2, random_state=RANDOM_STATE)
    coords = pca.fit_transform(Xw)

    out = df[["id", "name"]].copy()
    out["cluster"] = labels
    out["persona"] = [personas[c]["name"] for c in labels]
    out["pc1"], out["pc2"] = coords[:, 0], coords[:, 1]
    return {
        "labels": labels,
        "best_k": best_k,
        "silhouette_scores": scores,
        "silhouette": scores[best_k],
        "personas": personas,
        "points": out,
        "pca_variance": pca.explained_variance_ratio_.tolist(),
    }
