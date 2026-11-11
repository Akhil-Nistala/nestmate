"""
Marketplace routes: Explore, My group, My listings, Rent.

Every fit number here comes from core/market.py, which reuses the matching
engine's pair and group scores. State changes go through core/actions.py.
What is simulated for the demo is said on screen where it happens: other
members accepting, signing the agreement, and payments.
"""
import re
from datetime import date

import streamlit as st

from core import actions, market, store
from core.schema import AREAS, LISTER_TYPES, LISTING_GENDER, LISTING_KINDS, TRAIT_SHORT, VISIT_SLOTS
from ui import nav, session
from ui.components import (lc, avatar, chip, empty, engine, esc, first, habit_grid, join_and, key_tag, md, money,
                           month_name, page_head, people_row, src_tag, stats)
from ui.member_pages import group_card, group_sentence, me_id, my_profile, need_quiz

UPI_RE = re.compile(r"^[\w.\-]{2,}@[A-Za-z]{2,}$")


# ---------------------------------------------------------------------------
# Listing text
# ---------------------------------------------------------------------------
def listing_title(li):
    if li["kind"] == "whole_flat":
        return f"{li['bhk']}BHK flat in {esc(li['area'])}"
    return f"Room in a {li['bhk']}BHK in {esc(li['area'])}"


def lister_sentence(li, names):
    who = esc(names(li["owner_id"]))
    if li["lister_type"] == "owner_lives_here":
        return f"{who} owns this flat and lives there."
    if li["lister_type"] == "tenant_spare_room":
        s = f"{who} rents this flat and is letting a spare room."
        if not li.get("landlord_on_app"):
            s += " The landlord isn't on Nestmate, so rent goes to their UPI ID."
        return s
    return f"Listed by the owner, {who}, who doesn't live there."


def rules_sentence(li):
    r = li["rules"]
    bits = [LISTING_GENDER[r.get("gender", "any")]]
    bits += [t for k, t in (("veg_only", "veg-only kitchen"), ("no_smoking", "no smoking"),
                            ("no_drinking", "no drinking")) if r.get(k)]
    bits.append("guests welcome" if r.get("guests_ok", True) else "no frequent guests")
    return join_and([bits[0]] + bits[1:]) + "."


def free_chip(li):
    n = len(market.free_rooms(li))
    return chip(f"{n} room{'s' if n != 1 else ''} free", "ok" if n else "warn")


# ---------------------------------------------------------------------------
# Explore
# ---------------------------------------------------------------------------
MODES = {"both": "Flats and people", "flat": "Flats and rooms", "people": "Flatmates",
         "group": "Flats for your group"}


def _open(lid):
    session.state()["explore"]["open"] = lid


def _result_card(r, uid, names, ctx, show_interest):
    li = r["listing"]
    rf = r["room_fit"]
    basis = "Fit with the people living there"
    tag = key_tag(r["score"], title=basis) if rf else chip(*r["label"])
    office = (market.person(ctx, uid) or {}).get("office_location", "")
    lines = f"Rooms from {money(r['rent'])} each, {r['minutes']} min to your office in {esc(office)}. {rules_sentence(li)}"
    extra = ""
    if rf:
        live = join_and(esc(first(names(o))) for o, _ in rf["with"])
        extra += f"<p class='card-p'>You'd live with {live}.</p>"
        low = rf["lowest"]
        if low and low[2]:
            t, mine, theirs = low[2]
            extra += (f"<p class='warnline'>You and {esc(first(names(low[0])))} differ on {TRAIT_SHORT[t]}: "
                      f"you said {esc(lc(mine))}, {esc(first(names(low[0])))} said {esc(lc(theirs))}.</p>")
    if show_interest and r["interested"]:
        n = len(r["interested"])
        faces = "".join(f"<span class='face'>{avatar(names(p))}<span>{esc(first(names(p)))}"
                        f"{f' <b>{s:.0f}%</b>' if s is not None else ''}</span></span>"
                        for p, s in r["interested"][:4])
        extra += (f"<p class='card-p strong'>{n} {'person' if n == 1 else 'people'} "
                  f"{'is' if n == 1 else 'are'} interested</p><div class='faces'>{faces}</div>")
    with st.container(key=f"res-{li['id']}"):
        md(f"""<div class='card-head'><div class='ch-main'>
              <h2 class='card-h'>{listing_title(li)} {free_chip(li)}</h2>
              <p class='card-p'>{lines}</p>{extra}</div>
              {tag}</div>""")
        st.button("Open this flat", key=f"open-{li['id']}", on_click=_open, args=(li["id"],))


