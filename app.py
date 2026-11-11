"""
Nestmate: find flatmates you'll actually get on with, and the flat to go with them.
Run:  streamlit run app.py

This file is only the router. WHY role-based routes with st.navigation:
the set of pages is built per request from the logged-in role, so a member
literally has no /admin-* URL to visit, rather than a hidden menu item.

    logged out  ->  /login  /signup
    member      ->  /home  /explore  /matches (Flat groups)  /group  /listings  /rent
                    /profile  /answers  /onboarding (until the quiz is done)
    admin (HR)  ->  /admin  /admin-flats  /admin-people  /admin-model  /admin-listings  /admin-flags

Every member page is registered (so pages can link to each other), but the top
bar only shows the ones that have something for this person.
Pages live in ui/: auth_pages.py, member_pages.py, market_pages.py, admin_pages.py.
"""
import streamlit as st

st.set_page_config(page_title="Nestmate", page_icon="assets/icon.svg", layout="wide",
                   initial_sidebar_state="collapsed")

from core import actions, llm, store  # noqa: E402  (set_page_config must run first)
from core.encode import load_cohort  # noqa: E402
from ui import admin_pages, auth_pages, market_pages, member_pages, nav, session, theme  # noqa: E402
from ui.components import esc, initials  # noqa: E402

store.ensure_seeded()
session.init()
theme.inject_css()
acc = session.account()


def build_pages():
    """(page key -> st.Page, keys shown in the top bar) for the current role."""
    P = st.Page
    if acc is None:
        pages = {"login": P(auth_pages.login_page, title="Log in", url_path="login", default=True),
                 "signup": P(auth_pages.signup_page, title="Sign up", url_path="signup")}
        return pages, []
    if acc["role"] == "admin":
        pages = {"overview": P(admin_pages.overview_page, title="Overview", url_path="admin", default=True),
                 "admin-flats": P(admin_pages.flats_page, title="Flat groups", url_path="admin-flats"),
                 "admin-people": P(admin_pages.people_page, title="People", url_path="admin-people"),
                 "admin-listings": P(admin_pages.review_page, title="Listings to review", url_path="admin-listings"),
                 "admin-flags": P(admin_pages.flags_page, title="Flags", url_path="admin-flags"),
                 "admin-model": P(admin_pages.model_page, title="Model checks", url_path="admin-model")}
        return pages, list(pages)

    uid = acc["user_id"]
    has_profile = uid in set(load_cohort()["id"])
    listings = store.load("listings")
    owns = any(li["owner_id"] == uid for li in listings)
    rents = bool(actions.tenancies_for_member(uid) or actions.tenancies_for_lister(uid))
    # New members start on the quiz; someone who only lists a space starts on Home.
    default = "home" if has_profile or owns or rents else "onboarding"
    spec = [("home", member_pages.home_page, "Home"),
            ("explore", market_pages.explore_page, "Explore"),
            ("matches", member_pages.matches_page, "Flatmates"),
            ("group", market_pages.group_page, "My group"),
            ("listings", market_pages.listings_page, "My listings"),
            ("rent", market_pages.rent_page, "Rent"),
            ("profile", member_pages.profile_page, "Profile"),
            ("answers", member_pages.answers_page, "Your answers"),
            ("onboarding", member_pages.onboarding_page, "Lifestyle quiz")]
    pages = {k: P(fn, title=t, url_path=k, default=(k == default)) for k, fn, t in spec}
    visible = {"home": True, "explore": True, "matches": has_profile, "group": bool(actions.my_group(uid)),
               "listings": owns, "rent": rents, "profile": has_profile}
    return pages, [k for k, show in visible.items() if show]


# Every path the app can show, so the theme choice is saved for all of them.
ALL_PATHS = ["/", "/login", "/signup", "/home", "/explore", "/matches", "/group", "/listings", "/rent", "/profile",
             "/answers", "/onboarding", "/admin", "/admin-flats", "/admin-people", "/admin-listings", "/admin-flags",
             "/admin-model"]

pages, shown = build_pages()
nav.PAGES.clear()
nav.PAGES.update(pages)
current = st.navigation(list(pages.values()), position="hidden")

# ---------------------------------------------------------------------------
# Top bar: logo and wordmark, route links, theme toggle, account menu
# ---------------------------------------------------------------------------
ss = st.session_state
dark = theme.mode() == "dark"


def _toggle_theme():
    ss.theme_target = "light" if dark else "dark"


with st.container(key="topbar", horizontal=True, vertical_alignment="center", gap="medium"):
    is_admin = acc is not None and acc["role"] == "admin"
    st.html("<div class='brand'><span class='logo' aria-hidden='true'></span><span class='wordmark'>nestmate</span>"
            f"{'<span class=console>Admin</span>' if is_admin else ''}</div>", width="content")
    if acc is not None and len(shown) > 1:
        with st.container(key="nav", horizontal=True, gap=None, width="content"):
            for key in shown:
                page = pages[key]
                # WHY a keyed wrapper: it lets CSS mark the current route (Streamlit
                # doesn't expose an "active" attribute on page links).
                state = "on" if page.url_path == current.url_path else "off"
                with st.container(key=f"nav-{state}-{key}", width="content"):
                    st.page_link(page, label=page.title)
    with st.container(horizontal=True, horizontal_alignment="right", vertical_alignment="center",
                      gap="small", key="actions"):
        st.button("", icon=":material/light_mode:" if dark else ":material/dark_mode:", type="tertiary",
                  key="theme-btn", help="Switch to light mode" if dark else "Switch to dark mode",
                  on_click=_toggle_theme)
        if acc is not None:
            with st.popover(acc["name"].split()[0], icon=":material/account_circle:", key="account"):
                role = "Admin" if acc["role"] == "admin" else "Member"
                org = acc.get("organisation") or ("Property owner" if acc["user_id"].startswith("O") else "")
                st.html(f"<div class='acct'><span class='avatar me'>{esc(initials(acc['name']))}</span><div>"
                        f"<div class='n'>{esc(acc['name'])}</div><div class='m'>{esc(acc['email'])}</div>"
                        f"<div class='chips'><span class='chip ok'>{role}</span>"
                        f"{f'<span class=chip>{esc(org)}</span>' if org else ''}"
                        f"{'<span class=\"chip warn\">Demo account</span>' if acc.get('demo') else ''}</div></div></div>"
                        f"<p class='fine'>Generated text uses "
                        f"{'Gemini, with a cache' if llm.llm_available() else 'templates (no API key set)'}, "
                        f"and is labelled where it appears.</p>")
                if acc["role"] == "member" and "answers" in pages and acc["user_id"] in set(load_cohort()["id"]):
                    st.page_link(pages["answers"], label="Your answers", icon=":material/tune:")
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

msg = session.pop_flash()
if msg:
    st.success(msg, icon=":material/check_circle:")

current.run()
