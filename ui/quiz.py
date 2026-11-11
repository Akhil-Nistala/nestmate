"""
The lifestyle quiz: four short steps, every option visible as a button.

Used for onboarding (empty) and for "Your answers" (pre-filled from the
saved profile). Design decisions:
  - No pre-selected lifestyle answers. A slider parked on the middle records
    "average" for people who never touched it; here an unanswered question
    stays unanswered and Continue names it.
  - Ordered scales use a segmented control (the order is visible), short
    categorical sets (food, smoking, drinking) use pills.
  - "Matters a lot to me" under each question, and a specific dealbreaker
    under food, smoking, drinking and noise, instead of one abstract list.
  - In-progress answers live in the session dict, not only in widget state:
    Streamlit drops the state of widgets that are not rendered, so going Back
    would otherwise lose them.
"""
import streamlit as st

from core import llm
from core.encode import dealbreaker_list, save_signup
from core.schema import (BUDGET_MAX, BUDGET_MIN, DEALBREAKERS, FLAT_SIZES, GENDER_MIX_UI, JOINING_MONTHS,
                         MAX_DEALBREAKERS, MAX_PRIORITIES, OFFICES, QUESTION_UI, QUIZ_STEPS, TRAIT_SHORT, TRAITS,
                         self_contradictions)
from ui import session
from ui.components import esc, join_and, md, money, progress

CONTRADICTION = {
    "no_smokers": "You said you smoke, and no smokers is one of your dealbreakers.",
    "veg_kitchen": "You said you cook or eat non-veg, and a veg-only kitchen is one of your dealbreakers.",
    "no_drinking": "You said you drink, and no drinking at home is one of your dealbreakers.",
    "quiet_home": "You're fine with a lively home or have friends over weekly, and a quiet home is one of your "
                  "dealbreakers.",
}
DB_SHORT = {"quiet_home": "quiet home", "veg_kitchen": "veg-only kitchen", "no_smokers": "no smokers",
            "no_drinking": "no drinking"}


# ---------------------------------------------------------------------------
# Draft (session) state
# ---------------------------------------------------------------------------
def _draft(prev, mode):
    acc = session.account()
    q = session.state().get("quiz")
    if q and q["owner"] == acc["user_id"] and q["mode"] == mode:
        return q
    dbs = dealbreaker_list(prev.get("dealbreakers", ""))
    mix = prev.get("preferred_gender_mix")
    if "same_gender" in dbs:  # older profiles: same effect as "same gender only"
        mix = "same only"
    q = {"owner": acc["user_id"], "mode": mode, "step": 0, "nonce": (q or {}).get("nonce", 0) + 1,
         "answers": {t: (int(prev[t]) if t in prev and prev[t] == prev[t] else None) for t in TRAITS},
         "priorities": [p for p in str(prev.get("priorities", "") or "").split(";") if p in TRAITS],
         "dealbreakers": [d for d in dbs if d != "same_gender"],
         "budget": (int(prev.get("budget_min", 9000)), int(prev.get("budget_max", 15000))),
         "size": int(prev["flat_size_pref"]) if prev.get("flat_size_pref") else None,
         "mix": mix, "text": prev.get("free_text", "") or "",
         "office": acc.get("office_location") or prev.get("office_location"),
         "joining": acc.get("joining_month") or prev.get("joining_month"),
         "error": None, "notice": None}
    session.state()["quiz"] = q
    return q


def _key(q, name):
    return f"quiz{q['nonce']}-{name}"


def _default(q, name, value):
    """Pass the saved value only the first time a widget is created; afterwards
    its own state wins (avoids Streamlit's 'default and session state' warning)."""
    return {} if _key(q, name) in st.session_state else {"value": value}


# ---------------------------------------------------------------------------
# Callbacks (run before the next render, so the screen is consistent)
# ---------------------------------------------------------------------------
def _set_answer(q, t):
    q["answers"][t] = st.session_state[_key(q, t)]
    q["error"] = None


def _toggle(q, kind, item, limit, noun):
    k = _key(q, f"{kind}-{item}")
    on, lst = st.session_state[k], q[kind]
    if on and item not in lst:
        if len(lst) >= limit:
            st.session_state[k] = False
            q["notice"] = f"You can mark up to {limit} {noun}. Untick one first."
            return
        lst.append(item)
    elif not on and item in lst:
        lst.remove(item)
    q["notice"] = None


def _set(q, field, name=None):
    q[field] = st.session_state[_key(q, name or field)]
    q["error"] = None


def _missing(q, step):
    return [t for t in QUIZ_STEPS[step]["traits"] if q["answers"][t] is None]


