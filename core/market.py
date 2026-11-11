"""
Fit scores and checks for the marketplace (flats, rooms, groups, flags).

Pure functions: no Streamlit, no file access. Pages pass in the cohort, the
matching results and the store rows, so everything here is unit-testable.

WHY no second scoring engine: every person-to-person number is the existing
pair score from core/grouping.pair_scores, and every group number is
describe_group/group_score. This module only decides WHICH people to compare
(a seeker and the people already living in a flat, a group and a flat) and
adds the practical side (rent and commute) where no people are involved.

Residents who aren't in the cohort (a landlord who lives in, a flatmate who
isn't on Nestmate) count once the lister has described their habits on the
listing form. WHY the same formula: a described housemate is turned into a
profile row and scored by grouping.pair_scores, so their numbers mean exactly
what a cohort member's do. They never block on budget or gender preference
(they already live there); seekers' dealbreakers still apply to them.

Score meanings, so the UI can say what a number is:
  "people"    - lifestyle fit with the people you'd live with (pair scores)
  "group"     - group score of everyone who'd live there
  "practical" - rent and commute fit, for a flat with nobody living in it yet
"""
import itertools
from collections import defaultdict

import numpy as np
import pandas as pd

from core.grouping import conflict_reason, describe_group, pair_scores
from core.schema import (AREAS, MAX_ACTIVE_LISTINGS, MIN_SHOWN_FIT, QUESTION_UI, SCAM_DISCOUNT, TRAIT_RANGE,
                         TRAIT_SHORT, TRAITS, WEIGHTS)

AREA = {a["area"]: a for a in AREAS}
_W = np.array([WEIGHTS[t] for t in TRAITS])
_RANGE = np.array([TRAIT_RANGE[t][1] - TRAIT_RANGE[t][0] for t in TRAITS], dtype=float)


# ---------------------------------------------------------------------------
# Context: the cohort and its matching results, indexed by member id
# ---------------------------------------------------------------------------
# Columns a profile needs for pair scoring and describe_group.
PROFILE_COLS = ["id", "name", "gender", "budget_min", "budget_max", "preferred_gender_mix", "dealbreakers",
                "priorities", "office_location", "organisation"] + TRAITS


def described_profile(p):
    """A people-store row with lister-described habits -> a scoreable profile row.
    Wide budget and "any" gender mix: they already live there, so only habits and
    the seeker's dealbreakers matter."""
    a = p.get("answers") or {}
    if not all(t in a for t in TRAITS):
        return None
    return {"id": p["id"], "name": p["name"], "gender": p.get("gender", ""), "budget_min": 0,
            "budget_max": 10 ** 9, "preferred_gender_mix": "any", "dealbreakers": "", "priorities": "",
            "office_location": "", "organisation": "", "described_by": p.get("described_by"),
            **{t: int(a[t]) for t in TRAITS}}


def make_ctx(df, clustering, res, people=()):
    cohort_ids = set(df["id"])
    described = {}
    for p in people:
        row = described_profile(p)
        if row and p["id"] not in cohort_ids:
            described[p["id"]] = row
    return {"df": df, "S": res["S"], "compat": res["compat"], "cl": clustering,
            "pos": {pid: i for i, pid in enumerate(df["id"])}, "rows": df.set_index("id", drop=False),
            "described": described}


def in_cohort(ctx, pid):
    return pid in ctx["pos"]


def known(ctx, pid):
    """Has habit answers we can score: a cohort member or a described resident."""
    return in_cohort(ctx, pid) or pid in ctx.get("described", {})


def is_described(ctx, pid):
    return not in_cohort(ctx, pid) and pid in ctx.get("described", {})


def person(ctx, pid):
    return ctx["rows"].loc[pid].to_dict() if in_cohort(ctx, pid) else None


def profile(ctx, pid):
    """Cohort row, or a described resident's profile, or None."""
    if in_cohort(ctx, pid):
        return person(ctx, pid)
    d = ctx.get("described", {}).get(pid)
    return dict(d) if d else None


