"""
Fit scores and checks for the marketplace (flats, rooms, groups, flags).

Pure functions: no Streamlit, no file access. Pages pass in the cohort, the
matching results and the store rows, so everything here is unit-testable.

WHY no second scoring engine: every person-to-person number is the existing
pair score from core/grouping.pair_scores, and every group number is
describe_group/group_score. This module only decides WHICH people to compare
(a seeker and the people already living in a flat, a group and a flat) and
adds the practical side (rent and commute) where no people are involved.

Score meanings, so the UI can say what a number is:
  "people"    - lifestyle fit with the people you'd live with (pair scores)
  "group"     - group score of everyone who'd live there
  "practical" - rent and commute fit, for a flat with nobody living in it yet
"""
import itertools
from collections import defaultdict

import numpy as np

from core.grouping import conflict_reason, describe_group, group_score
from core.schema import (AREAS, MAX_ACTIVE_LISTINGS, QUESTION_UI, SCAM_DISCOUNT, TRAIT_RANGE, TRAIT_SHORT, TRAITS,
                         WEIGHTS)

AREA = {a["area"]: a for a in AREAS}
_W = np.array([WEIGHTS[t] for t in TRAITS])
_RANGE = np.array([TRAIT_RANGE[t][1] - TRAIT_RANGE[t][0] for t in TRAITS], dtype=float)


# ---------------------------------------------------------------------------
# Context: the cohort and its matching results, indexed by member id
# ---------------------------------------------------------------------------
def make_ctx(df, clustering, res):
    return {"df": df, "S": res["S"], "compat": res["compat"], "cl": clustering,
            "pos": {pid: i for i, pid in enumerate(df["id"])}, "rows": df.set_index("id", drop=False)}


def in_cohort(ctx, pid):
    return pid in ctx["pos"]


def person(ctx, pid):
    return ctx["rows"].loc[pid].to_dict() if in_cohort(ctx, pid) else None


def pair(ctx, a, b):
    """(score 0..100, compatible) for two cohort members; (None, True) if either has no answers."""
    if not (in_cohort(ctx, a) and in_cohort(ctx, b)):
        return None, True
    i, j = ctx["pos"][a], ctx["pos"][b]
    return float(ctx["S"][i, j]), bool(ctx["compat"][i, j])


def biggest_difference(ctx, a, b):
    """The trait two people differ on most (weighted), as (trait key, a's answer, b's answer)."""
    pa, pb = person(ctx, a), person(ctx, b)
    gaps = [abs(pa[t] - pb[t]) / _RANGE[k] * _W[k] for k, t in enumerate(TRAITS)]
    k = int(np.argmax(gaps))
    if gaps[k] == 0:
        return None
    t = TRAITS[k]
    return t, QUESTION_UI[t]["choices"][int(pa[t])], QUESTION_UI[t]["choices"][int(pb[t])]


def describe(ctx, member_ids):
    """describe_group for any list of cohort member ids (order kept)."""
    idx = [ctx["pos"][m] for m in member_ids if in_cohort(ctx, m)]
    d = describe_group(idx, ctx["df"], ctx["S"], ctx["cl"]["personas"], ctx["cl"]["labels"])
    d["target"] = len(idx)
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
    """Fit with the people who already live there (cohort members only).
    Returns None if nobody with answers lives there, else
    {score, with: [(id, score)], lowest: (id, score, difference), blocked: reason}."""
    occ = [o for o in residents(listing) if o != me and in_cohort(ctx, o)]
    if not occ or not in_cohort(ctx, me):
        return None
    for o in occ:
        why = conflict_reason(person(ctx, me), person(ctx, o))
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
        if s is None or ok:
            out.append((pid, s))
    return sorted(out, key=lambda x: (-(x[1] or 0), x[0]))


