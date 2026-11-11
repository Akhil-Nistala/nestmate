"""
Log in and Sign up pages (the only routes visible when logged out).

Layout: on the left, what Nestmate does, shown with a real habit grid (made-up
people); on the right, the form. Demo accounts sit under the login form,
labelled by the story each one shows, so the live demo never depends on typing
a password on stage. They only exist when NESTMATE_DEMO=1.
"""
import streamlit as st

from core import auth
from core.encode import load_cohort, seed_ids
from core.schema import ALLOWED_DOMAINS, GENDERS, JOINING_MONTHS, OFFICES
from ui import nav, session
from ui.components import habit_grid, key_tag, md

# Made-up people for the sample card (not in the cohort).
SAMPLE = [
    {"id": "you", "name": "You", "sleep_time": 2, "cleanliness": 4, "guests_frequency": 2, "food": 1, "smoking": 1},
    {"id": "s1", "name": "Meghana Rao", "sleep_time": 2, "cleanliness": 5, "guests_frequency": 2, "food": 1,
     "smoking": 1},
    {"id": "s2", "name": "Tara Joseph", "sleep_time": 3, "cleanliness": 4, "guests_frequency": 3, "food": 2,
     "smoking": 1},
]


def _brand_panel(headline, sub):
    md(f"""<div class='intro'>
      <h1 class='hero-h'>{headline}</h1>
      <p class='hero-p'>{sub}</p>
      <div class='sample'>
        <div class='card-head'><div class='ch-main'><h2 class='card-h'>3-person flat</h2>
        <p class='card-p'>Early nights and a veg kitchen. Budget ₹12,000–16,000 each, working in Gachibowli.</p>
        </div>{key_tag(92)}</div>
        {habit_grid(SAMPLE, "you")}
      </div>
      <ul class='trust'>
        <li><b>Verified email.</b> Only people with a partner company or college email can join.</li>
        <li><b>Whole flats, not single profiles.</b> You decide on the group you'd live with.</li>
        <li><b>House rules agreed before you move.</b> Quiet hours, chores, guests and bills, in writing.</li>
      </ul></div>""")


def _finish_login(acc):
    session.log_in(acc)
    # The page set changes with the role, so rerun and let the router pick the
    # right home page (admin overview, member home, or the quiz).
    st.rerun()


def _demo_box():
    with st.container(key="demo-box"):
        md("<h3 class='panel-h'>Demo accounts</h3><p class='fine'>One tap, no password. "
           "Each account shows a different part of Nestmate.</p>")
        cohort = load_cohort()
        for p in auth.DEMO_PERSONAS:
            with st.container(key=f"demo-{p['id']}", horizontal=True, vertical_alignment="center"):
                md(f"<div class='demo-who'><b>{p['label']}</b><span>{p['who']}</span></div>")
                if st.button("Open", key=f"demo-btn-{p['id']}"):
                    _finish_login(auth.demo_persona(p["id"], cohort))
        with st.container(key="demo-admin", horizontal=True, vertical_alignment="center"):
            md("<div class='demo-who'><b>HR admin</b><span>Priya Nair, Deloitte HR: cohort, flats, listings and "
               "flags</span></div>")
            if st.button("Open", key="demo-btn-admin"):
                _finish_login(auth.demo_admin())
        seed = cohort[cohort["id"].isin(seed_ids())]
        names = dict(zip(seed["id"], seed["name"]))
        with st.expander("Any member of the synthetic cohort"):
            pick = st.selectbox("Sign in as", sorted(names, key=names.get),
                                format_func=lambda i: f"{names[i]} ({i})")
            if st.button("Sign in as this member", key="demo-any"):
                _finish_login(auth.demo_member(seed[seed["id"] == pick].iloc[0].to_dict()))
        md(f"<p class='fine'>HR admin login: <code>{auth.DEMO_ADMIN['email']}</code>, password "
           f"<code>{auth.DEMO_ADMIN['password']}</code>.</p>")


def login_page():
    left, right = st.columns([1.1, 1], gap="large")
    with left:
        _brand_panel("Know who you're living with before you land in Hyderabad.",
                     "Nestmate puts your verified joining batch into whole flats, matched on sleep, "
                     "cleanliness, guests and food, and finds the flat to go with them.")
    with right:
        with st.container(key="auth-card"):
            md("<h2 class='form-h'>Log in</h2><p class='form-sub'>Use your work or college email.</p>")
            with st.form("login", border=False, enter_to_submit=True):
                email = st.text_input("Email", placeholder="you@deloitte.com")
                password = st.text_input("Password", type="password")
                ok = st.form_submit_button("Log in", type="primary", width="stretch")
            if ok:
                acc, err = auth.log_in(email, password)
                if err:
                    st.error(err)
                else:
                    _finish_login(acc)
            st.page_link(nav.PAGES["signup"], label="New here? Create an account")
        # WHY gated: demo accounts skip passwords, so they only exist when NESTMATE_DEMO=1.
        if auth.demo_enabled():
            _demo_box()


def signup_page():
    left, right = st.columns([1.1, 1], gap="large")
    with left:
        _brand_panel("Two minutes now saves a year with the wrong flatmates.",
                     "Create your account with your work or college email, answer a short lifestyle quiz, "
                     "and see whole flat groups from your batch.")
    with right, st.container(key="auth-card"):
        md("<p class='fine'>Step 1 of 2: your account. Step 2 is the lifestyle quiz.</p>"
           "<h2 class='form-h'>Create your account</h2>"
           "<p class='form-sub'>Only people from partner companies and colleges can join.</p>")
        with st.form("signup", border=False):
            name = st.text_input("Full name")
            email = st.text_input("Work or college email", placeholder="you@deloitte.com",
                                  help="Accepted: " + ", ".join(ALLOWED_DOMAINS))
            c1, c2 = st.columns(2)
            password = c1.text_input("Password", type="password", help=f"At least {auth.MIN_PASSWORD} characters")
            confirm = c2.text_input("Confirm password", type="password")
            c1, c2, c3 = st.columns(3)
            gender = c1.selectbox("Gender", GENDERS)
            office = c2.selectbox("Office", OFFICES)
            month = c3.selectbox("Joining", JOINING_MONTHS)
            ok = st.form_submit_button("Create account", type="primary", width="stretch")
        if ok:
            acc, err = auth.sign_up(name, email, password, confirm, gender, office, month)
            if err:
                st.error(err)
            else:
                _finish_login(acc)
        md("<p class='fine'>Email verification by one-time code is mocked for the demo. "
           "The partner-domain check stands in for it.</p>")
        st.page_link(nav.PAGES["login"], label="Already have an account? Log in")