def _profiles_df(ctx, ids):
    rows = [profile(ctx, i) for i in ids]
    return pd.DataFrame([{c: r.get(c, "") for c in PROFILE_COLS} for r in rows])


def pair(ctx, a, b):
    """(score 0..100, compatible) for two people with answers; (None, True) if either has none.
    Two cohort members use the precomputed matrix; anyone described is scored with
    the same pair_scores formula on the fly."""
    if in_cohort(ctx, a) and in_cohort(ctx, b):
        i, j = ctx["pos"][a], ctx["pos"][b]
        return float(ctx["S"][i, j]), bool(ctx["compat"][i, j])
    if not (known(ctx, a) and known(ctx, b)):
        return None, True
    S, compat = pair_scores(_profiles_df(ctx, [a, b]))
    return float(S[0, 1]), bool(compat[0, 1])


def fit_together(ctx, ids):
    """(all compatible, mean pair score) for people with answers; unknown ids are skipped."""
    ids = [i for i in dict.fromkeys(ids) if known(ctx, i)]
    pairs = [pair(ctx, a, b) for a, b in itertools.combinations(ids, 2)]
    if not pairs:
        return True, None
    return all(ok for _, ok in pairs), float(np.mean([s for s, _ in pairs]))


def biggest_difference(ctx, a, b):
    """The trait two people differ on most (weighted), as (trait key, a's answer, b's answer)."""
    pa, pb = profile(ctx, a), profile(ctx, b)
    gaps = [abs(pa[t] - pb[t]) / _RANGE[k] * _W[k] for k, t in enumerate(TRAITS)]
    k = int(np.argmax(gaps))
    if gaps[k] == 0:
        return None
    t = TRAITS[k]
    return t, QUESTION_UI[t]["choices"][int(pa[t])], QUESTION_UI[t]["choices"][int(pb[t])]


def describe(ctx, member_ids):
    """describe_group for any list of people with answers (order kept): cohort
    members and described residents. Others are skipped."""
    ids = [m for m in dict.fromkeys(member_ids) if known(ctx, m)]
    if all(in_cohort(ctx, m) for m in ids):
        idx = [ctx["pos"][m] for m in ids]
        d = describe_group(idx, ctx["df"], ctx["S"], ctx["cl"]["personas"], ctx["cl"]["labels"])
    else:
        # WHY a small local table: described residents aren't in the cohort matrix.
        # They get no persona vote; the flat's persona comes from cohort members.
        df = _profiles_df(ctx, ids)
        S, _ = pair_scores(df)
        votes = [int(ctx["cl"]["labels"][ctx["pos"][m]]) for m in ids if in_cohort(ctx, m)]
        fallback = max(set(votes), key=votes.count) if votes else 0
        labels = [int(ctx["cl"]["labels"][ctx["pos"][m]]) if in_cohort(ctx, m) else fallback for m in ids]
        d = describe_group(list(range(len(ids))), df, S, ctx["cl"]["personas"], labels)
        d["offices"] = [o for o in d["offices"] if o]
    d["target"] = len(ids)
    return d


# ---------------------------------------------------------------------------
# Listings: basics
# ---------------------------------------------------------------------------
def area_rent(area):
    return AREA[area]["rent"]


def commute(area, office):
    return AREA[area]["commute"].get(office) if area in AREA else None


def free_rooms(listing):
    return [r for r in listing["rooms"] if not r.get("occupied_by")]


def is_live(listing):
    return listing["status"] == "approved"


def is_active(listing):
    return listing["status"] in ("pending", "approved")


def residents(listing):
    """People already living there (occupants), including an owner who lives in."""
    return list(dict.fromkeys(listing.get("occupants", [])))


