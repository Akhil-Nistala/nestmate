"""
Form whole FLAT GROUPS (2-4 people) -- the hero feature.

WHY K-means alone is not enough:
  K-means cannot control cluster size. A persona cluster might have 40 people,
  but a flat needs exactly 2, 3 or 4. K-means also ignores hard rules (budget,
  dealbreakers, gender preference). So we use it to NARROW the search to people
  with similar lifestyles, then this step builds actual flats inside each cluster.

WHY greedy + swap pass (not an exact optimiser): exact group partitioning is
NP-hard. Greedy is fast, explainable in one sentence, and deterministic; the
swap pass recovers most of the quality lost by greedy choices.
"""
import itertools

import numpy as np

from core.encode import dealbreaker_list
from core.schema import TRAITS, WEIGHTS, TRAIT_RANGE, TRAIT_SHORT, QUESTIONS, violates_dealbreaker

MAX_SWAP_ITERS = 200
_W = np.array([WEIGHTS[t] for t in TRAITS])
_RANGE = np.array([TRAIT_RANGE[t][1] - TRAIT_RANGE[t][0] for t in TRAITS], dtype=float)


# ---------------------------------------------------------------------------
# 1. Pairwise compatibility
# ---------------------------------------------------------------------------
def conflict_reason(a, b):
    """Return why a and b can't live together, or None if compatible.
    a, b are dict-like profile rows."""
    if a["budget_min"] > b["budget_max"] or b["budget_min"] > a["budget_max"]:
        return "budget ranges don't overlap"
    if a["gender"] != b["gender"] and "same only" in (a["preferred_gender_mix"], b["preferred_gender_mix"]):
        return "gender preference"
    for me, other in ((a, b), (b, a)):
        for d in dealbreaker_list(me["dealbreakers"]):
            if violates_dealbreaker(d, me, other):
                return f"{me['name'].split()[0]}'s dealbreaker: {d}"
    return None


def pair_scores(df):
    """score = 100 * (1 - weighted normalised distance); 0 if incompatible.
    WHY normalise by range: a 1-step gap on a 3-option question is bigger than on
    a 5-option question. WHY a 0..100 score: easy for users and HR to read."""
    X = df[TRAITS].to_numpy(dtype=float)
    diff = np.abs(X[:, None, :] - X[None, :, :]) / _RANGE        # (n, n, traits) in 0..1
    dist = (diff * _W).sum(axis=2) / _W.sum()
    S = 100 * (1 - dist)

    rows = df.to_dict("records")
    n = len(rows)
    compat = np.ones((n, n), dtype=bool)
    for i in range(n):
        for j in range(i + 1, n):
            if conflict_reason(rows[i], rows[j]):
                compat[i, j] = compat[j, i] = False
    np.fill_diagonal(compat, False)
    S = np.where(compat, S, 0.0)
    return S, compat


def group_score(members, S):
    """Mean pairwise score of a group."""
    pairs = list(itertools.combinations(members, 2))
    return float(np.mean([S[i, j] for i, j in pairs])) if pairs else 0.0


def all_compatible(members, compat):
    return all(compat[i, j] for i, j in itertools.combinations(members, 2))