def _people_mode(ctx, uid, names):
    people = market.people_results(ctx, uid)
    if not people:
        empty("Nobody fits your dealbreakers yet", "Try a wider budget or fewer dealbreakers in Your answers.")
        return
    md("<p class='lede'>The people you'd get on with best. To form a group, go to Flat groups.</p>")
    if st.button("See flat groups", type="primary"):
        nav.go("matches")
    me = market.person(ctx, uid)
    for pid, score in people:
        p = market.person(ctx, pid)
        diff = market.biggest_difference(ctx, uid, pid)
        note = (f"Biggest difference: {TRAIT_SHORT[diff[0]]}, you said {esc(lc(diff[1]))}, "
                f"{esc(first(p['name']))} said {esc(lc(diff[2]))}." if diff else "You answered everything the same.")
        with st.container(key=f"person-{pid}"):
            md(f"""<div class='card-head'><div class='ch-main'>
                  <h2 class='card-h'>{esc(p['name'])}</h2>
                  <p class='card-p'>{esc(p['organisation'])}, working in {esc(p['office_location'])}. Budget
                  {money(p['budget_min'])}–{p['budget_max']:,}, wants a {p['flat_size_pref']}-person flat.</p>
                  <p class='fine'>{note}</p></div>{key_tag(score)}</div>""")
            md(habit_grid([me, p], uid))


def _group_mode(ctx, uid, names, listings):
    g = actions.my_group(uid)
    if not g:
        empty("You don't have a group yet", "Accept a group in Flat groups, then come back here.")
        return
    results = market.group_results(ctx, g["member_ids"], listings)
    lo, hi = market.shared_budget(ctx, g["member_ids"])
    md(f"<p class='lede'>Flats with {len(g['member_ids'])} free rooms, each inside your group's shared budget of "
       f"{money(lo)}–{hi:,}, where the house rules and the people already living there suit all of you.</p>")
    if not results:
        empty("No flat fits the whole group yet", "New flats are listed every week. Try Flats and rooms to see "
              "everything, or ask your group about a wider budget.")
        return
    for r in results:
        li = r["listing"]
        with st.container(key=f"gres-{li['id']}"):
            who = "the group and the people already living there" if r["with_residents"] else "your group"
            rooms = ", ".join(f"{x['room_id']} {money(x['rent'])}" for x in r["rooms"])
            md(f"""<div class='card-head'><div class='ch-main'>
                  <h2 class='card-h'>{listing_title(li)} {free_chip(li)}</h2>
                  <p class='card-p'>Rooms {rooms}. {money(r['rent_total'])} a month for the group, about
                  {r['minutes']} min average commute. {rules_sentence(li)}</p></div>
                  {key_tag(r['score'], title='Group fit of ' + who)}</div>
                  <p class='fine'>Group fit of {who}.</p>""")
            with st.container(horizontal=True, gap="small"):
                st.button("Open this flat", key=f"gopen-{li['id']}", on_click=_open, args=(li["id"],))
                if li["id"] in g["shortlist"]:
                    md(f"<p class='fine inline'>{chip('Shortlisted', 'ok')}</p>")
                elif st.button("Shortlist for the group", key=f"short-{li['id']}"):
                    actions.shortlist(g["id"], li["id"])
                    st.rerun()


def _flat_filters(me):
    with st.container(key="filters", horizontal=True, gap="medium"):
        budget = st.slider("Rent per room (₹)", 5000, 25000, (5000, int(me["budget_max"])), step=500,
                           key="f-budget")
        areas = st.multiselect("Areas", [a["area"] for a in AREAS], placeholder="Any area", key="f-areas")
        kind = st.pills("Type", ["room", "whole_flat"], format_func={"room": "Rooms", "whole_flat": "Whole flats"}.get,
                        key="f-kind")
        commute = st.select_slider("Max commute", [10, 15, 20, 25, 30, 45], value=45,
                                   format_func=lambda m: f"{m} min", key="f-commute")
    return {"budget": budget, "areas": areas or None, "kind": kind, "max_commute": commute}


def explore_page():
    cohort, cl, res, ctx = engine()
    uid = me_id()
    me = my_profile(cohort)
    names = actions.name_lookup(cohort)
    state = session.state()["explore"]
    if state.get("open"):
        return listing_detail(state["open"], uid, names, ctx, cohort)
    page_head("Explore", "Flats, rooms and people, ranked by how well they fit you.")
    if me is None:
        need_quiz("Explore")
        return
    goal = actions.get_goal(uid)
    default = state.get("mode") or {"flat": "flat", "flatmates": "people"}.get(goal, "both")
    modes = list(MODES) if actions.my_group(uid) else [m for m in MODES if m != "group"]
    if default not in modes:
        default = "both"
    mode = st.segmented_control("Show", modes, format_func=MODES.get, default=default, key="explore-mode",
                                label_visibility="collapsed") or default
    state["mode"] = mode
    listings = store.load("listings")
    if mode == "people":
        return _people_mode(ctx, uid, names)
    if mode == "group":
        return _group_mode(ctx, uid, names, listings)
    if mode == "flat":
        f = _flat_filters(me)
        results = market.flat_results(ctx, uid, listings, **f)
    else:
        md("<p class='lede'>Flats with free rooms, and who else is interested in each.</p>")
        results = [r for r in market.flat_results(ctx, uid, listings, rank="people") if r["listing"]["kind"] == "room"
                   or len(market.free_rooms(r["listing"])) >= 2]
    if not results:
        empty("No flats match", "Widen the budget or commute, or pick more areas.")
        return
    md(f"<p class='fine'>{len(results)} flat{'s' if len(results) != 1 else ''}</p>")
    for r in results:
        _result_card(r, uid, names, ctx, show_interest=(mode == "both"))


