"""
Nestmate — Find your flat group before you land.
Run:  streamlit run app.py

This file is only the router. WHY role-based routes with st.navigation:
the set of pages is built per request from the logged-in role, so a member
literally has no /admin-* URL to visit, rather than a hidden menu item.

    logged out  ->  /            Log in
                    /signup      Sign up
    member      ->  /onboarding  (until the quiz is done)
                    /            Matches   /flat   /profile   /preferences
    admin (HR)  ->  /            Overview  /admin-flats   /admin-people   /admin-model

Pages live in ui/: auth_pages.py, member_pages.py, admin_pages.py.
"""
import streamlit as st

st.set_page_config(page_title="Nestmate", page_icon="assets/icon.svg", layout="wide",
                   initial_sidebar_state="collapsed")

from core import llm  # noqa: E402  (set_page_config must run first)
from core.encode import load_cohort  # noqa: E402
from ui import admin_pages, auth_pages, member_pages, nav, session, theme  # noqa: E402
from ui.components import esc, initials  # noqa: E402

session.init()
theme.inject_css()
acc = session.account()


def build_pages():
    """(page key -> st.Page) for the current role. Order = nav order."""
    P = st.Page
    if acc is None:
        return {"login": P(auth_pages.login_page, title="Log in", url_path="login", default=True),
                "signup": P(auth_pages.signup_page, title="Sign up", url_path="signup")}
    if acc["role"] == "admin":
        return {"overview": P(admin_pages.overview_page, title="Overview", url_path="admin", default=True),
                "admin-flats": P(admin_pages.flats_page, title="Flat groups", url_path="admin-flats"),
                "admin-people": P(admin_pages.people_page, title="People", url_path="admin-people"),
                "admin-model": P(admin_pages.model_page, title="Model checks", url_path="admin-model")}
    if acc["user_id"] not in set(load_cohort()["id"]):
        return {"onboarding": P(member_pages.onboarding_page, title="Lifestyle quiz", url_path="onboarding",
                                default=True)}
    return {"matches": P(member_pages.matches_page, title="Matches", url_path="matches", default=True),
            "flat": P(member_pages.flat_page, title="My flat", url_path="flat"),
            "profile": P(member_pages.profile_page, title="Profile", url_path="profile"),
            "preferences": P(member_pages.preferences_page, title="Preferences", url_path="preferences")}


# Every path the app can show, so the theme choice is saved for all of them.
ALL_PATHS = ["/", "/login", "/signup", "/onboarding", "/matches", "/flat", "/profile", "/preferences",
             "/admin", "/admin-flats", "/admin-people", "/admin-model"]

nav.PAGES.clear()
nav.PAGES.update(build_pages())
current = st.navigation(list(nav.PAGES.values()), position="hidden")

# ---------------------------------------------------------------------------
# Top bar: brand · route links · theme toggle · account menu
# ---------------------------------------------------------------------------
ss = st.session_state
dark = theme.mode() == "dark"


def _toggle_theme():
    ss.theme_target = "light" if dark else "dark"


with st.container(key="topbar", horizontal=True, vertical_alignment="center", gap="medium"):
    is_admin = acc is not None and acc["role"] == "admin"
    st.html(f"<div class='brand'><span class='logo'>n</span><span class='wordmark'>Nestmate</span>"
            f"{'<span class=\"console\">HR console</span>' if is_admin else ''}</div>", width="content")
    if acc is not None and len(nav.PAGES) > 1:
        with st.container(key="nav", horizontal=True, gap=None, width="content"):
            for key, page in nav.PAGES.items():
                # WHY a keyed wrapper: it lets CSS style the active route (Streamlit
                # doesn't expose an "active" attribute on page links).
                state = "on" if page.title == current.title else "off"
                with st.container(key=f"nav-{state}-{key}", width="content"):
                    st.page_link(page, label=page.title)
    with st.container(horizontal=True, horizontal_alignment="right", vertical_alignment="center",
                      gap="small", key="actions"):
        st.button("", icon=":material/light_mode:" if dark else ":material/dark_mode:", type="tertiary",
                  key="theme-btn", help="Switch to light mode" if dark else "Switch to dark mode",
                  on_click=_toggle_theme)
        if acc is not None:
            with st.popover(acc["name"].split()[0], icon=":material/account_circle:", key="account"):
                role = "HR admin" if acc["role"] == "admin" else "Member"
                st.html(f"<div class='acct'><span class='avatar me'>{esc(initials(acc['name']))}</span><div>"
                        f"<div class='n'>{esc(acc['name'])}</div><div class='m'>{esc(acc['email'])}</div>"
                        f"<div class='chips'><span class='chip ok'>{role}</span>"
                        f"<span class='chip'>{esc(acc.get('organisation', ''))}</span>"
                        f"{'<span class=\"chip warn\">Demo</span>' if acc.get('demo') else ''}</div></div></div>"
                        f"<p class='fine'>Language model: "
                        f"{'Gemini, with cache' if llm.llm_available() else 'templates only (no API key)'}. "
                        f"Generated text is labelled AI or Template.</p>")
                st.button("Log out", icon=":material/logout:", width="stretch", on_click=session.log_out)

# ---------------------------------------------------------------------------
# Invisible client-side helpers (session cookie + theme switch). Rendered before
# the page so a page that stops early can't skip them; hidden with CSS.
# ---------------------------------------------------------------------------
with st.container(key="sys"):
    js = session.cookie_js()
    if ss.get("theme_target"):
        js += theme.switch_js(ss.pop("theme_target"), ALL_PATHS)
    st.html(f"<script>{js}</script>", unsafe_allow_javascript=True)

current.run()
