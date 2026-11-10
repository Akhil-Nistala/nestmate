"""
Small, reusable building blocks shared by member and admin pages.

WHY hand-written HTML for these: Streamlit's defaults make every app look the
same. A handful of tidy components (page header, stat strip, chips, score ring)
give Nestmate its own look while the interactive parts stay native widgets.
All user-supplied text goes through esc() because names and free text come
from sign-ups.
"""
import html
import math

import streamlit as st

from core.cluster import run_clustering
from core.evaluate import evaluate
from core.grouping import build_all
from core.schema import QUESTIONS

esc = html.escape


# ---------------------------------------------------------------------------
# Cached computation (shared across users; results are read-only)
# ---------------------------------------------------------------------------
@st.cache_resource(show_spinner=False, max_entries=4)
def compute(df):
    cl = run_clustering(df)
    return cl, build_all(df, cl)


@st.cache_resource(show_spinner=False, max_entries=2)
def cached_eval(df):
    return evaluate(df)


# ---------------------------------------------------------------------------
# HTML helpers
# ---------------------------------------------------------------------------
def md(markup):
    # WHY strip each line: Markdown treats 4-space-indented lines as code blocks,
    # which would print our HTML as text.
    st.markdown(" ".join(line.strip() for line in markup.splitlines()), unsafe_allow_html=True)


def label(trait, value):
    return QUESTIONS[trait]["options"][int(value)]


def initials(name):
    parts = name.split()
    return (parts[0][0] + (parts[-1][0] if len(parts) > 1 else "")).upper()


def avatar(name, me=False, size=""):
    return f"<span class='avatar {'me' if me else ''} {size}'>{esc(initials(name))}</span>"


def chip(text, kind=""):
    return f"<span class='chip {kind}'>{text}</span>"


def src_tag(source):
    # Honest labelling: every generated text says whether an LLM or a template wrote it.
    return f"<span class='src {'ai' if source == 'AI' else ''}'>{'AI' if source == 'AI' else 'Template'}</span>"


def page_head(title, sub=None, eyebrow=None):
    md(f"""<div class='page-head'>
        {f"<div class='eyebrow'>{eyebrow}</div>" if eyebrow else ''}
        <h1 class='display'>{title}</h1>
        {f"<p>{sub}</p>" if sub else ''}</div>""")


def stats(items):
    """items: (label, value) or (label, value, hint)."""
    cells = "".join(f"<div class='stat'><div class='l'>{i[0]}</div><div class='v'>{i[1]}</div>"
                    f"{f'<div class=h>{i[2]}</div>' if len(i) > 2 else ''}</div>" for i in items)
    md(f"<div class='stats'>{cells}</div>")


def section(title, sub=None):
    md(f"<div class='section'><h3>{title}</h3>{f'<p>{sub}</p>' if sub else ''}</div>")


def ring(score, size=76):
    """Circular match score. WHY a ring: one glanceable number per card."""
    r, sw = 30, 6
    c = 2 * math.pi * r
    off = c * (1 - max(0, min(100, score)) / 100)
    return (f"<svg class='ring' width='{size}' height='{size}' viewBox='0 0 72 72' aria-label='{score:.0f} out of 100'>"
            f"<circle cx='36' cy='36' r='{r}' fill='none' stroke='var(--line)' stroke-width='{sw}'/>"
            f"<circle cx='36' cy='36' r='{r}' fill='none' stroke='var(--accent)' stroke-width='{sw}' "
            f"stroke-linecap='round' stroke-dasharray='{c:.1f}' stroke-dashoffset='{off:.1f}' "
            f"transform='rotate(-90 36 36)'/>"
            f"<text x='36' y='41' text-anchor='middle' class='ring-v'>{score:.0f}</text></svg>")


def kv_table(rows):
    body = "".join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in rows)
    return f"<table class='kv'>{body}</table>"


def empty(title, body):
    md(f"<div class='empty'><div class='t'>{title}</div><div class='b'>{body}</div></div>")