# ---------------------------------------------------------------------------
# One flat
# ---------------------------------------------------------------------------
def listing_detail(lid, uid, names, ctx, cohort):
    li = store.get("listings", lid)
    if st.button("Back to results", icon=":material/arrow_back:", type="tertiary", key="back"):
        session.state()["explore"].pop("open", None)
        st.rerun()
    if not li or li["status"] != "approved":
        empty("This flat isn't listed any more", "Go back to see what's available.")
        return
    rf = market.room_fit(ctx, uid, li)
    free = market.free_rooms(li)
    me = market.person(ctx, uid)
    minutes = market.commute(li["area"], me["office_location"]) if me else None
    score = rf["score"] if rf else None
    label = (market.practical_label(min(r["rent"] for r in free), me["budget_min"], me["budget_max"], minutes)
             if me and free and not rf else None)
    md(f"""<div class='card-head'><div class='ch-main'>
          <h1 class='display sm'>{listing_title(li)}</h1>
          <p class='card-p'>{esc(li['address_hint'])}. {lister_sentence(li, names)}
          {f'{minutes} min to your office.' if minutes else ''}</p></div>
          {key_tag(score, title='Fit with the people living there') if rf else (chip(*label) if label else '')}</div>""")
    left, right = st.columns([3, 2], gap="large")
    with left:
        rows = ""
        for r in li["rooms"]:
            who = r.get("occupied_by")
            status = esc(names(who)) if who else chip("Free", "ok")
            rent = money(r["rent"]) if r["rent"] else "Owner's room"
            rows += (f"<tr><td>{r['room_id']}</td><td class='num'>{rent}</td>"
                     f"<td>{'Attached bath' if r['attached_bath'] else 'Shared bath'}, "
                     f"{'furnished' if r['furnished'] else 'unfurnished'}</td><td>{status}</td></tr>")
        md(f"<div class='panel'><h3 class='panel-h'>Rooms</h3><div class='grid-wrap'><table class='list'>"
           f"<thead><tr><th>Room</th><th class='num'>Rent</th><th>Details</th><th>Who's there</th></tr></thead>"
           f"<tbody>{rows}</tbody></table></div>"
           f"<p class='fine'>Deposit {li['deposit_months']} month{'s' if li['deposit_months'] != 1 else ''}. "
           f"Available from {date.fromisoformat(li['available_from']).strftime('%d %B %Y').lstrip('0')}. "
           f"House rules: {rules_sentence(li)}</p></div>")
        if rf and me:
            live = [market.person(ctx, o) for o, _ in rf["with"]]
            md(f"<div class='panel'><h3 class='panel-h'>You'd live with {join_and(esc(first(p['name'])) for p in live)}</h3>"
               + habit_grid([me] + live, uid) + "</div>")
            low = rf["lowest"]
            if low and low[2]:
                t, mine, theirs = low[2]
                st.warning(f"You and {first(names(low[0]))} differ on {TRAIT_SHORT[t]}: you said {lc(mine)}, "
                           f"{first(names(low[0]))} said {lc(theirs)}. Worth talking about before you move in.",
                           icon=":material/info:")
        elif any(not market.in_cohort(ctx, o) for o in market.residents(li)):
            md("<p class='fine'>The owner lives here too. They haven't answered the lifestyle questions.</p>")
    with right:
        g = actions.my_group(uid)
        interested = market.interested_people(ctx, uid, li)
        with st.container(key="interest-panel"):
            md(f"<h3 class='panel-h'>Also interested</h3>"
               f"<p class='fine'>{len(interested)} {'person' if len(interested) == 1 else 'people'} "
               f"who fit your dealbreakers.</p>")
            for pid, s in interested:
                p = market.person(ctx, pid)
                in_group = g and pid in g["member_ids"]
                with st.container(horizontal=True, vertical_alignment="center", key=f"int-{pid}"):
                    md(f"<div class='person slim'>{avatar(p['name'])}<div class='who'><div class='n'>"
                       f"{esc(p['name'])}</div><div class='m'>{esc(p['organisation'])}, {esc(p['office_location'])}"
                       f"</div></div>{key_tag(s)}</div>")
                    if in_group:
                        md(chip("In your group", "ok"))
        mine = uid in li.get("interested", [])
        with st.container(horizontal=True, gap="small", key="detail-actions"):
            if st.button("Remove my interest" if mine else "I'm interested", key="interest"):
                actions.mark_interested(lid, uid, not mine)
                st.rerun()
            if g and (g.get("anchored_listing_id") == lid or lid in g["shortlist"]):
                app = next((a for a in actions.open_applications(lid) if a.get("group_id") == g["id"]), None)
                if app:
                    md(chip("Your group has applied", "ok"))
                elif len(free) >= len(g["member_ids"]) and st.button("Apply as a group", type="primary"):
                    a, err = actions.apply(lid, g["member_ids"], group_id=g["id"])
                    if err:
                        st.error(err)
                    else:
                        session.flash(f"Applied as a group for rooms {', '.join(a['room_ids'])}. "
                                      f"{first(names(li['owner_id']))} will see your group's fit.")
                        session.state()["explore"].pop("open", None)
                        nav.go("group")
                if st.button("Go to my group"):
                    nav.go("group")
            elif g and len(free) >= len(g["member_ids"]):
                if st.button("Shortlist for my group"):
                    actions.shortlist(g["id"], lid)
                    session.flash("Shortlisted for your group.")
                    nav.go("group")
            elif free and me:
                if st.button("Apply for a room on my own"):
                    app, err = actions.apply(lid, [uid])
                    if err:
                        st.error(err)
                    else:
                        session.flash(f"Applied for room {app['room_ids'][0]}. The lister will see your fit "
                                      "with the people living there.")
                        st.rerun()
        with st.popover("Report this listing", icon=":material/flag:"):
            reason = st.text_area("What's wrong?", placeholder="For example: asked for money before a visit.",
                                  key="report-reason")
            if st.button("Send report", key="report-send"):
                if not reason.strip():
                    st.error("Say what's wrong so an admin can check it.")
                else:
                    actions.report_listing(lid, uid, reason)
                    st.success("Sent. An admin will review this listing.")


