"""
Member routes that are about YOU: home, flat groups (the deck), profile and
the lifestyle quiz (onboarding and "Your answers").

Members never see cohort-wide statistics or other people's data beyond the
people suggested to them or interested in the same flat. That view belongs
to the admin routes. Marketplace routes (explore, group, listings, rent) are
in ui/market_pages.py.
"""
import streamlit as st

from core import actions, llm, market, store
from core.encode import dealbreaker_list, save_signup
from core.schema import DEALBREAKERS, GENDER_MIX_UI, QUESTION_UI, TRAIT_SHORT, TRAITS
from ui import nav, session
from ui.components import (areas_list, avatar, chip, choice, empty, engine, esc, first, habit_grid, key_tag,
                           kv_table, md, money, month_name, page_head, people_row, persona_label, src_tag)
from ui.quiz import quiz


# ---------------------------------------------------------------------------
# Who is looking
# ---------------------------------------------------------------------------
def me_id():
    return session.account()["user_id"]


def my_profile(cohort):
    """The logged-in member's cohort row, or None if they haven't done the quiz."""
    rows = cohort[cohort["id"] == me_id()]
    return rows.iloc[0].to_dict() if len(rows) else None


def need_quiz(what):
    """Empty state for pages that need lifestyle answers."""
    empty("Answer the lifestyle quiz first",
          f"{what} uses your answers about sleep, cleanliness, guests and food. It takes about two minutes.")
    if st.button("Answer the lifestyle quiz", type="primary", key="need-quiz"):
        nav.go("onboarding")


# ---------------------------------------------------------------------------
# Home: what do you need?
# ---------------------------------------------------------------------------
HOME_OPTIONS = {
    "both": ("Find a flat and flatmates", "I have neither.", "Show flats and people"),
    "flat": ("Find a flat", "I just need a place.", "Show flats and rooms"),
    "flatmates": ("Find flatmates", "I want people first, or my friends and I want to move together.",
                  "Show flatmates"),
    "list": ("List a space", "I have a flat or a room to rent out.", "List a space"),
}


def explore_defaults(goal):
    """Where Explore starts for each Home goal. Only a starting point: the person
    can change any of it, and their choices are kept for the session."""
    if goal == "flat":
        return {"tab": "Flats", "sort": "practical", "share": False}
    if goal == "flatmates":
        return {"tab": "People", "sort": "people", "share": True}
    return {"tab": "Flats", "sort": "people", "share": True}


def _choose(goal, has_profile):
    actions.set_goal(me_id(), goal)
    session.state()["explore"] = explore_defaults(goal)
    if goal == "list":
        session.state()["listing_form"] = True
        nav.go("listings")
    if not has_profile:
        session.flash("Answer a few questions first, so we can show who and what fits you.")
        nav.go("onboarding")
    nav.go("explore")


def _option(goal, has_profile, primary=False):
    title, line, button = HOME_OPTIONS[goal]
    with st.container(key=f"opt-{goal}{'-primary' if primary else ''}"):
        md(f"<h2 class='opt-h'>{title}</h2><p class='opt-p'>{line}</p>")
        if st.button(button, key=f"go-{goal}", type="primary" if primary else "secondary",
                     width="stretch" if not primary else "content"):
            _choose(goal, has_profile)


def _continue_items(cohort, ctx):
    uid = me_id()
    names = actions.name_lookup(cohort)
    items = []
    g = actions.my_group(uid)
    if g:
        others = [first(names(m)) for m in g["member_ids"] if m != uid]
        what = {"forming": "Your group is forming", "applied": "Your group has applied for a flat",
                "housed": "Your group has a flat"}[g["status"]]
        items.append((f"{what}, with {', '.join(others)}.", "Open my group", "group"))
    apps = [a for a in store.load("applications") if a.get("applicant") == uid and a["status"] in ("sent", "visit_booked")]
    for a in apps:
        li = store.get("listings", a["listing_id"])
        status = f"visit booked for {a['visit_slot']}" if a["status"] == "visit_booked" else "waiting for the lister"
        items.append((f"Your application for a room in {li['area']}: {status}.", "Explore flats", "explore"))
    due = [p for p in store.load("payments") if p["member_id"] == uid and p["status"] == "due"]
    for p in due:
        items.append((f"Rent of {money(p['amount'])} is due for {month_name(p['month'])}.", f"Pay {money(p['amount'])}",
                      "rent"))
    mine = [li for li in store.load("listings") if li["owner_id"] == uid]
    waiting = [a for a in store.load("applications") if a["listing_id"] in {li["id"] for li in mine}
               and a["status"] in ("sent", "visit_booked")]
    if waiting:
        n = len(waiting)
        items.append((f"{n} application{'s' if n > 1 else ''} waiting on your listing{'s' if len(mine) > 1 else ''}.",
                      "Review applicants", "listings"))
    pending = [li for li in mine if li["status"] == "pending"]
    if pending and not waiting:
        items.append((f"Your listing in {pending[0]['area']} is waiting for review.", "Open my listings", "listings"))
    return items


