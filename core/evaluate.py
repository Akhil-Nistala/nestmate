"""
Sanity tests and metrics. Run:  python -m core.evaluate

WHY: "the clusters look nice" isn't evidence. These checks show the panel that
(1) clustering recovers the hidden archetypes (ARI), (2) no formed group breaks a
hard rule, (3) results are deterministic, and (4) grouping beats random flats.

WHY the main baseline obeys the hard rules: an incompatible pair scores 0, so
fully random flats are dragged down by budget/dealbreaker/gender clashes. That
would credit the RULES, not the lifestyle matching, for most of the gap. The
fair question is "do our flats fit better than random flats that are equally
legal?", so the baseline builds random flats under the same rules. The fully
random number is kept alongside it for reference.
"""
import itertools

import numpy as np
from sklearn.metrics import adjusted_rand_score

from core.cluster import run_clustering
from core.encode import load_cohort
from core.grouping import build_all, conflict_reason, group_score

BASELINE_RUNS = 20  # averaged so one lucky/unlucky shuffle can't swing the number


def random_valid_baseline(sizes, S, compat, runs=BASELINE_RUNS, seed=0):
    """Mean group score of random flats with the same sizes as ours that break no
    hard rule. Each run shuffles the cohort, then fills each flat (largest first)
    with the next people in shuffled order who are compatible with everyone
    already in it. Returns (mean score, share of flats that could be filled)."""
    rng = np.random.default_rng(seed)
    n = len(S)
    run_means, filled = [], 0
    for _ in range(runs):
        free = list(rng.permutation(n))
        scores = []
        for size in sorted(sizes, reverse=True):
            g = []
            for j in free:
                if all(compat[j, m] for m in g):
                    g.append(j)
                    if len(g) == size:
                        break
            if len(g) < size:
                continue  # no legal flat of this size left in this shuffle
            for j in g:
                free.remove(j)
            scores.append(group_score(g, S))
        filled += len(scores)
        run_means.append(np.mean(scores) if scores else 0.0)
    return float(np.mean(run_means)), filled / (runs * len(sizes))


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

    # (4) Quality vs a rule-respecting random baseline with the same group sizes.
    placed = sum(g["size"] for g in groups)
    metrics["groups_formed"] = len(groups)
    metrics["people_placed_pct"] = round(100 * placed / len(df), 1)
    metrics["unmatched"] = len(res["unmatched"])
    metrics["mean_group_score"] = round(float(np.mean([g["score"] for g in groups])), 1)

    sizes = [g["size"] for g in groups]
    base, fill = random_valid_baseline(sizes, S, res["compat"])
    metrics["random_baseline_score"] = round(base, 1)  # random flats, same sizes, no rule broken
    metrics["random_baseline_filled_pct"] = round(100 * fill, 1)

    # Reference only: fully random flats, rules ignored (incompatible pairs score 0).
    rng = np.random.default_rng(0)
    idx = rng.permutation(len(df))
    rand_scores, pos = [], 0
    for size in sizes:
        rand_scores.append(group_score(list(idx[pos:pos + size]), S))
        pos += size
    metrics["random_ignoring_rules_score"] = round(float(np.mean(rand_scores)), 1)
    return metrics


if __name__ == "__main__":
    for k, v in evaluate().items():
        print(f"{k:28s} {v}")