# ---------------------------------------------------------------------------
# My group
# ---------------------------------------------------------------------------
def tenancy_block(t, uid, names, key):
    """House agreement + signing (simulated), shared by My group and Rent."""
    md(f"<div class='label'>House agreement {src_tag(t['agreement_source'])}</div>")
    with st.container(key=f"agreement-{key}"):
        st.markdown(t["agreement_text"])
    signers = [m["member_id"] for m in t["members"]]
    with st.container(key=f"sign-{key}"):
        md("<h3 class='panel-h'>Signatures</h3><p class='fine'>Signing is simulated for the demo.</p>")
        for m in signers:
            with st.container(horizontal=True, vertical_alignment="center", key=f"sig-{key}-{m}"):
                md(f"<p class='cont-p'>{esc(names(m))}</p>")
                if m in t["signed"]:
                    md(chip("Signed", "ok"))
                elif st.button("Sign" if m == uid else f"Sign for {first(names(m))}", key=f"signbtn-{key}-{m}"):
                    actions.sign(t["id"], m)
                    st.rerun()
    st.download_button("Download agreement", t["agreement_text"], file_name=f"nestmate_agreement_{t['id']}.md",
                       icon=":material/download:", key=f"dl-{key}")


def _find_flats():
    session.state()["explore"] = {"mode": "group"}


def group_page():
    cohort, cl, res, ctx = engine()
    uid = me_id()
    names = actions.name_lookup(cohort)
    g = actions.my_group(uid)
    if not g:
        page_head("My group")
        empty("No group yet", "Accept one of your suggested flat groups. "
              "Your group, its flats and your house agreement will appear here.")
        with st.container(horizontal=True, gap="small"):
            if st.button("See flat groups", type="primary"):
                nav.go("matches")
            if st.button("Explore flats"):
                nav.go("explore")
        return
    d = market.describe(ctx, g["member_ids"])
    d["target"] = g["target_size"]
    status = {"forming": ("Forming", ""), "applied": ("Applied for a flat", "warn"), "housed": ("Has a flat", "ok")}
    text, kind = status[g["status"]]
    page_head(f"Your {len(g['member_ids'])}-person group", group_sentence(d) + f" {chip(text, kind)}")
    with st.container(key="group-card"):
        group_card(d, uid)
        md(people_row([market.person(ctx, m) for m in g["member_ids"]], uid,
                      note=lambda p: chip("Accepted, simulated", "") if p["id"] != uid else ""))

    listings = {li["id"]: li for li in store.load("listings")}
    apps = [a for a in store.load("applications") if a.get("group_id") == g["id"]]
    tenancy = next((t for t in store.load("tenancies") if t.get("application_id") in {a["id"] for a in apps}), None)
    if tenancy:
        li = listings[tenancy["listing_id"]]
        md(f"<h2 class='sec-h'>Your flat: {listing_title(li)}</h2>")
        rooms = ", ".join(f"{esc(first(names(m['member_id'])))} in {m['room_id']} ({money(m['rent_share'])})"
                          for m in tenancy["members"])
        md(f"<p class='lede'>{rooms}. Moving in on "
           f"{date.fromisoformat(tenancy['start_date']).strftime('%d %B %Y').lstrip('0')}.</p>")
        tenancy_block(tenancy, uid, names, "group")
        if st.button("Go to rent", type="primary", icon=":material/payments:"):
            nav.go("rent")
        return

    md("<h2 class='sec-h'>Flats for this group</h2>")
    short = [listings[lid] for lid in g["shortlist"] if lid in listings]
    if not short:
        md("<p class='lede'>No flats shortlisted yet. Find flats with enough free rooms for all of you.</p>")
    for li in short:
        app = next((a for a in apps if a["listing_id"] == li["id"] and a["status"] != "rejected"), None)
        with st.container(key=f"short-{li['id']}", horizontal=True, vertical_alignment="center"):
            enough = len(market.free_rooms(li)) >= len(g["member_ids"])
            md(f"<div class='ch-main'><h3 class='card-h'>{listing_title(li)}</h3><p class='card-p'>"
               f"{len(market.free_rooms(li))} free rooms from {money(min([r['rent'] for r in market.free_rooms(li)] or [0]))}."
               f" {lister_sentence(li, names)}</p></div>")
            if app:
                label = {"sent": "Applied, waiting for the lister", "visit_booked": f"Visit booked: {app['visit_slot']}",
                         "accepted": "Accepted"}[app["status"]]
                md(chip(esc(label), "ok" if app["status"] != "sent" else "warn"))
            elif not enough:
                md(chip("Not enough free rooms", "warn"))
            elif st.button("Apply as a group", type="primary", key=f"apply-{li['id']}"):
                a, err = actions.apply(li["id"], g["member_ids"], group_id=g["id"])
                if err:
                    st.error(err)
                else:
                    session.flash(f"Applied as a group for rooms {', '.join(a['room_ids'])}. "
                                  f"{first(names(li['owner_id']))} will see your group's fit.")
                    st.rerun()
    rejected = [a for a in apps if a["status"] == "rejected"]
    for a in rejected:
        md(f"<p class='fine'>{listing_title(listings[a['listing_id']])}: declined. {esc(a.get('reason', ''))}</p>")
    with st.container(horizontal=True, gap="small", key="group-actions"):
        if st.button("Find flats for us", type="primary", icon=":material/search:"):
            _find_flats()
            nav.go("explore")
        if st.button("Leave group", type="tertiary"):
            actions.leave_group(uid, g["id"])
            session.flash("You left the group.")
            st.rerun()


