"""
State changes for the marketplace flows: groups, applications, tenancies,
rent, bills, listings, reports and admin decisions.

No Streamlit here: pages call these and re-render. Fit numbers come from
core/market.py; storage from core/store.py.

What is SIMULATED for the demo (and labelled so in the UI):
  - other members accepting a group (marked accepted straight away)
  - signing the house agreement (a button per member, no e-signature)
  - payments (mock checkout; no money moves; a receipt number is issued)
"""
from datetime import datetime, timezone

from core import llm, market, store

ACTIVE_GROUP = ("forming", "applied", "housed")


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Names (cohort, seeded landlords, signed-up accounts)
# ---------------------------------------------------------------------------
def name_lookup(cohort):
    names = dict(zip(cohort["id"], cohort["name"]))
    names.update({p["id"]: p["name"] for p in store.load("people")})
    return lambda pid: names.get(pid, pid)


# ---------------------------------------------------------------------------
# Home choice
# ---------------------------------------------------------------------------
GOALS = {"flat": "Find a flat", "flatmates": "Find flatmates", "both": "Find a flat and flatmates",
         "list": "List a space"}


def get_goal(mid):
    row = next((r for r in store.load("member_state") if r["id"] == mid), None)
    return row.get("goal") if row else None


def set_goal(mid, goal):
    def fn(rows):
        for r in rows:
            if r["id"] == mid:
                r["goal"] = goal
                return
        rows.append({"id": mid, "goal": goal})
    store.mutate("member_state", fn)


# ---------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------
def my_group(mid):
    """The member's current group (latest active one), or None."""
    mine = [g for g in store.load("groups") if mid in g["member_ids"] and g["status"] in ACTIVE_GROUP]
    return mine[-1] if mine else None


def _leave_forming(rows, mid):
    """A member is in one forming group at a time: leave any other forming group."""
    for g in rows:
        if g["status"] == "forming" and mid in g["member_ids"]:
            g["member_ids"] = [m for m in g["member_ids"] if m != mid]
            g["accepted"] = [m for m in g.get("accepted", []) if m != mid]
            if len(g["member_ids"]) < 2:
                g["status"] = "dissolved"


def create_group(creator, member_ids, target_size, anchored_listing_id=None):
    """New forming group. Other members' acceptance is simulated (accepted at once)."""
    member_ids = list(dict.fromkeys([creator] + [m for m in member_ids if m != creator]))
    out = {}

    def fn(rows):
        for m in member_ids:
            _leave_forming(rows, m)
        g = {"id": store.next_id("GR", rows), "member_ids": member_ids, "created_by": creator,
             "target_size": max(target_size, len(member_ids)), "anchored_listing_id": anchored_listing_id,
             "status": "forming", "accepted": list(member_ids),
             "shortlist": [anchored_listing_id] if anchored_listing_id else [], "created_at": _now()}
        rows.append(g)
        out.update(g)
    store.mutate("groups", fn)
    return out


def leave_group(mid, group_id):
    def fn(rows):
        for g in rows:
            if g["id"] == group_id:
                g["member_ids"] = [m for m in g["member_ids"] if m != mid]
                g["accepted"] = [m for m in g.get("accepted", []) if m != mid]
                if len(g["member_ids"]) < 2:
                    g["status"] = "dissolved"
    store.mutate("groups", fn)


def shortlist(group_id, listing_id):
    def fn(rows):
        for g in rows:
            if g["id"] == group_id and listing_id not in g["shortlist"]:
                g["shortlist"].append(listing_id)
    store.mutate("groups", fn)


def unshortlist(group_id, listing_id):
    """Take a flat off the group's shortlist (and drop it as the group's anchor flat)."""
    def fn(rows):
        for g in rows:
            if g["id"] == group_id:
                g["shortlist"] = [x for x in g["shortlist"] if x != listing_id]
                if g.get("anchored_listing_id") == listing_id:
                    g["anchored_listing_id"] = None
    store.mutate("groups", fn)


def mark_interested(listing_id, mid, on=True):
    def fn(rows):
        for li in rows:
            if li["id"] == listing_id:
                s = set(li.get("interested", []))
                s.add(mid) if on else s.discard(mid)
                li["interested"] = sorted(s)
    store.mutate("listings", fn)


# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------
def open_applications(listing_id):
    return [a for a in store.load("applications") if a["listing_id"] == listing_id
            and a["status"] in ("sent", "visit_booked")]


