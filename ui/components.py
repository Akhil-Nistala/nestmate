"""
Small, reusable building blocks shared by member and admin pages.

WHY hand-written HTML for these: a few product-specific pieces (the fit key
tag, the habit grid, the stat strip) carry most of Nestmate's look, while the
interactive parts stay native Streamlit widgets.
All user-supplied text goes through esc() because names, listings and free
text come from sign-ups.
"""
import html

import streamlit as st

from core import market
from core.cluster import run_clustering
from core.encode import load_cohort
from core.evaluate import evaluate
from core.grouping import build_all
from core.schema import QUESTION_UI, QUESTIONS, TRAIT_SHORT

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


def engine():
    """(cohort, clustering, results, market context) for the current data."""
    cohort = load_cohort()
    cl, res = compute(cohort)
    return cohort, cl, res, market.make_ctx(cohort, cl, res)


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------
def md(markup):
    # WHY strip each line: Markdown treats 4-space-indented lines as code blocks,
    # which would print our HTML as text.
    st.markdown(" ".join(line.strip() for line in markup.splitlines()), unsafe_allow_html=True)


def label(trait, value):
    """Answer text as stored (also what the LLM sees)."""
    return QUESTIONS[trait]["options"][int(value)]


def choice(trait, value):
    """Answer text as shown on screen."""
    return QUESTION_UI[trait]["choices"][int(value)]


def persona_label(name):
    """Persona names are stored as 'Night-owl · Social' (they are part of LLM
    prompts and the cache, so the stored form can't change). On screen they read
    as 'Night-owl, social'."""
    parts = name.rstrip("+").split(" · ")
    return ", ".join([parts[0]] + [p[:1].lower() + p[1:] for p in parts[1:]])


def money(n):
    return f"₹{int(n):,}"


def join_and(items):
    items = list(items)
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def first(name):
    return name.split()[0]


def initials(name):
    parts = name.replace(".", "").split()
    return (parts[0][0] + (parts[-1][0] if len(parts) > 1 else "")).upper()


# ---------------------------------------------------------------------------
# Small pieces
# ---------------------------------------------------------------------------
def avatar(name, me=False, size=""):
    return f"<span class='avatar {'me' if me else ''} {size}' aria-hidden='true'>{esc(initials(name))}</span>"


def chip(text, kind=""):
    """Small tag. kind: '' | ok | warn | you. `text` must already be safe HTML."""
    return f"<span class='chip {kind}'>{text}</span>"


def src_tag(source):
    # Honest labelling: every generated text says whether an LLM or a template wrote it.
    ai = source == "AI"
    return (f"<span class='src {'ai' if ai else ''}'><i aria-hidden='true'></i>"
            f"{'Written by AI' if ai else 'From a template'}</span>")


def key_tag(score, unit="% fit", title=None):
    """The fit score as a key tag: the one marigold shape on a card."""
    if score is None:
        return ""
    t = f" title='{esc(title)}'" if title else ""
    return (f"<span class='keytag'{t} aria-label='{score:.0f}{unit}'>"
            f"<b>{score:.0f}</b><span>{unit}</span></span>")


def page_head(title, sub=None):
    md(f"""<div class='page-head'><h1 class='display'>{title}</h1>
        {f"<p>{sub}</p>" if sub else ''}</div>""")


def stats(items):
    """One bordered strip split into cells. items: (label, value) or (label, value, hint)."""
    cells = "".join(f"<div class='stat'><div class='l'>{i[0]}</div><div class='v'>{i[1]}</div>"
                    f"{f'<div class=h>{i[2]}</div>' if len(i) > 2 and i[2] else ''}</div>" for i in items)
    md(f"<div class='stats'>{cells}</div>")


def section(title, sub=None):
    md(f"<div class='section'><h3>{title}</h3>{f'<p>{sub}</p>' if sub else ''}</div>")


def kv_table(rows):
    body = "".join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in rows)
    return f"<table class='kv'>{body}</table>"


def empty(title, body):
    md(f"<div class='empty'><div class='t'>{title}</div><div class='b'>{body}</div></div>")


def progress(done, total, text=None):
    pct = 0 if not total else round(100 * done / total)
    md(f"<div class='progress' role='progressbar' aria-valuenow='{pct}' aria-valuemin='0' aria-valuemax='100'>"
       f"<div style='width:{pct}%'></div></div>" + (f"<p class='fine'>{text}</p>" if text else ""))


# ---------------------------------------------------------------------------
# Habit grid: why a group fits, one column per person
# ---------------------------------------------------------------------------
GRID_TRAITS = ["sleep_time", "cleanliness", "guests_frequency", "food", "smoking"]
VERDICT = {"same": ("Same", "ok"), "close": ("Close", ""), "differs": ("Differs", "warn")}


def verdict(values):
    spread = max(values) - min(values)
    return "same" if spread == 0 else "close" if spread == 1 else "differs"


def habit_grid(people, me_id=None, traits=GRID_TRAITS):
    """people: dicts with id, name and the trait answers. The viewer is shown as 'You'.
    Scrolls sideways on narrow screens instead of squashing the columns."""
    if not people:
        return ""
    head = "".join(f"<th scope='col'>{avatar(p['name'], p['id'] == me_id)}"
                   f"<span>{'You' if p['id'] == me_id else esc(first(p['name']))}</span></th>" for p in people)
    body = ""
    for t in traits:
        vals = [int(p[t]) for p in people]
        v_text, v_kind = VERDICT[verdict(vals)]
        cells = "".join(f"<td>{esc(choice(t, v))}</td>" for v in vals)
        body += (f"<tr><th scope='row'>{TRAIT_SHORT[t].capitalize()}</th>{cells}"
                 f"<td class='verdict'>{chip(v_text, v_kind) if len(people) > 1 else ''}</td></tr>")
    return (f"<div class='grid-wrap'><table class='habits'><thead><tr><th scope='col'><span class='sr'>Habit</span></th>"
            f"{head}<th scope='col'><span class='sr'>Verdict</span></th></tr></thead><tbody>{body}</tbody></table></div>")


def people_row(people, me_id=None, note=None):
    """Avatars with names and where they work."""
    items = "".join(
        f"<div class='person'>{avatar(p['name'], p['id'] == me_id)}<div class='who'>"
        f"<div class='n'>{esc(p['name'])}{chip('You', 'you') if p['id'] == me_id else ''}</div>"
        f"<div class='m'>{esc(p.get('organisation') or '')}"
        f"{', ' + esc(p['office_location']) if p.get('office_location') else ''}</div></div>"
        f"{note(p) if note else ''}</div>" for p in people)
    return f"<div class='people'>{items}</div>"


def areas_list(areas):
    rows = "".join(f"<tr><td>{esc(a['area'])}{'' if a['fits_budget'] else ' ' + chip('Over budget', 'warn')}</td>"
                   f"<td class='num'>{money(a['rent'])} each, {a['avg_commute']} min</td></tr>" for a in areas)
    return f"<table class='list'><tbody>{rows}</tbody></table>"