# ---------------------------------------------------------------------------
# My listings
# ---------------------------------------------------------------------------
def _listing_form(uid, names):
    with st.container(key="listing-form"):
        md("<h2 class='step-h'>List a space</h2>")
        kind = st.pills("What are you listing?", list(LISTING_KINDS), format_func=LISTING_KINDS.get, key="lf-kind")
        situations = ["owner_away"] if kind == "whole_flat" else list(LISTER_TYPES)
        situation = st.pills("What's your situation?", situations, format_func=LISTER_TYPES.get, key="lf-sit")
        if not (kind and situation):
            md("<p class='hint'>Answer these two first. The rest of the form depends on them.</p>")
            return
        lives_there = situation in ("owner_lives_here", "tenant_spare_room")
        c1, c2 = st.columns(2, gap="medium")
        area = c1.selectbox("Area", [a["area"] for a in AREAS], key="lf-area")
        hint = c2.text_input("Where exactly, roughly", placeholder="Near Inorbit Mall, 2nd floor", key="lf-hint",
                             help="Don't enter the full address. Share it after a visit is booked.")
        bhk = st.segmented_control("Size", [1, 2, 3, 4], format_func=lambda n: f"{n}BHK", default=2, key="lf-bhk")
        bhk = bhk or 2
        avg = market.area_rent(area)
        if kind == "whole_flat":
            n_let = bhk
        else:
            most = bhk - 1 if lives_there else bhk
            if most < 1:
                st.error("A 1BHK has no spare room if you live there. Pick a bigger size.")
                return
            n_let = st.segmented_control("Rooms to let", list(range(1, most + 1)), default=1, key="lf-nlet") or 1
        md(f"<p class='hint'>Rooms in {esc(area)} usually go for about {money(avg)} a month each.</p>")
        rooms = []
        for i in range(n_let):
            c1, c2, c3 = st.columns([2, 1, 1], gap="small", vertical_alignment="bottom")
            rent = c1.number_input(f"Room {i + 1} rent (₹ a month)", 2000, 60000, avg, step=500, key=f"lf-rent-{i}")
            bath = c2.checkbox("Attached bath", key=f"lf-bath-{i}")
            furn = c3.checkbox("Furnished", value=True, key=f"lf-furn-{i}")
            rooms.append({"rent": int(rent), "attached_bath": bath, "furnished": furn, "occupied_by": None})
        landlord_on_app, upi = True, ""
        if lives_there:
            own = 0
            if situation == "tenant_spare_room":
                own = st.number_input("Your own rent share (₹ a month)", 2000, 60000, avg, step=500, key="lf-own")
                landlord_on_app = st.pills("Is your landlord on Nestmate?", ["Yes", "No"], default="No",
                                           key="lf-landlord") == "Yes"
                if not landlord_on_app:
                    upi = st.text_input("Landlord's UPI ID", placeholder="name@bank", key="lf-upi",
                                        help="Your new flatmate pays their rent share straight to this ID.")
            rooms.insert(0, {"rent": int(own), "attached_bath": True, "furnished": True, "occupied_by": uid})
            md("<p class='hint'>You live here, so people looking at this room see how well they'd fit with you.</p>")
        c1, c2 = st.columns(2, gap="medium")
        deposit = c1.segmented_control("Deposit", [1, 2, 3], format_func=lambda n: f"{n} month{'s' if n > 1 else ''}",
                                       default=2, key="lf-dep") or 2
        avail = c2.date_input("Available from", date(2027, 7, 1), min_value=date(2027, 5, 1), key="lf-date")
        gender = st.pills("Who can live here?", list(LISTING_GENDER), format_func=LISTING_GENDER.get, default="any",
                          key="lf-gender") or "any"
        with st.container(horizontal=True, gap="medium"):
            veg = st.checkbox("Veg-only kitchen", key="lf-veg")
            nosmoke = st.checkbox("No smoking", key="lf-smoke")
            nodrink = st.checkbox("No drinking", key="lf-drink")
            guests = st.checkbox("Guests welcome", value=True, key="lf-guests")
        if st.button("Send for review", type="primary", key="lf-submit"):
            if not hint.strip():
                st.error("Add a rough location, like a landmark, so people can judge the commute.")
                return
            if not landlord_on_app and not UPI_RE.match(upi.strip()):
                st.error("Enter the landlord's UPI ID, like name@bank, so your flatmate can pay rent.")
                return
            for i, r in enumerate(rooms, 1):
                r["room_id"] = f"R{i}"
            nearest = min(next(a for a in AREAS if a["area"] == area)["commute"].items(), key=lambda x: (x[1], x[0]))[0]
            li = actions.create_listing(uid, {
                "kind": kind, "lister_type": situation, "area": area, "address_hint": hint.strip(),
                "office_nearest": nearest, "bhk": bhk, "rooms": [{"room_id": r.pop("room_id"), **r} for r in rooms],
                "deposit_months": deposit, "available_from": avail.isoformat(),
                "rules": {"gender": gender, "veg_only": veg, "no_smoking": nosmoke, "no_drinking": nodrink,
                          "guests_ok": guests},
                "occupants": [uid] if lives_there else [], "landlord_on_app": landlord_on_app,
                "landlord_upi": upi.strip()})
            session.state()["listing_form"] = False
            session.flash(f"Sent {li['id']} for review. It shows in Explore once an admin approves it.")
            st.rerun()