# ---------------------------------------------------------------------------
# 2-4. Group formation
# ---------------------------------------------------------------------------
def form_groups(df, labels):
    """Returns (groups, unmatched). Indices refer to df positions.
    Deterministic: no randomness, ties broken by row order."""
    S, compat = pair_scores(df)
    pref = df["flat_size_pref"].to_numpy()
    n = len(df)
    n_options = compat.sum(axis=1)

    groups = []  # each: {"members": [...], "target": int, "cluster": int (-1 = cross-persona)}
    leftovers = []

    # Step 2: greedy within each cluster AND same size preference.
    for c in sorted(set(labels)):
        for size in (2, 3, 4):
            pool = [i for i in range(n) if labels[i] == c and pref[i] == size]
            formed, left = _greedy(pool, size, S, compat, n_options)
            groups += [{"members": g, "target": size, "cluster": int(c)} for g in formed]
            leftovers += left

    # Step 3: improvement pass -- swap members between groups with the same target
    # size (so everyone's size preference stays satisfied).
    iters = 0
    improved = True
    while improved and iters < MAX_SWAP_ITERS:
        improved = False
        for a, b in itertools.combinations(range(len(groups)), 2):
            ga, gb = groups[a], groups[b]
            if ga["target"] != gb["target"]:
                continue
            before = group_score(ga["members"], S) + group_score(gb["members"], S)
            for x, y in itertools.product(ga["members"], gb["members"]):
                na = [y if m == x else m for m in ga["members"]]
                nb = [x if m == y else m for m in gb["members"]]
                if not (all_compatible(na, compat) and all_compatible(nb, compat)):
                    continue
                # Equal group sizes -> raising the pair's sum raises the overall average.
                if group_score(na, S) + group_score(nb, S) > before + 1e-9:
                    ga["members"], gb["members"] = na, nb
                    improved = True
                    iters += 1
                    break
            if iters >= MAX_SWAP_ITERS:
                break

    # Step 4a: leftovers -> best compatible group (any cluster) with an open spot.
    still_left = []
    for i in sorted(leftovers):
        options = [g for g in groups
                   if len(g["members"]) < g["target"] and g["target"] == pref[i]
                   and all(compat[i, m] for m in g["members"])]
        if options:
            best = max(options, key=lambda g: np.mean([S[i, m] for m in g["members"]]))
            best["members"].append(i)
        else:
            still_left.append(i)

    # Step 4b: leftovers -> new flats with EACH OTHER, across clusters. WHY: two
    # compatible people who both want a 2-person flat but landed in different
    # personas (or were each the odd one out in their cluster) should still be
    # matched; the persona split is only a search shortcut, not a hard rule.
    final_left = []
    for size in (2, 3, 4):
        pool = [i for i in still_left if pref[i] == size]
        formed, left = _greedy(pool, size, S, compat, n_options)
        groups += [{"members": g, "target": size, "cluster": -1} for g in formed]
        final_left += left

    # Reasons are computed last, so they reflect every group formed above.
    unmatched = [{"index": i, "reason": unmatched_reason(i, df, compat, groups, pref)} for i in sorted(final_left)]
    return groups, unmatched, S, compat


def _greedy(pool, size, S, compat, n_options):
    """Greedy flats of `size` from `pool`: seed with the hardest-to-place person
    (fewest compatible people, so they aren't left behind), then repeatedly add
    the compatible person with the best average score to the group so far.
    Returns (groups as member lists with >= 2 people, leftover indices)."""
    free = sorted(pool, key=lambda i: (n_options[i], i))
    groups, leftovers = [], []
    while free:
        seed = free.pop(0)
        g = [seed]
        while len(g) < size:
            cands = [j for j in free if all(compat[j, m] for m in g)]
            if not cands:
                break
            best = max(cands, key=lambda j: (np.mean([S[j, m] for m in g]), -j))
            g.append(best)
            free.remove(best)
        if len(g) >= 2:
            groups.append(g)
        else:
            leftovers.append(seed)
    return groups, leftovers


def unmatched_reason(i, df, compat, groups, pref):
    rows = df.to_dict("records")
    me = rows[i]
    if compat[i].sum() == 0:
        budget_ok = [j for j in range(len(rows)) if j != i
                     and not (me["budget_min"] > rows[j]["budget_max"] or rows[j]["budget_min"] > me["budget_max"])]
        if not budget_ok:
            return "no one in budget range"
        return "dealbreakers / gender preference rule out everyone in budget"
    return f"no compatible open spot in a {pref[i]}-person flat (try another flat size)"


# ---------------------------------------------------------------------------
# 5. Describe a group for the UI and the LLM
# ---------------------------------------------------------------------------
def _label(t, v):
    return QUESTIONS[t]["options"][int(v)]


