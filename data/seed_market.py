"""
Seed the marketplace (listings, landlords, one waiting group application,
a report) for the demo. Deterministic: same files every run.

Run:  python data/seed_market.py      (also resets every marketplace file)

What it sets up, so each demo account has a story:
  - Mr. Rao (O001) owns an approved 3BHK in Gachibowli, let as rooms, with one
    group application already waiting.
  - Rahul Patel (U167) rents a 2BHK in Madhapur and lists his spare room; his
    landlord is not on the app, so rent goes to the landlord's UPI ID.
  - Arjun Gupta (U102) has picked "Find a flat and flatmates"; Vamsi Das (U082),
    his best fit in the cohort, is interested in Mr. Rao's flat. With Best people
    fit and Only flats I can share, Mr. Rao's flat is first in Explore for Arjun.
  - Meera Joshi (O006) lists a 1BHK in Madhapur, for one person: switching off
    Only flats I can share is what makes it appear.
  - Rents follow the area table in core/schema.py. One pending listing is priced
    50% below its area average, and its owner has three listings, so the admin
    Flags page has real evidence to show. One listing has a user report.

Interested people and the waiting group are picked with the matching engine
(pair scores, hard rules), not by hand, so they are actually compatible.
"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from core import store  # noqa: E402
from core.encode import PROFILES_CSV, _clean  # noqa: E402
from core.grouping import pair_scores  # noqa: E402
from core.market import listing_blocks  # noqa: E402
from core.schema import AREAS  # noqa: E402

SEED = 42
CREATED = "2027-05-20T10:00:00+05:30"  # fixed, so files are identical every run

ARJUN, VAMSI, RAHUL, MR_RAO = "U102", "U082", "U167", "O001"

PEOPLE = [
    {"id": "O001", "name": "Srinivas Rao", "email": "srinivas.rao@example.com", "kind": "landlord",
     "gender": "Male", "seeded": True},
    # Lives in L003 and described her own habits on the listing form (no quiz).
    {"id": "O002", "name": "Lakshmi Iyer", "email": "lakshmi.iyer@example.com", "kind": "landlord",
     "gender": "Female", "seeded": True, "described_by": "O002",
     "answers": {"sleep_time": 1, "wake_time": 1, "cleanliness": 5, "noise_tolerance": 2, "guests_frequency": 2,
                 "food": 1, "cooking": 3, "smoking": 1, "drinking": 1, "work_mode": 3, "social_level": 3}},
    {"id": "O003", "name": "Kiran Kumar", "email": "kiran.kumar@example.com", "kind": "landlord",
     "gender": "Male", "seeded": True},
    {"id": "O004", "name": "Sunita Reddy", "email": "sunita.reddy@example.com", "kind": "landlord",
     "gender": "Female", "seeded": True},
    {"id": "O005", "name": "Venkat Naidu", "email": "venkat.naidu@example.com", "kind": "landlord",
     "gender": "Male", "seeded": True},
    {"id": "O006", "name": "Meera Joshi", "email": "meera.joshi@example.com", "kind": "landlord",
     "gender": "Female", "seeded": True},
]

OPEN = {"gender": "any", "veg_only": False, "no_smoking": False, "no_drinking": False, "guests_ok": True}


def rooms(*specs):
    """specs: (rent, attached_bath, furnished, occupied_by)"""
    return [{"room_id": f"R{i}", "rent": rent, "attached_bath": bath, "furnished": furn, "occupied_by": occ}
            for i, (rent, bath, furn, occ) in enumerate(specs, 1)]


def nearest_office(area):
    a = next(x for x in AREAS if x["area"] == area)
    return min(a["commute"], key=lambda o: (a["commute"][o], o))


def listing(lid, owner, kind, lister_type, area, hint, bhk, room_list, status="approved", rules=None,
            occupants=(), landlord_on_app=True, landlord_upi="", deposit=2, available="2027-07-01"):
    return {"id": lid, "owner_id": owner, "kind": kind, "lister_type": lister_type, "area": area,
            "address_hint": hint, "office_nearest": nearest_office(area), "bhk": bhk, "rooms": room_list,
            "deposit_months": deposit, "available_from": available, "rules": {**OPEN, **(rules or {})},
            "occupants": list(occupants), "landlord_on_app": landlord_on_app,
            "landlord_upi": landlord_upi if not landlord_on_app else "", "status": status,
            "photos": [f"{lid}-{n}" for n in ("living", "room", "kitchen")], "interested": [],
            "created_at": CREATED}


def build(df):
    S, compat = pair_scores(df)
    pos = {pid: i for i, pid in enumerate(df["id"])}
    rows = df.set_index("id")

    def first(mask, exclude=()):
        ids = [i for i in df.loc[mask, "id"] if i not in exclude]
        return ids[0]

    # Occupants, chosen by rule so they are believable residents of that flat.
    iyer_lodger = first((df.gender == "Female") & (df.food == 1) & (df.office_location == "Kondapur"))
    kotha_a = first((df.gender == "Male") & (df.office_location == "Kondapur") & (df.smoking < 3), [RAHUL, ARJUN, VAMSI])
    kotha_b = next(i for i in df.loc[(df.gender == "Male") & (df.office_location == "Kondapur"), "id"]
                   if i not in (kotha_a, RAHUL, ARJUN, VAMSI) and compat[pos[kotha_a], pos[i]])
    seri_tenant = first((df.office_location == "Gachibowli") & (df.budget_min <= 9000), [ARJUN, VAMSI, RAHUL])

    L = [
        listing("L001", MR_RAO, "room", "owner_away", "Gachibowli", "Near DLF Cyber City gate 2, 3rd floor", 3,
                rooms((14500, True, True, None), (14000, True, True, None), (13500, False, True, None))),
        listing("L002", RAHUL, "room", "tenant_spare_room", "Madhapur", "Behind Inorbit Mall, 2nd floor", 2,
                rooms((15000, True, True, RAHUL), (14500, False, True, None)), rules={"gender": "male"},
                occupants=[RAHUL], landlord_on_app=False, landlord_upi="kvreddy.rent@okaxis"),
        listing("L003", "O002", "room", "owner_lives_here", "Kondapur", "Near Botanical Garden, independent house", 3,
                rooms((0, True, True, "O002"), (12000, True, True, iyer_lodger), (11500, False, True, None)),
                rules={"gender": "female", "veg_only": True, "no_smoking": True, "no_drinking": True},
                occupants=["O002", iyer_lodger]),
        listing("L004", "O005", "room", "owner_away", "Kothaguda", "Off Kothaguda main road, gated society", 3,
                rooms((11000, True, True, kotha_a), (11000, False, True, kotha_b), (10500, False, False, None)),
                rules={"gender": "male"}, occupants=[kotha_a, kotha_b]),
        listing("L005", "O005", "whole_flat", "owner_away", "Madhapur", "Ayyappa Society, lift and power backup", 2,
                rooms((15500, True, True, None), (15000, True, True, None))),
        listing("L006", "O003", "whole_flat", "owner_away", "Manikonda", "Near Lanco Hills", 3,
                rooms((9000, True, False, None), (9000, False, False, None), (8500, False, False, None))),
        listing("L007", "O003", "whole_flat", "owner_away", "Miyapur", "Near Miyapur metro", 2,
                rooms((7500, True, False, None), (7000, False, False, None))),
        listing("L008", "O004", "whole_flat", "owner_away", "Gachibowli", "Telecom Nagar, 5 min to ORR", 2,
                rooms((14500, True, True, None), (14000, False, True, None)), status="pending"),
        listing("L009", "O003", "whole_flat", "owner_away", "Kondapur", "Near Kondapur main road", 2,
                rooms((6000, True, True, None), (6000, True, True, None)), status="pending", deposit=1,
                available="2027-06-15"),
        listing("L010", "O004", "whole_flat", "owner_away", "Nanakramguda", "Near Financial District", 3,
                rooms((13000, True, True, None), (13000, False, True, None), (12500, False, True, None))),
        listing("L011", seri_tenant, "room", "tenant_spare_room", "Serilingampally", "Near Lingampally station", 2,
                rooms((8500, True, False, seri_tenant), (8000, False, False, None)), occupants=[seri_tenant]),
        listing("L012", "O002", "whole_flat", "owner_away", "Kothaguda", "Kothaguda crossroads, new building", 2,
                rooms((11500, True, True, None), (11000, True, True, None))),
        # A 1BHK for one person: the flat "Only flats I can share" hides. Last in the
        # list, so the random interested picks for L001-L012 stay the same.
        listing("L013", "O006", "whole_flat", "owner_away", "Madhapur", "Near Madhapur metro, 4th floor", 1,
                rooms((16000, True, True, None),)),
    ]

    # Interested people: compatible with the flat's rules and residents, rent in
    # budget, short commute. Vamsi is interested in Mr. Rao's flat (Arjun's story).
    rng = np.random.default_rng(SEED)
    keep_out = {ARJUN, RAHUL}
    for li in L:
        free = [r for r in li["rooms"] if r["occupied_by"] is None]
        if li["status"] != "approved" or not free:
            continue
        rent = min(r["rent"] for r in free)
        area = next(a for a in AREAS if a["area"] == li["area"])
        cands = []
        for pid in df["id"]:
            p = rows.loc[pid]
            if pid in keep_out or pid in li["occupants"] or pid == li["owner_id"]:
                continue
            if not (p.budget_min <= rent <= p.budget_max) or area["commute"][p.office_location] > 20:
                continue
            if listing_blocks(li, p.to_dict()):
                continue
            if any(o in pos and not compat[pos[pid], pos[o]] for o in li["occupants"]):
                continue
            cands.append(pid)
        picked = list(rng.choice(cands, size=min(len(cands), int(rng.integers(3, 6))), replace=False)) if cands else []
        if li["id"] == "L001":
            picked = [VAMSI] + [p for p in picked if p != VAMSI][:3]
        li["interested"] = sorted(str(p) for p in picked)

    # A group already waiting on Mr. Rao's flat: the best compatible pair who fit
    # its budget and rules (and are not part of the demo stories).
    l1 = L[0]
    ok = [pid for pid in df["id"] if pid not in (ARJUN, VAMSI, RAHUL)
          and rows.loc[pid].budget_min <= 14000 <= rows.loc[pid].budget_max
          and not listing_blocks(l1, rows.loc[pid].to_dict())]
    a, b = max(((x, y) for i, x in enumerate(ok) for y in ok[i + 1:] if compat[pos[x], pos[y]]),
               key=lambda p: (S[pos[p[0]], pos[p[1]]], p))
    groups = [{"id": "GR001", "member_ids": [a, b], "created_by": a, "target_size": 2,
               "anchored_listing_id": "L001", "status": "applied", "accepted": [a, b], "shortlist": ["L001"],
               "created_at": CREATED}]
    applications = [{"id": "AP001", "listing_id": "L001", "applicant": None, "group_id": "GR001",
                     "room_ids": ["R2", "R3"], "status": "sent", "visit_slot": None, "created_at": CREATED}]
    reports = [{"id": "RP001", "listing_id": "L007", "by": "U010",
                "reason": "Asked me to send a token amount by UPI before showing the flat.", "created_at": CREATED}]
    member_state = [{"id": ARJUN, "goal": "both"}]
    return {"listings": L, "groups": groups, "applications": applications, "tenancies": [], "payments": [],
            "expenses": [], "people": PEOPLE, "reports": reports, "flag_actions": [], "member_state": member_state}


def main(quiet=False):
    df = _clean(pd.read_csv(PROFILES_CSV))  # seed profiles only: same output every run
    data = build(df)
    for name in store.ENTITIES:
        store.save(name, data.get(name, []))
    if not quiet:
        for name in store.ENTITIES:
            print(f"{name:14s} {len(data.get(name, []))}")
        print("interested in L001:", data["listings"][0]["interested"])
        print("waiting group:", data["groups"][0]["member_ids"])


if __name__ == "__main__":
    main()