def listing_blocks(listing, p):
    """Why `p` can't live in this listing under its house rules, or None.
    Same style as violates_dealbreaker: the rules belong to the flat and are
    checked against the person's answers. Missing answers never block."""
    rules = listing["rules"]
    g = rules.get("gender", "any")
    if g != "any" and str(p.get("gender", "")).lower() != g:
        return "men only" if g == "male" else "women only"

    def ans(t):
        v = p.get(t)
        return None if v is None or v != v else int(v)  # v != v: NaN

    if rules.get("veg_only") and ans("food") == 3:
        return "veg-only kitchen"
    if rules.get("no_smoking") and ans("smoking") == 3:
        return "no smoking"
    if rules.get("no_drinking") and (ans("drinking") or 0) >= 3:
        return "no drinking at home"
    if not rules.get("guests_ok", True) and (ans("guests_frequency") or 0) >= 4:
        return "no frequent guests"
    return None


def practical_label(rent, lo, hi, minutes):
    """Plain words for rent and commute, used instead of a % when no people are
    involved (a "100% fit" for an empty flat would overstate what we know)."""
    if rent > hi:
        return f"Over your budget by ₹{rent - hi:,}", "warn"
    if minutes is None or minutes <= 20:
        return "Fits your budget and commute", "ok"
    return f"Fits your budget, {minutes} min commute", ""


def practical_fit(rent, lo, hi, minutes):
    """0..100 from rent vs budget (60%) and commute (40%).
    Rent inside or under the budget is a full fit; 25% over budget is zero.
    Commute: 10 min or less is full; 45 min or more is zero."""
    rent_fit = 1.0 if rent <= hi else max(0.0, 1 - (rent - hi) / hi * 4)
    commute_fit = 1.0 if minutes is None else max(0.0, min(1.0, 1 - (minutes - 10) / 35))
    return round(100 * (0.6 * rent_fit + 0.4 * commute_fit))


# ---------------------------------------------------------------------------
# Seeker <-> people living in a flat
# ---------------------------------------------------------------------------
def room_fit(ctx, me, listing):
    """Fit with the people who already live there (cohort members and described
    residents). Returns None if nobody with answers lives there, else
    {score, with: [(id, score)], lowest: (id, score, difference), blocked: reason}."""
    occ = [o for o in residents(listing) if o != me and known(ctx, o)]
    if not occ or not in_cohort(ctx, me):
        return None
    for o in occ:
        why = conflict_reason(person(ctx, me), profile(ctx, o))
        if why:
            return {"score": 0, "with": [], "lowest": None, "blocked": why}
    scores = [(o, pair(ctx, me, o)[0]) for o in occ]
    low = min(scores, key=lambda x: (x[1], x[0]))
    return {"score": round(float(np.mean([s for _, s in scores]))), "with": scores,
            "lowest": (low[0], low[1], biggest_difference(ctx, me, low[0])), "blocked": None}


def interested_people(ctx, me, listing):
    """Who else said they're interested, compatible with me, best fit first."""
    out = []
    for pid in listing.get("interested", []):
        if pid == me or not in_cohort(ctx, pid):
            continue
        s, ok = pair(ctx, me, pid)
        if s is None or (ok and s >= MIN_SHOWN_FIT):
            out.append((pid, s))
    return sorted(out, key=lambda x: (-(x[1] or 0), x[0]))


def _solo_row(ctx, me, li):
    """One listing for one seeker, or None if they can't live there."""
    p = person(ctx, me) or {}
    free = free_rooms(li)
    if not free or li["owner_id"] == me or me in residents(li):
        return None
    if p and listing_blocks(li, p):
        return None
    rf = room_fit(ctx, me, li)
    if rf and rf["blocked"]:
        return None
    room = min(free, key=lambda r: (r["rent"], r["room_id"]))
    office = p.get("office_location")
    minutes = commute(li["area"], office) if office else None
    hi = p.get("budget_max", 10 ** 9)
    interested = interested_people(ctx, me, li)
    best = max((x for _, x in interested if x is not None), default=None)
    people = {"kind": "residents", "score": rf["score"], "with": rf["with"], "lowest": rf["lowest"]} if rf else None
    return {"listing": li, "rooms": [room], "rent": room["rent"], "rent_max": room["rent"],
            "rent_total": room["rent"], "minutes": minutes, "office": office, "budget_max": hi,
            "within_budget": room["rent"] <= hi, "practical": practical_fit(room["rent"], 0, hi, minutes),
            "people": people, "interested": interested, "signal": rf["score"] if rf else best}