def _application_card(a, li, ctx, names, uid):
    members = actions.applicants_of(a)
    view = market.applicant_view(ctx, li, members)
    who = join_and(esc(names(m)) for m in members)
    kind = f"applying as a group for rooms {', '.join(a['room_ids'])}" if a.get("group_id") else \
        f"applying for room {a['room_ids'][0]}"
    status = {"sent": ("New", "warn"), "visit_booked": (f"Visit {esc(a.get('visit_slot') or '')}", ""),
              "accepted": ("Accepted", "ok"), "rejected": ("Declined", "")}[a["status"]]
    basis = {"group": "Fit of everyone who'd live there", "practical": "", None: ""}[view["basis"]]
    tag = chip(*view["label"]) if view["basis"] == "practical" else key_tag(view["score"], title=basis)
    reasons = "".join(f"<li>{esc(r)}</li>" for r in view["reasons"])
    clash = f"<p class='warnline'>One to talk about: {esc(view['clash'])}.</p>" if view["clash"] else ""
    with st.container(key=f"app-{a['id']}"):
        md(f"""<div class='card-head'><div class='ch-main'>
              <h3 class='card-h'>{who} {chip(status[0], status[1])}</h3>
              <p class='card-p'>{kind.capitalize()}.</p>
              <ul class='reasons'>{reasons}</ul>{clash}</div>
              {tag}</div>""")
        known = [market.person(ctx, m) for m in dict.fromkeys(members + market.residents(li))
                 if market.in_cohort(ctx, m)]
        if len(known) >= 2:
            md(habit_grid(known))
        if a["status"] in ("sent", "visit_booked"):
            with st.container(horizontal=True, gap="small", key=f"appact-{a['id']}"):
                with st.popover("Book a visit" if a["status"] == "sent" else "Change visit", icon=":material/event:"):
                    slot = st.pills("Pick a slot", VISIT_SLOTS, key=f"slot-{a['id']}",
                                    default=a.get("visit_slot"))
                    if st.button("Book this slot", key=f"book-{a['id']}", type="primary", disabled=not slot):
                        actions.book_visit(a["id"], slot)
                        session.flash(f"Booked a visit for {slot}.")
                        st.rerun()
                if st.button("Accept", type="primary", key=f"acc-{a['id']}"):
                    with st.spinner("Creating the tenancy and writing the house agreement…"):
                        t, err = actions.accept_application(ctx, a["id"])
                    if err:
                        st.error(err)
                    else:
                        session.flash(f"Accepted {who.replace('&amp;', '&')}. The tenancy is created and the house "
                                      "agreement is ready to sign.")
                        st.rerun()
                if st.button("Decline", key=f"dec-{a['id']}"):
                    actions.reject_application(a["id"], "The lister declined.")
                    st.rerun()