def describe_group(members, df, S, personas, labels):
    rows = df.iloc[members].to_dict("records")
    X = df.iloc[members][TRAITS].to_numpy(dtype=float)
    spread = (X.max(axis=0) - X.min(axis=0)) / _RANGE  # 0 = everyone identical
    weighted = spread * _W

    # Matching = smallest spread, prefer important traits on ties.
    match_idx = sorted(range(len(TRAITS)), key=lambda k: (weighted[k], -_W[k]))[:2]
    matching = []
    for k in match_idx:
        t = TRAITS[k]
        vals = sorted({_label(t, v) for v in X[:, k]})
        matching.append({"trait": TRAIT_SHORT[t], "detail": f"everyone: {' / '.join(vals)}"})

    # Friction = largest weighted spread; name the odd one out.
    friction = []
    for k in sorted(range(len(TRAITS)), key=lambda k: -weighted[k])[:2]:
        if spread[k] == 0:
            continue
        t = TRAITS[k]
        col = X[:, k]
        med = np.median(col)
        odd = int(np.argmax(np.abs(col - med)))
        others = sorted({_label(t, v) for j, v in enumerate(col) if j != odd})
        friction.append({
            "trait": TRAIT_SHORT[t],
            "person": rows[odd]["name"].split()[0],
            "detail": f"{rows[odd]['name'].split()[0]}: {_label(t, col[odd])}; others: {' / '.join(others)}",
        })

    cluster_votes = [int(labels[m]) for m in members]
    main_cluster = max(set(cluster_votes), key=cluster_votes.count)
    return {
        "member_ids": [r["id"] for r in rows],
        "members": rows,
        "size": len(rows),
        "score": round(group_score(members, S), 1),
        "persona": personas[main_cluster]["name"],
        "budget": (int(max(r["budget_min"] for r in rows)), int(min(r["budget_max"] for r in rows))),
        "offices": sorted({r["office_location"] for r in rows}),
        "matching": matching,
        "friction": friction,
    }


def build_all(df, clustering):
    """Convenience wrapper used by the app: returns described groups + unmatched."""
    labels = clustering["labels"]
    groups, unmatched, S, compat = form_groups(df, labels)
    described = [describe_group(g["members"], df, S, clustering["personas"], labels) for g in groups]
    for d, g in zip(described, groups):
        d["target"] = g["target"]
    described.sort(key=lambda d: -d["score"])
    for n, d in enumerate(described, 1):
        d["group_id"] = f"G{n:02d}"
    unmatched_out = [{"id": df.iloc[u["index"]]["id"], "name": df.iloc[u["index"]]["name"],
                      "reason": u["reason"]} for u in unmatched]
    return {"groups": described, "unmatched": unmatched_out, "S": S, "compat": compat}


def alternative_groups(user_idx, df, S, compat, clustering, exclude_sets, size, k=2):
    """Extra suggestions for the 'swipe on groups' deck: seed with the user and
    greedily add best-average compatible people from the WHOLE cohort, avoiding
    people already shown, so each card is genuinely different."""
    pref = df["flat_size_pref"].to_numpy()
    shown = set().union(*exclude_sets) if exclude_sets else set()
    out = []
    for _ in range(k):
        g = [user_idx]
        while len(g) < size:
            cands = [j for j in range(len(df)) if j not in g and j not in shown
                     and pref[j] == size and all(compat[j, m] for m in g)]
            if not cands:
                break
            g.append(max(cands, key=lambda j: (np.mean([S[j, m] for m in g]), -j)))
        if len(g) < 2:
            break
        shown |= set(g) - {user_idx}
        d = describe_group(g, df, S, clustering["personas"], clustering["labels"])
        d["target"] = size
        out.append(d)
    return out


def user_deck(df, clustering, res, user_id):
    """The cards a user swipes through: their assigned group first, then alternatives.
    Shared by the app and the cache warm-up script so both see identical groups.
    Returns (deck, placed) where placed=False means the user is currently unmatched."""
    pos = int(df.index[df["id"] == user_id][0])  # load_cohort uses a 0..n-1 index
    mine = [g for g in res["groups"] if user_id in g["member_ids"]]
    exclude = [set(df.index[df["id"].isin(g["member_ids"])]) for g in mine]
    alts = alternative_groups(pos, df, res["S"], res["compat"], clustering, exclude,
                              int(df.iloc[pos]["flat_size_pref"]))
    return mine + alts, bool(mine)