def _group_row(ctx, group, li):
    """One listing for a whole group, or None: it needs a free room per person,
    every room inside the shared budget, house rules that suit everyone, and
    everyone (residents included) compatible under the hard rules."""
    if li["owner_id"] in group:
        return None
    rooms = pick_rooms(li, len(group))
    lo, hi = shared_budget(ctx, group)
    if len(rooms) < len(group) or any(r["rent"] > hi for r in rooms):
        return None
    if any(listing_blocks(li, person(ctx, m)) for m in group):
        return None
    live = [o for o in residents(li) if known(ctx, o) and o not in group]
    ok, score = fit_together(ctx, group + live)
    if not ok:
        return None
    with_ = [(o, float(np.mean([pair(ctx, m, o)[0] for m in group]))) for o in live]
    minutes = round(float(np.mean([commute(li["area"], person(ctx, m)["office_location"]) for m in group])))
    rents = [r["rent"] for r in rooms]
    return {"listing": li, "rooms": rooms, "rent": min(rents), "rent_max": max(rents), "rent_total": sum(rents),
            "minutes": minutes, "office": None, "budget_max": hi, "within_budget": True,
            "practical": practical_fit(max(rents), lo, hi, minutes),
            "people": {"kind": "group", "score": round(score or 0), "with": with_, "lowest": None},
            "interested": [], "signal": round(score or 0)}


def flat_results(ctx, me, listings, *, members=None, sort="people", shareable_only=False, budget=None,
                 areas=None, kind=None, max_commute=None):
    """Live flats `me` (or me and my group) could move into, filtered and sorted.

    members: everyone in my group when searching as a group (me included), else None.
    sort="people": flats with a people signal first, best fit first. The signal
      is fit with the people already living there; for an empty flat, the best
      fit among people interested in it (MIN_SHOWN_FIT or more). In a group it's
      the group's fit with any residents. Flats without a signal follow, by
      rent and commute.
    sort="practical": rent against budget, then commute.
    shareable_only: rooms in a shared flat, or whole flats with 2+ free rooms
      (just me only; a group search always needs a room each).
    budget=(lo, hi) keeps flats whose rooms all fall in that rent range.

    Each result: listing, rooms (the rooms you'd take), rent, rent_max,
    rent_total, minutes, office, budget_max, within_budget, practical (for
    sorting only, never shown as a %), people ({kind, score, with, lowest} or
    None), interested ([(id, score)]), signal (people fit used to sort, or None).
    """
    group = list(dict.fromkeys([me] + list(members))) if members and len(members) > 1 else None
    out = []
    for li in listings:
        if not is_live(li):
            continue
        if kind and li["kind"] != kind:
            continue
        if areas and li["area"] not in areas:
            continue
        if shareable_only and not group and li["kind"] != "room" and len(free_rooms(li)) < 2:
            continue
        r = _group_row(ctx, group, li) if group else _solo_row(ctx, me, li)
        if r is None:
            continue
        if budget and not all(budget[0] <= x["rent"] <= budget[1] for x in r["rooms"]):
            continue
        if max_commute and r["minutes"] is not None and r["minutes"] > max_commute:
            continue
        out.append(r)
    if sort == "people":
        # Ties (same whole-number fit) go to the flat with more free rooms: room to move in together.
        key = lambda r: (r["signal"] is None, -round(r["signal"] or 0), -len(free_rooms(r["listing"])),  # noqa: E731
                         -r["practical"], r["rent"], r["listing"]["id"])
    else:
        key = lambda r: (-r["practical"], -(r["signal"] or -1), r["rent"], r["listing"]["id"])  # noqa: E731
    return sorted(out, key=key)


