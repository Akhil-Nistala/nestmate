"""
Sanity tests and metrics. Run:  python -m core.evaluate

WHY: "the clusters look nice" isn't evidence. These checks show the panel that
(1) clustering recovers the hidden archetypes (ARI), (2) no formed group breaks a
hard rule, (3) results are deterministic, and (4) grouping beats random flats.
"""
import itertools

import numpy as np
from sklearn.metrics import adjusted_rand_score

from core.cluster import run_clustering
from core.encode import load_cohort
from core.grouping import build_all, conflict_reason, group_score


def evaluate(df=None):
    df = load_cohort() if df is None else df
    cl = run_clustering(df)
    res = build_all(df, cl)
    groups, S = res["groups"], res["S"]

    metrics = {
        "cohort_size": len(df),
        "best_k": cl["best_k"],
        "silhouette": round(cl["silhouette"], 3),
    }

    # (1) Archetype recovery -- only for synthetic rows that have the hidden label.
    has_truth = df["_true_archetype"].astype(str) != ""
    if has_truth.any():
        metrics["ARI_vs_hidden_archetypes"] = round(
            adjusted_rand_score(df.loc[has_truth, "_true_archetype"], cl["labels"][has_truth.to_numpy()]), 3)

    # (2) Hard-rule check: every pair inside every group must be compatible.
    violations = 0
    for g in groups:
        for a, b in itertools.combinations(g["members"], 2):
            if conflict_reason(a, b):
                violations += 1
    metrics["rule_violations_in_groups"] = violations

    # (3) Determinism: run again, compare.
    res2 = build_all(df, run_clustering(df))
    metrics["deterministic"] = [g["member_ids"] for g in groups] == [g["member_ids"] for g in res2["groups"]]

    # (4) Quality vs a random baseline with the same group sizes.
    placed = sum(g["size"] for g in groups)
    metrics["groups_formed"] = len(groups)
    metrics["people_placed_pct"] = round(100 * placed / len(df), 1)
    metrics["unmatched"] = len(res["unmatched"])
    metrics["mean_group_score"] = round(float(np.mean([g["score"] for g in groups])), 1)

    rng = np.random.default_rng(0)
    idx = rng.permutation(len(df))
    rand_scores, pos = [], 0
    for g in groups:
        members = list(idx[pos:pos + g["size"]])
        pos += g["size"]
        rand_scores.append(group_score(members, S))
    metrics["random_baseline_score"] = round(float(np.mean(rand_scores)), 1)
    return metrics


if __name__ == "__main__":
    for k, v in evaluate().items():
        print(f"{k:28s} {v}")
