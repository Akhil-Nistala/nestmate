"""
Log in and Sign up pages (the only routes visible when logged out).

Layout: a brand panel on the left that explains the product in one glance,
the form on the right. Demo mode sits under the login form, clearly labelled,
so the live demo never depends on typing a password on stage.
"""
import streamlit as st

from core import auth
from core.encode import load_cohort, seed_ids
from core.schema import ALLOWED_DOMAINS, GENDERS, JOINING_MONTHS, OFFICES
from ui import nav, session
from ui.components import md


def _brand_panel(headline, sub):
    md(f"""<div class='hero'>
      <div class='hero-body'>
        <div class='eyebrow light'>Hyderabad · 2027 joining cohort</div>
        <h1 class='hero-h'>{headline}</h1>
        <p class='hero-p'>{sub}</p>
      </div>
      <div class='preview'>
        <div class='pv-head'><span>3-person flat · Early-bird Homebody</span><b>92</b></div>
        <div class='pv-people'>
          <span class='avatar'>RV</span><span class='avatar'>AK</span><span class='avatar me'>You</span>
        </div>
        <div class='pv-tags'><span>Early nights</span><span>Veg kitchen</span><span>₹12k–16k</span></div>
      </div>
      <div class='hero-foot'>
        <div><b>Verified</b><span>Work or college email only</span></div>
        <div><b>Whole flats</b><span>Groups of 2–4, not single profiles</span></div>
        <div><b>Explained</b><span>Why it works and what to agree on</span></div>
      </div></div>""")


def _finish_login(acc):
    session.log_in(acc)
    # The page set changes with the role, so rerun and let the router pick the
    # right home page (admin overview or member matches).
    st.rerun()


def login_page():
    left, right = st.columns([1.05, 1], gap="large", vertical_alignment="center")
    with left:
        _brand_panel("Find your flat group before you land.",
                     "Nestmate matches your verified joining cohort into whole flats whose sleep, "
                     "cleanliness, food and guest habits actually fit.")
    with right, st.container(key="auth-card"):
        md("<h2 class='form-h'>Welcome back</h2><p class='form-sub'>Log in to see your matches.</p>")
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
        st.page_link(nav.PAGES["signup"], label="New here? **Create an account**")

        # WHY gated: demo mode skips passwords, so it only exists when NESTMATE_DEMO=1.
        if not auth.demo_enabled():
            return
        md("<div class='divider'><span>or explore the demo</span></div>")
        with st.container(key="demo-box"):
            md("<div class='demo-label'>Demo mode <span class='chip'>no password</span></div>")
            c1, c2 = st.columns(2, gap="small")
            if c1.button("HR admin", icon=":material/insights:", width="stretch",
                         help=f"Same as logging in as {auth.DEMO_ADMIN['email']} / {auth.DEMO_ADMIN['password']}"):
                _finish_login(auth.demo_admin())
            # Only synthetic seed profiles: real sign-ups can't be impersonated.
            cohort = load_cohort()
            cohort = cohort[cohort["id"].isin(seed_ids())]
            names = dict(zip(cohort["id"], cohort["name"]))
            with c2.popover("Cohort member", icon=":material/person:", width="stretch"):
                pick = st.selectbox("Sign in as", sorted(names, key=names.get),
                                    format_func=lambda i: f"{names[i]}  ·  {i}")
                if st.button("Continue", type="primary", width="stretch"):
                    _finish_login(auth.demo_member(cohort[cohort["id"] == pick].iloc[0].to_dict()))
            md(f"<p class='fine'>Admin login: <code>{auth.DEMO_ADMIN['email']}</code> · "
               f"<code>{auth.DEMO_ADMIN['password']}</code></p>")


def signup_page():
    left, right = st.columns([1.05, 1], gap="large", vertical_alignment="center")
    with left:
        _brand_panel("Two minutes now saves a year of the wrong flatmates.",
                     "Create your account with your work or college email, take a short lifestyle "
                     "quiz, and we'll suggest whole flat groups from your cohort.")
    with right, st.container(key="auth-card"):
        md("<div class='steps-mini'><span class='on'>1 · Account</span><span>2 · Lifestyle quiz</span></div>"
           "<h2 class='form-h'>Create your account</h2>"
           "<p class='form-sub'>Only partner companies and colleges can join.</p>")
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
        md("<p class='fine'>Email verification by one-time code is mocked for the demo: "
           "the partner-domain check stands in for it.</p>")
        st.page_link(nav.PAGES["login"], label="Already have an account? **Log in**")
