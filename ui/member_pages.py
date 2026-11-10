"""
Member (client) routes: onboarding quiz, matches, my flat, profile, preferences.

Members never see cohort-wide statistics or other people's data beyond the
groups suggested to them. That view belongs to the admin route.
"""
import streamlit as st

from core import llm
from core.encode import dealbreaker_list, load_cohort, save_signup
from core.grouping import user_deck
from core.schema import (BUDGET_MAX, BUDGET_MIN, DEALBREAKERS, FLAT_SIZES, GENDER_MIX, QUESTIONS, TRAIT_SHORT,
                         TRAITS)
from ui import nav, session
from ui.components import (avatar, chip, compute, empty, esc, kv_table, label, md, page_head, ring, section,
                           src_tag)



def current_user(cohort):
    """The logged-in member's cohort row, or None if they haven't done the quiz."""
    uid = session.account().get("user_id")
    rows = cohort[cohort["id"] == uid]
    return rows.iloc[0].to_dict() if len(rows) else None


def _reset_matches():
    session.state().update(decisions={}, formed=None)


# ---------------------------------------------------------------------------
# Lifestyle quiz (used for onboarding and for editing preferences)
# ---------------------------------------------------------------------------
def _quiz(prev, submit_label):
    acc = session.account()
    with st.form("quiz", border=False):
        with st.container(key="quiz-card"):
            section("How you live", "Answers are ordered, so drag to the closest fit.")
            answers = {}
            cols = st.columns(2, gap="large")
            for n, (t, q) in enumerate(QUESTIONS.items()):
                opts = list(q["options"])
                default = int(prev.get(t, opts[len(opts) // 2]))
                # WHY select_slider: answers are ordered, and a slider shows that order visually.
                answers[t] = cols[n % 2].select_slider(q["label"], options=opts, value=default,
                                                       format_func=lambda v, q=q: q["options"][v])
        with st.container(key="quiz-card-2"):
            section("The flat you want")
            c1, c2, c3 = st.columns(3, gap="large")
            budget = c1.slider("Budget per person / month (₹)", BUDGET_MIN, BUDGET_MAX,
                               (int(prev.get("budget_min", 9000)), int(prev.get("budget_max", 15000))), step=500)
            size = c2.segmented_control("People per flat", FLAT_SIZES, required=True,
                                        default=int(prev.get("flat_size_pref", 3)))
            mix = c3.segmented_control("Flatmate gender", GENDER_MIX, required=True,
                                       default=prev.get("preferred_gender_mix", "same only"),
                                       format_func=str.capitalize)
            dbs = st.multiselect("Dealbreakers (up to 3)", list(DEALBREAKERS), format_func=DEALBREAKERS.get,
                                 default=dealbreaker_list(prev.get("dealbreakers", "")), max_selections=3)
            text = st.text_area("Describe your ideal flat life in 1–3 sentences", value=prev.get("free_text", ""),
                                placeholder="I game till late but keep the kitchen spotless.")
        submitted = st.form_submit_button(submit_label, type="primary")

    if submitted:
        profile = {"id": acc["user_id"], "name": acc["name"], "email": acc["email"], "verified": True,
                   "organisation": acc["organisation"], "office_location": acc["office_location"],
                   "joining_month": acc["joining_month"], "gender": acc["gender"]}
        profile.update(answers)
        profile.update({"preferred_gender_mix": mix, "budget_min": budget[0], "budget_max": budget[1],
                        "flat_size_pref": size, "free_text": text, "dealbreakers": ";".join(dbs),
                        "_true_archetype": ""})
        with st.spinner("Reading your description and updating the cohort…"):
            session.state()["extracted"][profile["id"]] = llm.extract_traits(text)
            save_signup(profile)
        _reset_matches()
        return True
    return False


def onboarding_page():
    md("<div class='steps-mini'><span class='done'>1 · Account</span><span class='on'>2 · Lifestyle quiz</span></div>")
    first = session.account()["name"].split()[0]
    page_head(f"Nice to meet you, {esc(first)}.", "Two minutes. Honest answers make better flatmates.")
    if _quiz({}, "Save and see my matches"):
        st.rerun()  # router now shows the member pages; default is Matches


def preferences_page():
    me = current_user(load_cohort())
    page_head("Preferences", "Change your answers any time. Your matches update straight away.")
    if _quiz(me, "Save changes"):
        nav.go("matches")


# ---------------------------------------------------------------------------
# Matches: decide on whole groups, not individual people
# ---------------------------------------------------------------------------
def group_key(g):
    return "|".join(sorted(g["member_ids"]))


def _group_card(g, me_id, pos, total):
    open_spots = g["target"] - g["size"]
    people = ""
    for m in g["members"]:
        is_me = m["id"] == me_id
        tags = "".join(chip(label(t, m[t])) for t in ("sleep_time", "cleanliness", "guests_frequency"))
        people += (f"<div class='person'>{avatar(m['name'], is_me)}<div class='who'>"
                   f"<div class='n'>{esc(m['name'])}{' <span class=you>you</span>' if is_me else ''}</div>"
                   f"<div class='m'>{esc(m['organisation'])} · {esc(m['office_location'])}</div>"
                   f"<div class='tags'>{tags}</div></div></div>")
    dots = "".join(f"<i class='{'on' if i == pos else ''}'></i>" for i in range(total))
    md(f"""<div class='card-head'>
        {ring(g['score'])}
        <div class='ch-main'>
          <div class='eyebrow'>Suggestion {pos + 1} of {total}<span class='dots'>{dots}</span></div>
          <h2 class='display sm'>{g['size']}-person flat · {esc(g['persona'])}</h2>
          <div class='chips'>{chip(f"₹{g['budget'][0]:,} – ₹{g['budget'][1]:,} each")}
            {chip(' · '.join(g['offices']))}
            {chip(f'{open_spots} spot open', 'warn') if open_spots > 0 else chip('Full flat', 'ok')}</div>
        </div></div>
        <div class='people'>{people}</div>""")
    left, right = st.columns([3, 2], gap="large")
    with left:
        text, src = llm.explain_group(g)
        md(f"<div class='label'>Why it works, what to watch {src_tag(src)}</div>")
        with st.container(key="explain"):
            st.markdown(text)
    with right:
        areas, summary, src = llm.suggest_areas(g)
        rows = "".join(f"<div class='area'><div><b>{a['area']}</b>"
                       f"{'' if a['fits_budget'] else chip('over budget', 'warn')}</div>"
                       f"<div class='r'>₹{a['rent']:,} · {a['avg_commute']} min</div></div>" for a in areas)
        md(f"<div class='label'>Where to look {src_tag(src)}</div><div class='areas'>{rows}</div>"
           f"<p class='fine'>{esc(summary)}</p>")


def _accept(g):
    st_ = session.state()
    st_["decisions"][group_key(g)] = "accepted"
    st_["formed"] = g


@st.fragment
def _deck(deck, me_id):
    decisions = session.state()["decisions"]
    pending = [g for g in deck if group_key(g) not in decisions]
    if not pending:
        empty("That's every suggestion for now",
              "New people join the cohort every week. We'll let you know when a new group fits.")
        # WHY on_click: callbacks run before the fragment re-renders, so the deck
        # refreshes in one pass without an explicit st.rerun.
        st.button("Start over", icon=":material/restart_alt:", on_click=_reset_matches)
        return
    g = pending[0]
    with st.container(key="group-card"):
        _group_card(g, me_id, deck.index(g), len(deck))
        with st.container(horizontal=True, gap="small", key="card-actions"):
            if st.button("Accept group", type="primary", icon=":material/check:"):
                _accept(g)
                nav.go("flat")
            # A click inside a fragment re-runs only this card, not the whole page.
            st.button("Pass", icon=":material/close:",
                      on_click=lambda: decisions.__setitem__(group_key(g), "passed"))
            md("<span class='fine' style='margin:0 0 0 8px'>A flat forms when everyone in it accepts.</span>")


def matches_page():
    cohort = load_cohort()
    me = current_user(cohort)
    with st.spinner("Finding your flat groups…"):
        cl, res = compute(cohort)
    persona = cl["points"].set_index("id").loc[me["id"], "persona"]
    page_head("Your matches", "You decide on whole groups, not individual people.",
              eyebrow=f"{esc(me['name'].split()[0])} · {esc(persona)}")
    deck, placed = user_deck(cohort, cl, res, me["id"])
    if not placed:
        reason = next((u["reason"] for u in res["unmatched"] if u["id"] == me["id"]), "no compatible group")
        st.warning(f"We couldn't place you in a cohort flat yet: {reason}. These are the closest alternatives.",
                   icon=":material/info:")
    if session.state()["formed"]:
        st.success("You've accepted a group. Your house agreement is ready in My flat.", icon=":material/home:")
    _deck(deck, me["id"])


# ---------------------------------------------------------------------------
# My flat: the accepted group + AI house agreement
# ---------------------------------------------------------------------------
def flat_page():
    g = session.state()["formed"]
    if not g:
        page_head("My flat")
        empty("No flat yet", "Accept a suggested group on the Matches page and your house agreement appears here.")
        if st.button("See my matches", type="primary"):
            nav.go("matches")
        return
    me_id = session.account()["user_id"]
    page_head(" · ".join(esc(m["name"].split()[0]) for m in g["members"]),
              f"{esc(g['persona'])} · ₹{g['budget'][0]:,} – ₹{g['budget'][1]:,} each",
              eyebrow="Flat formed")
    left, right = st.columns([2, 1], gap="large")
    with right:
        people = "".join(f"<div class='person slim'>{avatar(m['name'], m['id'] == me_id)}<div class='who'>"
                         f"<div class='n'>{esc(m['name'])}</div><div class='m'>{esc(m['organisation'])}</div></div>"
                         f"{chip('Accepted', 'ok')}</div>" for m in g["members"])
        # WHY say "simulated": in the real product each member accepts on their own phone.
        md(f"<div class='panel'><div class='label'>Flatmates</div>{people}"
           f"<p class='fine'>Other members' acceptance is simulated for the demo.</p></div>"
           f"<div class='panel'><div class='label'>Match</div>"
           f"<div style='display:flex;align-items:center;gap:14px'>{ring(g['score'], 64)}"
           f"<div class='fine' style='margin:0'>Compatibility across sleep, cleanliness, guests, food and "
           f"8 more lifestyle answers.</div></div></div>")
    with left:
        text, src = llm.house_agreement(g)
        md(f"<div class='label'>House agreement {src_tag(src)}</div>")
        with st.container(key="agreement"):
            st.markdown(text)
        st.download_button("Download agreement", text, file_name="nestmate_house_agreement.md",
                           icon=":material/download:")


# ---------------------------------------------------------------------------
# Profile: persona + what the AI read from your own words
# ---------------------------------------------------------------------------
def profile_page():
    cohort = load_cohort()
    user = current_user(cohort)
    cl, _ = compute(cohort)
    persona = cl["personas"][int(cl["points"].set_index("id").loc[user["id"], "cluster"])]
    md(f"""<div class='persona-hero'>{avatar(user['name'], True, 'lg')}<div>
        <div class='eyebrow'>Your persona</div><h1 class='display'>{esc(persona['name'])}</h1>
        <p>{esc(persona['description'])}</p></div></div>""")

    left, right = st.columns([1, 1], gap="large")
    with left:
        dbs = ", ".join(DEALBREAKERS[d] for d in dealbreaker_list(user["dealbreakers"])) or "None"
        md(f"<div class='panel'><div class='label'>Account</div>" + kv_table([
            ("Name", esc(user["name"])), ("Email", esc(user["email"])),
            ("Organisation", f"{esc(user['organisation'])} {chip('Verified', 'ok')}"),
            ("Office · joining", f"{esc(user['office_location'])} · {esc(user['joining_month'])}")]) + "</div>"
           f"<div class='panel'><div class='label'>Flat preferences</div>" + kv_table([
            ("Budget per person", f"₹{user['budget_min']:,} – ₹{user['budget_max']:,}"),
            ("People per flat", user["flat_size_pref"]),
            ("Flatmate gender", user["preferred_gender_mix"].capitalize()),
            ("Dealbreakers", esc(dbs))]) + "</div>"
           f"<div class='panel'><div class='label'>Quiz answers</div>" +
           kv_table([(QUESTIONS[t]["label"], label(t, user[t])) for t in TRAITS]) + "</div>")
        if st.button("Edit preferences", icon=":material/tune:"):
            nav.go("preferences")
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
            rows.append((f"{TRAIT_SHORT[t].capitalize()}<div class='fine' style='margin:2px 0 0'>"
                         f"{esc(v['reason'])}</div>",
                         label(t, v["value"]) + ("" if same else f"<br>{chip('differs from quiz', 'warn')}")))
        md(f"<div class='panel'><div class='label'>In your words {src_tag(source)}</div>"
           f"<blockquote class='quote'>“{esc(user['free_text'])}”</blockquote>"
           + (kv_table(rows) if rows else "<p class='fine'>No traits could be inferred.</p>") + "</div>")
        # WHY ask first: the AI suggests, the user decides. No silent profile edits.
        if diffs and st.button(f"Use {len(diffs)} suggested answer{'s' if len(diffs) > 1 else ''}",
                               icon=":material/auto_fix_high:"):
            save_signup({**user, **diffs})
            _reset_matches()
            st.rerun()