def home_page():
    cohort, cl, res, ctx = engine()
    acc = session.account()
    has_profile = my_profile(cohort) is not None
    page_head(f"Hi {esc(first(acc['name']))}. What do you need in Hyderabad?",
              "Pick one to start. One account can do all of these, so you can come back for the others.")
    _option("both", has_profile, primary=True)
    cols = st.columns(3, gap="medium")
    for col, goal in zip(cols, ("flat", "flatmates", "list")):
        with col:
            _option(goal, has_profile)

    items = _continue_items(cohort, ctx)
    if items:
        with st.container(key="continue"):
            md("<h2 class='sec-h'>Continue where you left off</h2>")
            for n, (text, button, route) in enumerate(items):
                with st.container(horizontal=True, vertical_alignment="center", key=f"cont-{n}"):
                    md(f"<p class='cont-p'>{esc(text)}</p>")
                    if st.button(button, key=f"cont-btn-{n}"):
                        nav.go(route)


# ---------------------------------------------------------------------------
# Lifestyle quiz: onboarding and "Your answers"
# ---------------------------------------------------------------------------
def onboarding_page():
    cohort, *_ = engine()
    acc = session.account()
    page_head(f"Nice to meet you, {esc(first(acc['name']))}.",
              "Four short steps. Honest answers make better flatmates, and only the people you match with "
              "see them.")
    if quiz(my_profile(cohort) or {}, "onboarding", "Save and see my flat groups"):
        session.flash("Saved your answers. These are the flat groups that fit you best.")
        nav.go("matches")


def answers_page():
    cohort, *_ = engine()
    me = my_profile(cohort)
    if me is None:
        page_head("Your answers")
        need_quiz("Your answers")
        return
    page_head("Your answers", "Change anything. Your flat groups and fit scores update as soon as you save.")
    if quiz(me, "edit", "Save changes"):
        session.flash("Saved your changes. Your flat groups are updated.")
        nav.go("matches")


# ---------------------------------------------------------------------------
# Flat groups: decide on whole groups, not individual people
# ---------------------------------------------------------------------------
def group_key(g):
    return "|".join(sorted(g["member_ids"]))


def group_sentence(g):
    lo, hi = g["budget"]
    return (f"{esc(persona_label(g['persona']))}. Budget {money(lo)}–{hi:,} each, "
            f"working in {esc(' and '.join(g['offices']) if len(g['offices']) < 3 else ', '.join(g['offices']))}.")


def group_card(g, me, head_extra="", people_controls=None):
    """Title, sentence, status, key tag, people, habit grid, explanation, areas.
    people_controls: optional function that draws the people with buttons."""
    open_spots = g["target"] - g["size"]
    status = chip(f"{open_spots} spot open", "warn") if open_spots > 0 else chip("Full flat", "ok")
    md(f"""<div class='card-head'><div class='ch-main'>
          <h2 class='card-h'>{g['size']}-person flat {status}</h2>
          <p class='card-p'>{group_sentence(g)}</p>{head_extra}</div>
          {key_tag(g['score'])}</div>""")
    if people_controls:
        people_controls()
    else:
        md(people_row(g["members"], me))
    md(habit_grid(g["members"], me))
    left, right = st.columns([3, 2], gap="large")
    with left:
        text, src = llm.explain_group(g)
        md(f"<div class='label'>Why it works and what to agree on {src_tag(src)}</div>")
        with st.container(key=f"explain-{group_key(g)}"):
            st.markdown(text)
    with right:
        areas, summary, src = llm.suggest_areas(g)
        md(f"<div class='label'>Areas to look in {src_tag(src)}</div>{areas_list(areas)}"
           f"<p class='fine'>{esc(summary)}</p>")