def _step_error(q, step):
    miss = _missing(q, step)
    if miss:
        return f"Pick an answer for {join_and(TRAIT_SHORT[t] for t in miss)}."
    clash = [d for d in self_contradictions(q["answers"], q["dealbreakers"])
             if any(t in QUIZ_STEPS[step]["traits"] for t in
                    {"no_smokers": ["smoking"], "veg_kitchen": ["food"], "no_drinking": ["drinking"],
                     "quiet_home": ["noise_tolerance", "guests_frequency"]}[d])]
    if clash:
        return " ".join(CONTRADICTION[d] for d in clash) + " Change the answer or untick the dealbreaker."
    if QUIZ_STEPS[step]["key"] == "flat":
        need = [n for n, v in (("how many people", q["size"]), ("who you'll share with", q["mix"]),
                               ("your office", q["office"]), ("when you join", q["joining"])) if not v]
        if need:
            return f"Pick {join_and(need)}."
    return None


def _go(q, step):
    if step > q["step"]:
        err = _step_error(q, q["step"])
        if err:
            q["error"] = err
            return
    q["step"], q["error"], q["notice"] = step, None, None


# ---------------------------------------------------------------------------
# Pieces
# ---------------------------------------------------------------------------
def _steps(q):
    items = ""
    for i, s in enumerate(QUIZ_STEPS):
        state = "on" if i == q["step"] else "done" if i < q["step"] else ""
        cur = " aria-current='step'" if i == q["step"] else ""
        items += f"<li class='{state}'{cur}><span class='n'>{i + 1}</span><span class='t'>{s['title']}</span></li>"
    md(f"<ol class='quiz-steps' aria-label='Step {q['step'] + 1} of {len(QUIZ_STEPS)}'>{items}</ol>")


def _question(q, t):
    ui = QUESTION_UI[t]
    with st.container(key=f"q-{t}"):
        widget = st.segmented_control if ui["widget"] == "scale" else st.pills
        kw = {} if _key(q, t) in st.session_state else {"default": q["answers"][t]}
        widget(ui["ask"], list(ui["choices"]), format_func=ui["choices"].get, selection_mode="single",
               key=_key(q, t), on_change=_set_answer, args=(q, t), **kw)
        if ui.get("hint"):
            md(f"<p class='hint'>{ui['hint']}</p>")
        with st.container(horizontal=True, gap="medium", key=f"marks-{t}"):
            st.checkbox("Matters a lot to me", key=_key(q, f"priorities-{t}"),
                        on_change=_toggle, args=(q, "priorities", t, MAX_PRIORITIES, "things as mattering a lot"),
                        **_default(q, f"priorities-{t}", t in q["priorities"]))
            if ui.get("dealbreaker"):
                d, text = ui["dealbreaker"]
                st.checkbox(text, key=_key(q, f"dealbreakers-{d}"),
                            on_change=_toggle, args=(q, "dealbreakers", d, MAX_DEALBREAKERS, "dealbreakers"),
                            **_default(q, f"dealbreakers-{d}", d in q["dealbreakers"]))


def _flat_step(q):
    with st.container(key="q-flat"):
        st.slider("Budget per person, per month (₹)", BUDGET_MIN, BUDGET_MAX, step=500, key=_key(q, "budget"),
                  on_change=_set, args=(q, "budget"), **_default(q, "budget", q["budget"]))
        kw = {} if _key(q, "size") in st.session_state else {"default": q["size"]}
        st.segmented_control("How many people in the flat, including you?", FLAT_SIZES,
                             format_func=lambda n: f"{n} people", key=_key(q, "size"), on_change=_set,
                             args=(q, "size"), **kw)
        kw = {} if _key(q, "mix") in st.session_state else {"default": q["mix"]}
        st.pills("Who would you share with?", list(GENDER_MIX_UI), format_func=GENDER_MIX_UI.get,
                 key=_key(q, "mix"), on_change=_set, args=(q, "mix"), **kw)
        acc = session.account()
        if not acc.get("office_location"):  # e.g. a landlord account that wants to search too
            kw = {} if _key(q, "office") in st.session_state else {"default": q["office"]}
            st.pills("Which office will you work at?", OFFICES, key=_key(q, "office"), on_change=_set,
                     args=(q, "office"), **kw)
        if not acc.get("joining_month"):
            kw = {} if _key(q, "joining") in st.session_state else {"default": q["joining"]}
            st.pills("When do you join?", JOINING_MONTHS, key=_key(q, "joining"), on_change=_set,
                     args=(q, "joining"), **kw)
        st.text_area("Describe your ideal flat life in a sentence or two (optional)", key=_key(q, "text"),
                     placeholder="I game till late but keep the kitchen spotless.", max_chars=400,
                     on_change=_set, args=(q, "text"), **_default(q, "text", q["text"]))
        md("<p class='hint'>We read this for habits the questions missed, and show you what we found "
           "on your profile before using it.</p>")


