"""
Log in and Sign up pages (the only routes visible when logged out).

Deliberately short: one headline, one line, the form. Demo accounts are folded
under the form (they only exist when NESTMATE_DEMO=1), labelled by the story
each one shows, so a live demo never depends on typing a password.
"""
import streamlit as st

from core import auth
from core.encode import load_cohort, seed_ids
from core.schema import ALLOWED_DOMAINS, GENDERS, JOINING_MONTHS, OFFICES
from ui import nav, session
from ui.components import md


def _finish_login(acc):
    session.log_in(acc)
    # The page set changes with the role, so rerun and let the router pick the home page.
    st.rerun()


def _demo_accounts():
    with st.expander("Try a demo account"):
        cohort = load_cohort()
        for p in auth.DEMO_PERSONAS:
            with st.container(key=f"demo-{p['id']}", horizontal=True, vertical_alignment="center"):
                md(f"<div class='demo-who'><b>{p['label']}</b><span>{p['who']}</span></div>")
                if st.button("Open", key=f"demo-btn-{p['id']}"):
                    _finish_login(auth.demo_persona(p["id"], cohort))
        with st.container(key="demo-admin", horizontal=True, vertical_alignment="center"):
            md("<div class='demo-who'><b>Admin</b><span>Priya Nair, HR: cohort, listings and flags</span></div>")
            if st.button("Open", key="demo-btn-admin"):
                _finish_login(auth.demo_admin())
        seed = cohort[cohort["id"].isin(seed_ids())]
        names = dict(zip(seed["id"], seed["name"]))
        pick = st.selectbox("Or any member of the sample cohort", sorted(names, key=names.get),
                            format_func=lambda i: f"{names[i]} ({i})", index=None, placeholder="Pick a person")
        if pick and st.button("Sign in as this member", key="demo-any"):
            _finish_login(auth.demo_member(seed[seed["id"] == pick].iloc[0].to_dict()))


def login_page():
    with st.container(key="auth"):
        md("<h1 class='hero-h'>Find flatmates you'll actually get on with.</h1>"
           "<p class='hero-p'>Matched on sleep, cleanliness, guests and food, with people verified "
           "by their work or college email.</p>")
        with st.form("login", border=False, enter_to_submit=True):
            email = st.text_input("Email", placeholder="you@company.com")
            password = st.text_input("Password", type="password")
            ok = st.form_submit_button("Log in", type="primary", width="stretch")
        if ok:
            acc, err = auth.log_in(email, password)
            if err:
                st.error(err)
            else:
                _finish_login(acc)
        st.page_link(nav.PAGES["signup"], label="Create an account")
        # WHY gated: demo accounts skip passwords, so they only exist when NESTMATE_DEMO=1.
        if auth.demo_enabled():
            _demo_accounts()


def signup_page():
    with st.container(key="auth"):
        md("<h1 class='hero-h'>Create your account</h1>"
           "<p class='hero-p'>Use your work or college email. Next, a short lifestyle quiz.</p>")
        with st.form("signup", border=False):
            name = st.text_input("Full name")
            email = st.text_input("Work or college email", placeholder="you@company.com",
                                  help="Accepted for this demo: " + ", ".join(ALLOWED_DOMAINS))
            c1, c2 = st.columns(2)
            password = c1.text_input("Password", type="password", help=f"At least {auth.MIN_PASSWORD} characters")
            confirm = c2.text_input("Confirm password", type="password")
            c1, c2, c3 = st.columns(3)
            gender = c1.selectbox("Gender", GENDERS)
            office = c2.selectbox("Where you'll work", OFFICES)
            month = c3.selectbox("Moving in", JOINING_MONTHS)
            ok = st.form_submit_button("Create account", type="primary", width="stretch")
        if ok:
            acc, err = auth.sign_up(name, email, password, confirm, gender, office, month)
            if err:
                st.error(err)
            else:
                _finish_login(acc)
        st.page_link(nav.PAGES["login"], label="I already have an account")