def _accept(g, uid, key):
    actions.create_group(uid, g["member_ids"], g["target"])
    session.state()["decisions"][key] = "accepted"
    session.flash("Accepted the group. Other members' acceptance is simulated for the demo.")


def _keep(pid):
    kept = session.state().setdefault("kept_people", [])
    if pid not in kept:
        kept.append(pid)


def _pass_person(key, members, pid, uid, ctx, names):
    """Pass on one person: swap in the next best fit for everyone who stays."""
    state = session.state()
    passed = state.setdefault("passed_people", [])
    if pid not in passed:
        passed.append(pid)
    rest = [m for m in members if m != pid]
    nxt = market.next_best_person(ctx, rest, exclude=passed)
    if nxt:
        state.setdefault("group_edits", {})[key] = [nxt[0] if m == pid else m for m in members]
        st.toast(f"Passed on {first(names(pid))}. {first(names(nxt[0]))} is the next best fit ({nxt[1]:.0f}%).")
    elif len(rest) >= 2:
        state.setdefault("group_edits", {})[key] = rest
        st.toast(f"Passed on {first(names(pid))}. Nobody else fits this group, so it has one spot open.")
    else:
        passed.remove(pid)
        st.toast("Nobody else fits you right now, so this person stays.")


def _people_controls(g, uid, key, ctx, names):
    """Each person in the group with Accept and Pass (you're shown first, no buttons)."""
    kept = session.state().setdefault("kept_people", [])
    members = g["member_ids"]
    cols = st.columns(len(members), gap="medium")
    for col, m in zip(cols, sorted(g["members"], key=lambda p: p["id"] != uid)):
        with col, st.container(key=f"pp-{m['id']}"):
            md(people_row([m], uid))
            if m["id"] == uid:
                continue
            if m["id"] in kept:
                md(chip("Accepted", "ok"))
                continue
            with st.container(horizontal=True, gap="small"):
                st.button("Accept", key=f"keep-{m['id']}", icon=":material/check:", on_click=_keep, args=(m["id"],))
                st.button("Pass", key=f"swap-{m['id']}", icon=":material/close:",
                          on_click=_pass_person, args=(key, members, m["id"], uid, ctx, names))


# WHY not @st.fragment: a fragment re-run drops the page's injected stylesheet
# (st.html <style> lives outside the fragment), leaving the page unstyled.
# A full re-run is quick because the matching is cached.
def _deck(deck, uid, ctx, names):
    state = session.state()
    decisions = state["decisions"]
    pending = [g for g in deck if group_key(g) not in decisions]
    if not pending:
        empty("You've seen every suggestion for now",
              "New people join the cohort every week. Start over to see these groups again, or explore flats.")
        st.button("Start over", icon=":material/restart_alt:",
                  on_click=lambda: state.update(decisions={}, group_edits={}, passed_people=[], kept_people=[]))
        return
    g0 = pending[0]
    key = group_key(g0)
    members = state.setdefault("group_edits", {}).get(key, g0["member_ids"])
    # After a swap, rebuild the card from the engine (score, grid, explanation).
    g = g0 if members == g0["member_ids"] else {**market.describe(ctx, members), "target": g0["target"]}
    with st.container(key="group-card"):
        group_card(g, uid, head_extra=f"<p class='fine'>Suggestion {deck.index(g0) + 1} of {len(deck)}. "
                                      f"Accept or pass on each person; we'll swap in the next best fit.</p>",
                   people_controls=lambda: _people_controls(g, uid, key, ctx, names))
        with st.container(horizontal=True, gap="small", key="card-actions", vertical_alignment="center"):
            if st.button("Accept group", type="primary"):
                _accept(g, uid, key)
                nav.go("group")
            st.button("Pass on this group", on_click=lambda: decisions.__setitem__(key, "passed"))
            md("<p class='fine inline'>A flat forms when everyone in it accepts.</p>")