def listings_page():
    cohort, cl, res, ctx = engine()
    uid = me_id()
    names = actions.name_lookup(cohort)
    mine = [li for li in store.load("listings") if li["owner_id"] == uid]
    form_open = session.state().get("listing_form", not mine)
    page_head("My listings", "Flats and rooms you've listed, and the people who applied, best fit first.")
    if not form_open:
        if st.button("List a space", icon=":material/add_home:", type="primary" if not mine else "secondary"):
            session.state()["listing_form"] = True
            st.rerun()
    else:
        _listing_form(uid, names)
        if mine and st.button("Close the form", type="tertiary"):
            session.state()["listing_form"] = False
            st.rerun()
    if not mine:
        return
    apps = store.load("applications")
    status_txt = {"pending": ("Waiting for review", "warn"), "approved": ("Live", "ok"),
                  "rejected": ("Rejected", "warn"), "removed": ("Removed by an admin", "warn")}
    for li in mine:
        s, k = status_txt[li["status"]]
        mine_apps = [a for a in apps if a["listing_id"] == li["id"]]
        open_apps = [a for a in mine_apps if a["status"] in ("sent", "visit_booked")]
        with st.container(key=f"mylist-{li['id']}"):
            md(f"<h2 class='card-h big'>{listing_title(li)} {chip(s, k)}</h2>"
               f"<p class='card-p'>{esc(li['address_hint'])}. {len(market.free_rooms(li))} of {len(li['rooms'])} "
               f"rooms free. {len(li.get('interested', []))} interested, {len(open_apps)} "
               f"application{'s' if len(open_apps) != 1 else ''} waiting.</p>"
               + (f"<p class='warnline'>Reason: {esc(li['review_reason'])}</p>" if li.get("review_reason") else ""))
            rows = "".join(f"<tr><td>{r['room_id']}</td><td class='num'>{money(r['rent']) if r['rent'] else 'Yours'}</td>"
                           f"<td>{esc(names(r['occupied_by'])) if r.get('occupied_by') else chip('Free', 'ok')}</td></tr>"
                           for r in li["rooms"])
            md(f"<div class='grid-wrap'><table class='list'><thead><tr><th>Room</th><th class='num'>Rent</th>"
               f"<th>Who's there</th></tr></thead><tbody>{rows}</tbody></table></div>")
        order = sorted(mine_apps, key=lambda a: (a["status"] not in ("sent", "visit_booked"),
                                                 -(lambda v: v["score"] or v.get("rank") or 0)(market.applicant_view(ctx, li, actions.applicants_of(a)))))
        if order:
            md(f"<h3 class='sec-h small'>Applicants for {li['id']}, best fit first</h3>")
        for a in order:
            _application_card(a, li, ctx, names, uid)


# ---------------------------------------------------------------------------
# Rent
# ---------------------------------------------------------------------------
@st.dialog("Pay your rent share")
def checkout(payment, payee):
    md(f"<p class='demo-note'>Demo payment, no money moves.</p>"
       f"<p class='lede'>{money(payment['amount'])} for {month_name(payment['month'])}, to {esc(payee)}.</p>")
    method = st.pills("Pay with", ["UPI", "Card"], default="UPI", key="pay-method") or "UPI"
    if method == "UPI":
        st.text_input("Your UPI ID", placeholder="name@bank", key="pay-upi")
    else:
        st.text_input("Card number", placeholder="4111 1111 1111 1111", key="pay-card")
        c1, c2 = st.columns(2)
        c1.text_input("Expiry", placeholder="MM/YY", key="pay-exp")
        c2.text_input("CVV", placeholder="123", type="password", key="pay-cvv")
    if st.button(f"Pay {money(payment['amount'])}", type="primary", width="stretch", key="pay-go"):
        p = actions.pay(payment["id"], method)
        session.flash(f"Paid {money(p['amount'])} by {method}. Receipt {p['receipt_no']}.")
        st.rerun()


def _payee(li, names):
    if li["lister_type"] == "tenant_spare_room" and not li.get("landlord_on_app"):
        return f"the landlord's UPI ID {li['landlord_upi']}"
    if li["lister_type"] == "tenant_spare_room":
        return "the landlord"
    return names(li["owner_id"])