def people_results(ctx, me, limit=12):
    """Most compatible people in the cohort for 'Find flatmates'."""
    if not in_cohort(ctx, me):
        return []
    i = ctx["pos"][me]
    order = sorted((j for j in range(len(ctx["df"])) if j != i and ctx["compat"][i, j]),
                   key=lambda j: (-ctx["S"][i, j], j))[:limit]
    ids = list(ctx["df"]["id"])
    return [(ids[j], float(ctx["S"][i, j])) for j in order]


def next_best_person(ctx, member_ids, exclude=()):
    """Replacement when someone passes on a group member: the person who is
    compatible with EVERYONE still in the group (hard rules) and has the best
    average pair score with them. Returns (id, score) or None."""
    idx = [ctx["pos"][m] for m in member_ids if in_cohort(ctx, m)]
    skip = set(exclude) | set(member_ids)
    best = None
    for j, pid in enumerate(ctx["df"]["id"]):
        if pid in skip or not all(ctx["compat"][j, i] for i in idx):
            continue
        score = float(np.mean([ctx["S"][j, i] for i in idx]))
        if best is None or score > best[1]:
            best = (pid, score)
    return best


# ---------------------------------------------------------------------------
# Group <-> listing
# ---------------------------------------------------------------------------
def shared_budget(ctx, member_ids):
    ps = [person(ctx, m) for m in member_ids if in_cohort(ctx, m)]
    return max(p["budget_min"] for p in ps), min(p["budget_max"] for p in ps)


def pick_rooms(listing, n, taken=()):
    """The n cheapest free rooms, preferring rooms nobody else has asked for."""
    free = sorted(free_rooms(listing), key=lambda r: (r["room_id"] in taken, r["rent"], r["room_id"]))
    return free[:n]


# ---------------------------------------------------------------------------
# Lister's view of an application
# ---------------------------------------------------------------------------
def applicant_view(ctx, listing, member_ids):
    """Fit of applicants with each other and with whoever already lives there.
    Returns {score, basis, reasons: [str], clash: str or None}."""
    live = [o for o in residents(listing) if known(ctx, o)]
    everyone = list(dict.fromkeys(member_ids + live))
    scored = [m for m in everyone if known(ctx, m)]
    if len(scored) >= 2:
        d = describe(ctx, scored)
        reasons = [f"Same or close on {m['trait']}" for m in d["matching"]]
        clash = (f"{d['friction'][0]['person']} differs on {d['friction'][0]['trait']}: "
                 f"{d['friction'][0]['detail'].split(': ', 1)[1]}") if d["friction"] else None
        return {"score": round(d["score"]), "basis": "group", "reasons": reasons, "clash": clash}
    p = person(ctx, member_ids[0]) if member_ids else None
    if not p:
        return {"score": None, "basis": None, "reasons": [], "clash": None}
    rent = min((r["rent"] for r in free_rooms(listing)), default=0)
    minutes = commute(listing["area"], p["office_location"])
    reasons = [f"Budget ₹{p['budget_min']:,}–{p['budget_max']:,}", f"{minutes} min to their office"]
    return {"score": None, "rank": practical_fit(rent, p["budget_min"], p["budget_max"], minutes),
            "basis": "practical", "reasons": reasons, "clash": None,
            "label": practical_label(rent, p["budget_min"], p["budget_max"], minutes)}