def matches_page():
    cohort, cl, res, ctx = engine()
    me = my_profile(cohort)
    if me is None:
        page_head("Flat groups")
        need_quiz("Flat groups")
        return
    persona = cl["points"].set_index("id").loc[me["id"], "persona"]
    page_head("Flat groups for you",
              f"Whole flats of people joining when you do, not single profiles. You're in the "
              f"{esc(persona_label(persona).lower())} group of the cohort.")
    from core.grouping import user_deck
    deck, placed = user_deck(cohort, cl, res, me["id"])
    if not placed:
        reason = next((u["reason"] for u in res["unmatched"] if u["id"] == me["id"]), "no compatible group")
        st.warning(f"We couldn't place you in a flat yet ({reason}). These are the closest alternatives.",
                   icon=":material/info:")
    if actions.my_group(me["id"]):
        st.info("You already have a group. Accepting another one moves you to it.", icon=":material/group:")
    if not deck:
        empty("No flat groups yet", "Nobody in the cohort fits your budget and dealbreakers right now. "
              "Try a wider budget or another flat size in Your answers.")
        if st.button("Change my answers", type="primary"):
            nav.go("answers")
        return
    _deck(deck, me["id"], ctx, actions.name_lookup(cohort))


# ---------------------------------------------------------------------------
# Profile: persona + what the AI read from your own words
# ---------------------------------------------------------------------------
def profile_page():
    cohort, cl, res, ctx = engine()
    user = my_profile(cohort)
    if user is None:
        page_head("Profile")
        need_quiz("Your profile")
        return
    persona = cl["personas"][int(cl["points"].set_index("id").loc[user["id"], "cluster"])]
    md(f"""<div class='persona-hero'>{avatar(user['name'], True, 'lg')}<div>
        <h1 class='display'>{esc(user['name'])}</h1>
        <p>Your lifestyle group in the cohort is <b>{esc(persona_label(persona['name']).lower())}</b>.
        {esc(persona['description'])}</p></div></div>""")

    left, right = st.columns([1, 1], gap="large")
    priorities = [TRAIT_SHORT[t] for t in str(user.get("priorities", "")).split(";") if t in TRAIT_SHORT]
    with left:
        dbs = ", ".join(DEALBREAKERS[d] for d in dealbreaker_list(user["dealbreakers"])) or "None"
        md("<div class='panel'><h3 class='panel-h'>Account</h3>" + kv_table([
            ("Name", esc(user["name"])), ("Email", esc(user["email"])),
            ("Organisation", f"{esc(user['organisation'])} {chip('Verified', 'ok')}"),
            ("Office", esc(user["office_location"])), ("Joining", esc(user["joining_month"]))]) + "</div>"
           "<div class='panel'><h3 class='panel-h'>The flat you want</h3>" + kv_table([
            ("Budget per person", f"{money(user['budget_min'])}–{user['budget_max']:,}"),
            ("People per flat", user["flat_size_pref"]),
            ("Share with", GENDER_MIX_UI.get(user["preferred_gender_mix"], user["preferred_gender_mix"])),
            ("Dealbreakers", esc(dbs)),
            ("Matters a lot", esc(", ".join(priorities)) or "Nothing marked")]) + "</div>"
           "<div class='panel'><h3 class='panel-h'>Your answers</h3>" +
           kv_table([(QUESTION_UI[t]["ask"], esc(choice(t, user[t]))) for t in TRAITS]) + "</div>")
        if st.button("Edit your answers", icon=":material/edit:"):
            nav.go("answers")
    with right:
        extracted = session.state()["extracted"]
        if user["id"] not in extracted:
            extracted[user["id"]] = llm.extract_traits(user["free_text"])
        traits, source = extracted[user["id"]]
        rows, diffs = [], {}
        for t, v in traits.items():
            same = int(user[t]) == v["value"]
            if not same:
                diffs[t] = v["value"]
            rows.append((f"{TRAIT_SHORT[t].capitalize()}<div class='fine'>{esc(v['reason'])}</div>",
                         esc(choice(t, v["value"])) + ("" if same else f"<br>{chip('Differs from your answer', 'warn')}")))
        quote = (f"<blockquote class='quote'>{esc(user['free_text'])}</blockquote>" if user["free_text"]
                 else "<p class='fine'>You didn't describe your ideal flat life.</p>")
        md(f"<div class='panel'><h3 class='panel-h'>In your own words {src_tag(source)}</h3>{quote}"
           + (kv_table(rows) if rows else "<p class='fine'>We couldn't read any habits from this.</p>") + "</div>")
        # WHY ask first: the AI suggests, the user decides. No silent profile edits.
        if diffs and st.button(f"Use {len(diffs)} suggested answer{'s' if len(diffs) > 1 else ''}",
                               icon=":material/auto_fix_high:"):
            save_signup({**user, **diffs})
            session.state().update(decisions={})
            session.flash(f"Used {len(diffs)} suggested answer{'s' if len(diffs) > 1 else ''}.")
            st.rerun()