def apply(listing_id, member_ids, group_id=None):
    """Apply to a listing for one free room per person. Picks rooms nobody else
    has asked for first. Returns (application, None) or (None, reason)."""
    li = store.get("listings", listing_id)
    taken = {r for a in open_applications(listing_id) for r in a["room_ids"]}
    rooms = market.pick_rooms(li, len(member_ids), taken)
    if len(rooms) < len(member_ids):
        return None, f"This flat has {len(market.free_rooms(li))} free rooms; your group needs {len(member_ids)}."
    dup = [a for a in open_applications(listing_id)
           if (group_id and a.get("group_id") == group_id) or (not group_id and a.get("applicant") == member_ids[0])]
    if dup:
        return dup[0], None
    app = store.insert("applications", {"listing_id": listing_id, "applicant": None if group_id else member_ids[0],
                                        "group_id": group_id, "room_ids": [r["room_id"] for r in rooms],
                                        "status": "sent", "visit_slot": None, "created_at": _now()}, prefix="AP")
    if group_id:
        store.update("groups", group_id, status="applied")
    return app, None


def applicants_of(app):
    if app.get("group_id"):
        g = store.get("groups", app["group_id"])
        return g["member_ids"] if g else []
    return [app["applicant"]]


def book_visit(app_id, slot):
    store.update("applications", app_id, status="visit_booked", visit_slot=slot)


def reject_application(app_id, reason=""):
    app = store.update("applications", app_id, status="rejected", reason=reason)
    # Back to forming only if the group has no other application still open.
    if app and app.get("group_id") and not any(
            a["group_id"] == app["group_id"] for a in store.load("applications")
            if a.get("group_id") and a["status"] in ("sent", "visit_booked")):
        store.update("groups", app["group_id"], status="forming")


def accept_application(ctx, app_id):
    """Accept: rooms are taken, a tenancy is created with a house agreement
    (existing llm.house_agreement, AI or template), and this month's rent shares
    become due. Other open applications for the same rooms are declined.
    Returns (tenancy, None) or (None, reason)."""
    app = store.get("applications", app_id)
    li = store.get("listings", app["listing_id"])
    free = {r["room_id"] for r in market.free_rooms(li)}
    if not set(app["room_ids"]) <= free:
        return None, "Some of these rooms are no longer free. Decline this application or free a room first."
    members = applicants_of(app)
    rent = {r["room_id"]: r["rent"] for r in li["rooms"]}
    shares = [{"member_id": m, "room_id": rid, "rent_share": rent[rid]} for m, rid in zip(members, app["room_ids"])]

    everyone = [m for m in dict.fromkeys(members + market.residents(li)) if market.known(ctx, m)]
    if len(everyone) >= 2:
        text, source = llm.house_agreement(market.describe(ctx, everyone))
    else:
        text, source = ("House rules to be agreed with the owner at move-in.", "Template")

    tenancy = store.insert("tenancies", {"listing_id": li["id"], "application_id": app_id, "members": shares,
                                         "start_date": li["available_from"], "agreement_text": text,
                                         "agreement_source": source, "signed": [], "created_at": _now()},
                           prefix="T")

    def take(rows):
        for r in rows:
            if r["id"] == li["id"]:
                for room in r["rooms"]:
                    if room["room_id"] in app["room_ids"]:
                        room["occupied_by"] = dict(zip(app["room_ids"], members))[room["room_id"]]
                r["occupants"] = list(dict.fromkeys(r.get("occupants", []) + members))
    store.mutate("listings", take)

    def decide(rows):
        for a in rows:
            if a["id"] == app_id:
                a["status"] = "accepted"
            elif a["listing_id"] == li["id"] and a["status"] in ("sent", "visit_booked") \
                    and set(a["room_ids"]) & set(app["room_ids"]):
                a["status"], a["reason"] = "rejected", "Rooms were let to another applicant."
    store.mutate("applications", decide)
    if app.get("group_id"):
        store.update("groups", app["group_id"], status="housed")

    month = li["available_from"][:7]

    def due(rows):
        for s in shares:
            rows.append({"id": store.next_id("P", rows), "tenancy_id": tenancy["id"], "member_id": s["member_id"],
                         "month": month, "amount": s["rent_share"], "status": "due", "paid_at": None,
                         "method": None, "receipt_no": None})
    store.mutate("payments", due)
    return tenancy, None


def tenancies_for_member(mid):
    return [t for t in store.load("tenancies") if any(m["member_id"] == mid for m in t["members"])]


def tenancies_for_lister(mid):
    mine = {li["id"] for li in store.load("listings") if li["owner_id"] == mid}
    return [t for t in store.load("tenancies") if t["listing_id"] in mine]


def sign(tenancy_id, mid):
    def fn(rows):
        for t in rows:
            if t["id"] == tenancy_id and mid not in t["signed"]:
                t["signed"].append(mid)
    store.mutate("tenancies", fn)


