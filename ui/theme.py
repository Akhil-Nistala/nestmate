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
    # Cool stone neutrals; two meaning colours: rani pink = actions, selection and
    # "you"; marigold = fit scores and progress only. Status colours are separate.
    "light": {
        "bg": "#F4F4F1", "surface": "#FFFFFF", "surface-2": "#EEEFEB", "ink": "#1B1C1F", "ink-2": "#45474D",
        "muted": "#6B6D73", "line": "#DCDDD8", "line-2": "#E9EAE6",
        "accent": "#A8224F", "accent-ink": "#FFFFFF", "accent-weak": "#F7E4EB", "accent-line": "#E5B5C6",
        "score": "#F3B51B", "score-ink": "#1B1C1F",
        "ok": "#23704A", "ok-weak": "#E2F0E8", "warn": "#A55308", "warn-weak": "#FBEBDC",
        "ai": "#3C55B5", "ai-weak": "#E6EAF8", "focus": "#A8224F",
    },
    "dark": {
        "bg": "#141517", "surface": "#1C1D20", "surface-2": "#25262A", "ink": "#ECECE8", "ink-2": "#C9CAC4",
        "muted": "#8D8F95", "line": "#34363B", "line-2": "#2A2C30",
        "accent": "#E5517F", "accent-ink": "#141517", "accent-weak": "#3A1B26", "accent-line": "#7A2E47",
        "score": "#F5C243", "score-ink": "#1B1C1F",
        "ok": "#5CC08A", "ok-weak": "#17291F", "warn": "#E8954A", "warn-weak": "#33230F",
        "ai": "#8EA2F0", "ai-weak": "#1F2540", "focus": "#E5517F",
    },
}

# Persona colours for charts: fixed order, validated for colour-blind separation,
# lightness and contrast against each mode's surface (dataviz palette validator).
# Deliberately not pink or marigold, which carry meaning elsewhere in the app.
PERSONA_COLORS = {
    "light": ["#2a78d6", "#169c6c", "#8f5ad6", "#a66b05", "#0089b0", "#6e7f19"],
    "dark": ["#3987e5", "#199e70", "#9a6be0", "#b07a10", "#0f95bd", "#7d8c1f"],
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
                      margin=dict(l=4, r=4, t=8, b=4), font=dict(family="Schibsted Grotesk, system-ui, sans-serif", size=12, color=t["ink-2"]),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      hoverlabel=dict(bgcolor=t["surface"], bordercolor=t["line"], font=dict(color=t["ink"])),
                      legend=dict(orientation="h", y=-0.08, title=None, font=dict(color=t["ink-2"])))
    fig.update_xaxes(gridcolor=t["line-2"], zeroline=False, linecolor=t["line"], tickfont=dict(color=t["muted"]))
    fig.update_yaxes(gridcolor=t["line-2"], zeroline=False, linecolor=t["line"], tickfont=dict(color=t["muted"]))
    return fig