def flat_results(ctx, me, listings, budget=None, areas=None, kind=None, max_commute=None, office=None):
    """Live listings with a free room that `me` may live in, filtered and ranked.
    me: member id (may be outside the cohort; then no people scores)."""
    p = person(ctx, me) or {}
    office = office or p.get("office_location")
    lo, hi = budget or (p.get("budget_min", 0), p.get("budget_max", 10 ** 9))
    out = []
    for li in listings:
        free = free_rooms(li)
        if not is_live(li) or not free or li["owner_id"] == me or me in residents(li):
            continue
        if kind and li["kind"] != kind:
            continue
        if areas and li["area"] not in areas:
            continue
        if p and listing_blocks(li, p):
            continue
        rf = room_fit(ctx, me, li)
        if rf and rf["blocked"]:
            continue
        rent = min(r["rent"] for r in free)
        minutes = commute(li["area"], office) if office else None
        if budget and not (lo <= rent <= hi):
            continue
        if max_commute and minutes is not None and minutes > max_commute:
            continue
        practical = practical_fit(rent, lo, hi, minutes)
        out.append({"listing": li, "rent": rent, "minutes": minutes, "practical": practical,
                    "room_fit": rf, "score": rf["score"] if rf else practical,
                    "basis": "people" if rf else "practical",
                    "interested": interested_people(ctx, me, li)})
    return sorted(out, key=lambda r: (-r["score"], r["rent"], r["listing"]["id"]))


def people_results(ctx, me, limit=12):
    """Most compatible people in the cohort for 'Find flatmates'."""
    if not in_cohort(ctx, me):
        return []
    i = ctx["pos"][me]
    order = sorted((j for j in range(len(ctx["df"])) if j != i and ctx["compat"][i, j]),
                   key=lambda j: (-ctx["S"][i, j], j))[:limit]
    ids = list(ctx["df"]["id"])
    return [(ids[j], float(ctx["S"][i, j])) for j in order]


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


def group_results(ctx, member_ids, listings):
    """Live listings a whole group can move into together: enough free rooms,
    every room's rent inside the group's shared budget, house rules and the
    current residents compatible with everyone. Ranked by the group score of
    everyone who'd live there, then average commute, then total rent."""
    lo, hi = shared_budget(ctx, member_ids)
    n = len(member_ids)
    out = []
    for li in listings:
        if not is_live(li) or li["owner_id"] in member_ids:
            continue
        rooms = pick_rooms(li, n)
        if len(rooms) < n or any(not (r["rent"] <= hi) for r in rooms):
            continue
        if any(listing_blocks(li, person(ctx, m)) for m in member_ids):
            continue
        everyone = list(dict.fromkeys(member_ids + [o for o in residents(li) if in_cohort(ctx, o)]))
        idx = [ctx["pos"][m] for m in everyone]
        if not all(ctx["compat"][a, b] for a, b in itertools.combinations(idx, 2)):
            continue
        offices = [person(ctx, m)["office_location"] for m in member_ids]
        out.append({"listing": li, "rooms": rooms, "rent_total": sum(r["rent"] for r in rooms),
                    "score": round(group_score(idx, ctx["S"])), "with_residents": len(everyone) > n,
                    "minutes": round(float(np.mean([commute(li["area"], o) for o in offices])))})
    return sorted(out, key=lambda r: (-r["score"], r["minutes"], r["rent_total"], r["listing"]["id"]))


# ---------------------------------------------------------------------------
# Lister's view of an application
# ---------------------------------------------------------------------------
def applicant_view(ctx, listing, member_ids):
    """Fit of applicants with each other and with whoever already lives there.
    Returns {score, basis, reasons: [str], clash: str or None}."""
    live = [o for o in residents(listing) if in_cohort(ctx, o)]
    everyone = list(dict.fromkeys(member_ids + live))
    known = [m for m in everyone if in_cohort(ctx, m)]
    if len(known) >= 2:
        d = describe(ctx, known)
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
    return {"score": practical_fit(rent, p["budget_min"], p["budget_max"], minutes), "basis": "practical",
            "reasons": reasons, "clash": None}


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