# ---------------------------------------------------------------------------
# Rent and bills (mock payments: no money moves)
# ---------------------------------------------------------------------------
def pay(payment_id, method):
    def fn(rows):
        for p in rows:
            if p["id"] == payment_id and p["status"] == "due":
                p.update(status="paid", method=method, paid_at=_now(),
                         receipt_no=f"NM-{p['month'].replace('-', '')}-{p['id']}")
    rows = store.mutate("payments", fn)
    return next(p for p in rows if p["id"] == payment_id)


def add_expense(tenancy_id, label, amount, paid_by, split_between):
    return store.insert("expenses", {"tenancy_id": tenancy_id, "label": label.strip(), "amount": int(amount),
                                     "paid_by": paid_by, "split_between": list(split_between),
                                     "created_at": _now()}, prefix="E")


def household(tenancy):
    """Everyone who shares bills: the new tenants plus people already living there."""
    li = store.get("listings", tenancy["listing_id"])
    return list(dict.fromkeys(market.residents(li) + [m["member_id"] for m in tenancy["members"]]))


# ---------------------------------------------------------------------------
# Listings, reports, admin
# ---------------------------------------------------------------------------
def add_housemate(lister_id, name, company, phone):
    """Someone already living in a listed flat, as the lister entered them: basic
    details only. The phone number is shown to the lister, never to seekers."""
    return store.insert("people", {"name": name, "kind": "housemate", "organisation": company, "phone": phone,
                                   "added_by": lister_id, "created_at": _now()}, prefix="H")


def update_housemate(pid, name, company, phone):
    # Not store.update: its first parameter is also called `name`.
    def fn(rows):
        for p in rows:
            if p["id"] == pid:
                p.update(name=name, organisation=company, phone=phone)
    store.mutate("people", fn)


def housemates(listing):
    """People-store rows for the housemates entered on this listing, by room order."""
    rows = {p["id"]: p for p in store.load("people") if p.get("kind") == "housemate"}
    return [rows[o] for o in listing.get("occupants", []) if o in rows]


def describe_self(person_id, name, answers):
    """A lister who lives in but hasn't taken the quiz describes their own habits."""
    answers = {t: int(v) for t, v in answers.items()}
    if not store.update("people", person_id, answers=answers, described_by=person_id):
        store.insert("people", {"id": person_id, "name": name, "kind": "lister", "answers": answers,
                                "described_by": person_id, "created_at": _now()})


def create_listing(owner_id, fields):
    """New listing, pending until an admin approves it."""
    row = {"owner_id": owner_id, "status": "pending", "interested": [], "photos": [], "created_at": _now(), **fields}
    return store.insert("listings", row, prefix="L")


def update_listing(listing_id, **changes):
    """The lister's edits. The room count and who lives where don't change here."""
    return store.update("listings", listing_id, updated_at=_now(), **changes)


def delete_listing(listing_id, by):
    """Delete a listing the lister owns. Refused while someone rents through it.
    Open applications are declined, and the flat leaves every group's shortlist.
    Returns None, or the reason it can't be deleted."""
    li = store.get("listings", listing_id)
    if not li or li["owner_id"] != by:
        return "You can only delete your own listings."
    if any(t["listing_id"] == listing_id for t in store.load("tenancies")):
        return "People rent through this listing, so it can't be deleted."

    for a in open_applications(listing_id):
        reject_application(a["id"], "The lister removed this listing.")

    def drop_shortlists(rows):
        for g in rows:
            g["shortlist"] = [x for x in g.get("shortlist", []) if x != listing_id]
            if g.get("anchored_listing_id") == listing_id:
                g["anchored_listing_id"] = None
    store.mutate("groups", drop_shortlists)

    hm = {p["id"] for p in housemates(li)}
    store.mutate("people", lambda rows: [p for p in rows if p["id"] not in hm])
    store.mutate("listings", lambda rows: [r for r in rows if r["id"] != listing_id])
    return None


def review_listing(listing_id, approve, reason="", by=None):
    return store.update("listings", listing_id, status="approved" if approve else "rejected",
                        review_reason=reason.strip(), reviewed_by=by)


def report_listing(listing_id, by, reason):
    return store.insert("reports", {"listing_id": listing_id, "by": by, "reason": reason.strip(),
                                    "created_at": _now()}, prefix="RP")


def act_on_flag(flag, action, by=None):
    """action: 'dismissed' (no problem) or 'removed' (take the listings down)."""
    store.insert("flag_actions", {"flag_id": flag["id"], "action": action, "by": by, "at": _now()}, prefix="FA")
    if action == "removed":
        for lid in flag["listing_ids"]:
            store.update("listings", lid, status="removed")
