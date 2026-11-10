"""
Login session that survives a browser refresh.

WHY: Streamlit forgets st.session_state on every page reload, and switching
light/dark theme needs a reload. Without this, toggling the theme would log
you out. We keep a small server-side store keyed by a random session id and
put only that id in a cookie (the same pattern as a normal web session).

All per-user app state lives in ONE dict (st.session_state.app) that is also
the object stored server-side, so every change is persisted automatically.
"""
import secrets

import streamlit as st

COOKIE = "nm_sid"
MAX_AGE = 7 * 24 * 3600  # one week


@st.cache_resource
def _store():
    # sid -> app-state dict. Process memory is fine for a prototype; in
    # production this would be Redis or the database.
    return {}


def _fresh(account=None):
    return {"account": account, "decisions": {}, "formed": None, "extracted": {}, "groups_ready": False}


def init():
    """Call once at the top of every run. Restores a session from the cookie."""
    ss = st.session_state
    if "app" not in ss:
        sid = st.context.cookies.get(COOKIE)
        saved = _store().get(sid) if sid else None
        ss.app, ss.sid = (saved, sid) if saved else (_fresh(), None)
    return ss.app


def state():
    return st.session_state.app


def account():
    return st.session_state.app["account"]


def log_in(acc):
    sid = secrets.token_urlsafe(24)
    st.session_state.app = _fresh(acc)
    st.session_state.sid = sid
    _store()[sid] = st.session_state.app


def log_out():
    _store().pop(st.session_state.get("sid"), None)
    st.session_state.app = _fresh()
    st.session_state.sid = None


def cookie_js():
    """JS that writes (or clears) the session cookie. Rendered on every run."""
    sid = st.session_state.get("sid")
    if sid:
        return f"document.cookie='{COOKIE}={sid}; path=/; max-age={MAX_AGE}; SameSite=Lax';"
    return f"document.cookie='{COOKIE}=; path=/; max-age=0; SameSite=Lax';"