def _summary(q):
    answered = sum(v is not None for v in q["answers"].values())
    with st.container(key="quiz-summary"):
        md(f"<h3 class='sum-h'>Your profile</h3><p class='sum-sub'>{answered} of {len(TRAITS)} answered</p>")
        progress(answered, len(TRAITS))
        rows = ""
        for s in QUIZ_STEPS[:3]:
            rows += f"<tr class='grp'><th colspan='2'>{s['title']}</th></tr>"
            for t in s["traits"]:
                v = q["answers"][t]
                marks = ""
                if t in q["priorities"]:
                    marks += "<span class='mark'>Matters a lot</span>"
                d = QUESTION_UI[t].get("dealbreaker")
                if d and d[0] in q["dealbreakers"]:
                    marks += f"<span class='mark db'>Dealbreaker: {DB_SHORT[d[0]]}</span>"
                ans = esc(QUESTION_UI[t]["choices"][v]) if v is not None else "<span class='todo'>Not answered</span>"
                rows += f"<tr><td>{TRAIT_SHORT[t].capitalize()}</td><td>{ans}{marks}</td></tr>"
        lo, hi = q["budget"]
        todo = "<span class='todo'>Not answered</span>"
        size = f"{q['size']} people" if q["size"] else todo
        mix = GENDER_MIX_UI[q["mix"]] if q["mix"] else todo
        rows += "<tr class='grp'><th colspan='2'>The flat</th></tr>"
        rows += f"<tr><td>Budget</td><td>{money(lo)}–{hi:,} each</td></tr>"
        rows += f"<tr><td>Flat size</td><td>{size}</td></tr><tr><td>Share with</td><td>{mix}</td></tr>"
        md(f"<table class='summary'>{rows}</table>"
           f"<p class='fine'>{len(q['priorities'])} of {MAX_PRIORITIES} marked as mattering a lot, "
           f"{len(q['dealbreakers'])} of {MAX_DEALBREAKERS} dealbreakers.</p>")


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------
def _save(q, prev):
    acc = session.account()
    profile = {"id": acc["user_id"], "name": acc["name"], "email": acc["email"], "verified": True,
               "organisation": acc.get("organisation") or prev.get("organisation") or "",
               "office_location": q["office"], "joining_month": q["joining"],
               "gender": acc.get("gender") or prev.get("gender") or ""}
    profile.update({t: int(v) for t, v in q["answers"].items()})
    profile.update({"preferred_gender_mix": q["mix"], "budget_min": q["budget"][0], "budget_max": q["budget"][1],
                    "flat_size_pref": int(q["size"]), "free_text": q["text"].strip(),
                    "dealbreakers": ";".join(q["dealbreakers"]), "priorities": ";".join(q["priorities"]),
                    "_true_archetype": prev.get("_true_archetype", "") if q["mode"] == "edit" else ""})
    with st.spinner("Reading your description and updating your matches…"):
        session.state()["extracted"][profile["id"]] = llm.extract_traits(profile["free_text"])
        save_signup(profile)
    session.state().update(decisions={}, quiz=None)


def quiz(prev, mode, save_label):
    """Render the quiz. Returns True once the profile was saved."""
    q = _draft(prev or {}, mode)
    _steps(q)
    left, right = st.columns([3, 2], gap="large")
    step = QUIZ_STEPS[q["step"]]
    with left:
        with st.container(key="quiz-card"):
            md(f"<h2 class='step-h'>{step['title']}</h2>")
            if step["traits"]:
                for t in step["traits"]:
                    _question(q, t)
            else:
                _flat_step(q)
        if q.get("notice"):
            st.info(q["notice"], icon=":material/info:")
        if q.get("error"):
            st.error(q["error"], icon=":material/error:")
        saved = False
        with st.container(horizontal=True, gap="small", key="quiz-nav"):
            if q["step"] > 0:
                st.button("Back", on_click=_go, args=(q, q["step"] - 1), key=_key(q, "back"))
            if q["step"] < len(QUIZ_STEPS) - 1:
                st.button("Continue", type="primary", on_click=_go, args=(q, q["step"] + 1), key=_key(q, "next"))
            elif st.button(save_label, type="primary", key=_key(q, "save")):
                for i in range(len(QUIZ_STEPS)):
                    err = _step_error(q, i)
                    if err:
                        q["step"], q["error"] = i, err
                        st.rerun()
                _save(q, prev or {})
                saved = True
    with right:
        _summary(q)
    return saved