# ---------------------------------------------------------------------------
# Admin flags (rule-based, with evidence)
# ---------------------------------------------------------------------------
def flags(listings, reports, actions, name_of):
    """Rule-based flags. Each: {id, kind, title, listing_ids, owner_id, evidence: [str]}.
    Dismissed flags are left out; removed listings stop being active, so their
    flags disappear on their own."""
    done = {a["flag_id"] for a in actions}
    active = [li for li in listings if is_active(li)]
    out = []

    for li in active:
        rents = [r["rent"] for r in li["rooms"] if r["rent"] > 0]
        if not rents:
            continue
        avg, area_avg = float(np.mean(rents)), area_rent(li["area"])
        if avg < area_avg * (1 - SCAM_DISCOUNT):
            ev = [f"Rent is ₹{avg:,.0f} per room. The {li['area']} average is ₹{area_avg:,}, "
                  f"so this is {1 - avg / area_avg:.0%} below.",
                  f"Deposit: {li['deposit_months']} month{'s' if li['deposit_months'] != 1 else ''}. "
                  f"Status: {li['status']}."]
            out.append({"id": f"rent:{li['id']}", "kind": "Rent far below the area",
                        "title": f"{li['id']} in {li['area']} is priced far below the area",
                        "listing_ids": [li["id"]], "owner_id": li["owner_id"], "evidence": ev})

    by_owner = defaultdict(list)
    for li in active:
        by_owner[li["owner_id"]].append(li)
    for owner, lis in sorted(by_owner.items()):
        flats = {(li["area"], li["address_hint"]) for li in lis}
        if len(lis) > MAX_ACTIVE_LISTINGS and len(flats) > 1:
            ev = [f"{len(lis)} active listings from one account, in {len({li['area'] for li in lis})} areas:"]
            ev += [f"{li['id']}: {li['bhk']}BHK in {li['area']}, {li['status']}" for li in lis]
            out.append({"id": f"multi:{owner}", "kind": "Many listings from one account",
                        "title": f"{name_of(owner)} has {len(lis)} active listings in different flats",
                        "listing_ids": [li["id"] for li in lis], "owner_id": owner, "evidence": ev})

    by_listing = defaultdict(list)
    for r in reports:
        by_listing[r["listing_id"]].append(r)
    live_ids = {li["id"]: li for li in active}
    for lid, rs in sorted(by_listing.items()):
        if lid not in live_ids:
            continue
        ev = [f"{name_of(r['by'])}: “{r['reason']}”" for r in rs]
        out.append({"id": f"report:{lid}", "kind": "Reported by users",
                    "title": f"{lid} in {live_ids[lid]['area']} was reported {len(rs)} time{'s' if len(rs) > 1 else ''}",
                    "listing_ids": [lid], "owner_id": live_ids[lid]["owner_id"], "evidence": ev})
    return [f for f in out if f["id"] not in done]


# ---------------------------------------------------------------------------
# Shared bills
# ---------------------------------------------------------------------------
def settle(expenses, members):
    """Who owes whom, from bills split equally. Returns [(debtor, creditor, amount)],
    the fewest transfers by matching largest debtor with largest creditor."""
    bal = {m: 0.0 for m in members}
    for e in expenses:
        split = [m for m in e["split_between"] if m in bal] or list(bal)
        share = e["amount"] / len(split)
        bal[e["paid_by"]] = bal.get(e["paid_by"], 0.0) + e["amount"]
        for m in split:
            bal[m] -= share
    debt = sorted(([m, -v] for m, v in bal.items() if v < -0.5), key=lambda x: (-x[1], x[0]))
    cred = sorted(([m, v] for m, v in bal.items() if v > 0.5), key=lambda x: (-x[1], x[0]))
    out = []
    while debt and cred:
        amt = min(debt[0][1], cred[0][1])
        out.append((debt[0][0], cred[0][0], round(amt)))
        debt[0][1] -= amt
        cred[0][1] -= amt
        if debt[0][1] < 0.5:
            debt.pop(0)
        if cred[0][1] < 0.5:
            cred.pop(0)
    return out


def trait_name(t):
    return TRAIT_SHORT[t]