def _bills(t, uid, names):
    house = actions.household(t)
    bills = [e for e in store.load("expenses") if e["tenancy_id"] == t["id"]]
    md("<h2 class='sec-h'>Shared bills</h2><p class='lede'>Add a bill you paid. It's split equally, and the list "
       "below shows who owes whom.</p>")
    with st.form(f"bill-{t['id']}", border=False):
        c1, c2, c3 = st.columns([2, 1, 2], vertical_alignment="bottom")
        label = c1.text_input("What for", placeholder="Electricity, June")
        amount = c2.number_input("Amount (₹)", 0, 100000, 0, step=100)
        payer = c3.selectbox("Paid by", house, index=house.index(uid) if uid in house else 0, format_func=names)
        if st.form_submit_button("Add bill"):
            if not label.strip() or amount <= 0:
                st.error("Enter what the bill was for and an amount above zero.")
            else:
                actions.add_expense(t["id"], label, amount, payer, house)
                session.flash(f"Added {label.strip()}, {money(amount)}, split {len(house)} ways.")
                st.rerun()
    if bills:
        rows = "".join(f"<tr><td>{esc(e['label'])}</td><td class='num'>{money(e['amount'])}</td>"
                       f"<td>Paid by {esc(first(names(e['paid_by'])))}, split {len(e['split_between'])} ways</td></tr>"
                       for e in bills)
        md(f"<div class='grid-wrap'><table class='list'><tbody>{rows}</tbody></table></div>")
        owes = market.settle(bills, house)
        lines = "".join(f"<li><b>{esc(first(names(d)))}</b> owes <b>{esc(first(names(c)))}</b> {money(a)}</li>"
                        for d, c, a in owes) or "<li>Everyone is settled up.</li>"
        md(f"<ul class='owes'>{lines}</ul>")


def rent_page():
    cohort, cl, res, ctx = engine()
    uid = me_id()
    names = actions.name_lookup(cohort)
    as_tenant = actions.tenancies_for_member(uid)
    as_lister = actions.tenancies_for_lister(uid)
    page_head("Rent", "Your share each month, who has paid, and shared bills.")
    if not as_tenant and not as_lister:
        empty("No rent yet", "Rent shows up here once a lister accepts you, or once you accept a tenant.")
        if st.button("Explore flats", type="primary"):
            nav.go("explore")
        return
    payments = store.load("payments")
    listings = {li["id"]: li for li in store.load("listings")}
    for t in as_tenant:
        li = listings[t["listing_id"]]
        tp = [p for p in payments if p["tenancy_id"] == t["id"]]
        month = tp[0]["month"] if tp else t["start_date"][:7]
        mine = next((p for p in tp if p["member_id"] == uid), None)
        paid = sum(p["amount"] for p in tp if p["status"] == "paid")
        total = sum(p["amount"] for p in tp)
        md(f"<h2 class='sec-h'>{listing_title(li)}, {month_name(month)}</h2>")
        stats([("Your share", money(mine["amount"]) if mine else "None"),
               ("Status", "Paid" if mine and mine["status"] == "paid" else "Due"),
               ("Collected for the flat", f"{money(paid)} of {total:,}"),
               ("Pays to", esc(_payee(li, names)))])
        rows = "".join(f"<tr><td>{esc(names(p['member_id']))}</td><td class='num'>{money(p['amount'])}</td>"
                       f"<td>{chip('Paid', 'ok') if p['status'] == 'paid' else chip('Due', 'warn')}</td>"
                       f"<td>{esc(p['receipt_no'] or '')}</td></tr>" for p in tp)
        md(f"<div class='grid-wrap'><table class='list'><thead><tr><th>Who</th><th class='num'>Share</th><th>Status</th>"
           f"<th>Receipt</th></tr></thead><tbody>{rows}</tbody></table></div>")
        if mine and mine["status"] == "due":
            if st.button(f"Pay {money(mine['amount'])}", type="primary", key=f"pay-{mine['id']}",
                         icon=":material/payments:"):
                checkout(mine, _payee(li, names))
        with st.expander("House agreement"):
            tenancy_block(t, uid, names, f"rent-{t['id']}")
        _bills(t, uid, names)

    if as_lister:
        md("<h2 class='sec-h'>Rent from your tenants</h2>")
        for t in as_lister:
            li = listings[t["listing_id"]]
            tp = [p for p in payments if p["tenancy_id"] == t["id"]]
            paid = sum(p["amount"] for p in tp if p["status"] == "paid")
            total = sum(p["amount"] for p in tp)
            month = tp[0]["month"] if tp else t["start_date"][:7]
            stats([("Listing", listing_title(li)), ("Month", month_name(month)),
                   ("Collected", f"{money(paid)} of {total:,}"),
                   ("Still due", str(sum(p["status"] == "due" for p in tp)))])
            rows = "".join(f"<tr><td>{esc(names(p['member_id']))}</td>"
                           f"<td>{next(m['room_id'] for m in t['members'] if m['member_id'] == p['member_id'])}</td>"
                           f"<td class='num'>{money(p['amount'])}</td>"
                           f"<td>{chip('Paid', 'ok') if p['status'] == 'paid' else chip('Due', 'warn')}</td>"
                           f"<td>{esc(p['receipt_no'] or '')}</td></tr>" for p in tp)
            md(f"<div class='grid-wrap'><table class='list'><thead><tr><th>Tenant</th><th>Room</th>"
               f"<th class='num'>Share</th><th>Status</th><th>Receipt</th></tr></thead><tbody>{rows}</tbody></table></div>")
            if li["lister_type"] == "tenant_spare_room" and not li.get("landlord_on_app"):
                md(f"<p class='fine'>Your flatmate pays their share straight to your landlord's UPI ID "
                   f"{esc(li['landlord_upi'])}.</p>")
            with st.expander("House agreement"):
                tenancy_block(t, uid, names, f"lister-{t['id']}")
