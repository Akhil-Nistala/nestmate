"""
Design tokens for light and dark mode, shared by CSS and charts.

WHY tokens in Python (not only in the CSS file): Plotly charts are drawn from
Python, so they need the same colours. One dict per mode keeps the custom HTML,
the charts and Streamlit's own theme (.streamlit/config.toml) in sync.
"""
import json
import os

import streamlit as st

TOKENS = {
    "light": {
        "bg": "#F6F4EF", "surface": "#FFFFFF", "surface-2": "#F1EEE7", "ink": "#1A1917", "ink-2": "#46423C",
        "muted": "#7C776E", "line": "#E2DDD3", "line-2": "#ECE8E0", "accent": "#C2512A", "accent-ink": "#FFFFFF",
        "accent-weak": "#F8E8E0", "ok": "#2F7D4F", "ok-weak": "#E5F1E9", "warn": "#9A5B0B", "warn-weak": "#FAEFD9",
        "ai": "#6447B8", "ai-weak": "#EEEAFB", "hero": "#1A1917", "hero-ink": "#F6F4EF", "hero-muted": "#A8A397",
        "shadow": "0 1px 2px rgba(26,25,23,.04), 0 8px 24px -12px rgba(26,25,23,.12)",
    },
    "dark": {
        "bg": "#131211", "surface": "#1B1A18", "surface-2": "#23211E", "ink": "#F2EFE9", "ink-2": "#D2CDC3",
        "muted": "#928C82", "line": "#2F2C28", "line-2": "#262421", "accent": "#E2734C", "accent-ink": "#1A1917",
        "accent-weak": "#3A2219", "ok": "#6DBA8D", "ok-weak": "#1C2B22", "warn": "#DDA94A", "warn-weak": "#33280F",
        "ai": "#AD9BF2", "ai-weak": "#2A2340", "hero": "#1F1D1A", "hero-ink": "#F2EFE9", "hero-muted": "#928C82",
        "shadow": "0 1px 2px rgba(0,0,0,.3), 0 8px 24px -12px rgba(0,0,0,.6)",
    },
}

# Persona colours: earthy and distinguishable, readable on both backgrounds.
PERSONA_COLORS = {
    "light": ["#C2512A", "#3F7D5C", "#4F5BB8", "#C08A1E", "#9A4C8C", "#3C83A8"],
    "dark": ["#E2734C", "#5FA77E", "#7C86D9", "#D6A23B", "#B970A9", "#5AA3C7"],
}


def mode():
    """The theme the viewer's browser is showing ("light" if not yet known)."""
    return "dark" if st.context.theme.type == "dark" else "light"


def tok(name):
    return TOKENS[mode()][name]


CSS_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "style.css")


@st.cache_resource
def _css(mtime):
    # Keyed on the file's modified time: cached between clicks, refreshed on edit.
    with open(CSS_PATH, encoding="utf-8") as f:
        return f.read()


def inject_css():
    root = ";".join(f"--{k}:{v}" for k, v in TOKENS[mode()].items())
    # NB: st.html treats the block as a pure stylesheet only if it holds no other
    # tags, so style.css must never contain "<" (not even in comments).
    st.html(f"<style>:root{{{root}}}{_css(os.path.getmtime(CSS_PATH))}</style>")


def switch_js(target, paths):
    """JS that switches Streamlit's theme and reloads.

    WHY localStorage + reload: Streamlit has no Python API to change the theme.
    Its frontend reads the choice from localStorage (one key per URL path) when
    the page loads, which is exactly what its own Settings menu does."""
    value = json.dumps("Dark" if target == "dark" else "Light")
    keys = json.dumps([f"stActiveTheme-{p}-v2" for p in paths])
    return f"{keys}.forEach(k => localStorage.setItem(k, {json.dumps(value)})); window.location.reload();"


def style_fig(fig, height=360):
    t = TOKENS[mode()]
    fig.update_layout(template="plotly_dark" if mode() == "dark" else "plotly_white", height=height,
                      margin=dict(l=4, r=4, t=8, b=4), font=dict(family="Geist, sans-serif", size=12, color=t["ink-2"]),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      hoverlabel=dict(bgcolor=t["surface"], bordercolor=t["line"], font=dict(color=t["ink"])),
                      legend=dict(orientation="h", y=-0.08, title=None, font=dict(color=t["ink-2"])))
    fig.update_xaxes(gridcolor=t["line-2"], zeroline=False, linecolor=t["line"], tickfont=dict(color=t["muted"]))
    fig.update_yaxes(gridcolor=t["line-2"], zeroline=False, linecolor=t["line"], tickfont=dict(color=t["muted"]))
    return fig
