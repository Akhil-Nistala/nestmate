"""
Admin (HR) routes: cohort overview, flat groups, people, model checks.

WHY a separate route: HR needs the cohort-wide picture (who is joining, which
lifestyles, how many are placed); a fresher should never see other people's
data outside their suggested groups. The router only registers these pages
for admin accounts, and each page re-checks the role (defence in depth).
"""
import pandas as pd
import plotly.express as px
import streamlit as st

from core.encode import load_cohort
from core.schema import OFFICES, TRAITS
from ui import session
from ui.components import cached_eval, compute, esc, label, md, page_head, section, stats
from ui.theme import PERSONA_COLORS, mode, style_fig, tok


def _require_admin():
    acc = session.account()
    if not acc or acc.get("role") != "admin":
        st.error("This page is for HR admins only.")
        st.stop()


def _colors(cl):
    names = [p["name"] for p in cl["personas"].values()]
    pal = PERSONA_COLORS[mode()]
    return {n: pal[i % len(pal)] for i, n in enumerate(names)}


def _load():
    cohort = load_cohort()
    with st.spinner("Clustering the cohort…"):
        cl, res = compute(cohort)
    return cohort, cl, res


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------
def overview_page():
    _require_admin()
    cohort, cl, res = _load()
    org = session.account().get("organisation") or "Partner"
    page_head("Cohort overview", "Who is joining, which lifestyles we see, and how they group into flats.",
              eyebrow=f"{esc(org)} · HR console")
    placed = sum(g["size"] for g in res["groups"])
    stats([("Cohort size", len(cohort), f"{cohort['organisation'].nunique()} organisations"),
           ("Lifestyle personas", len(cl["personas"]), f"silhouette {cl['silhouette']:.2f}"),
           ("Flat groups", len(res["groups"]), f"avg match {sum(g['score'] for g in res['groups']) / max(1, len(res['groups'])):.0f}"),
           ("Placed", f"{placed / len(cohort):.0%}", f"{len(res['unmatched'])} need follow-up")])

    colors = _colors(cl)
    left, right = st.columns([3, 2], gap="large")
    with left, st.container(key="chart-map"):
        section("Cohort map", "Each dot is a person, placed by lifestyle similarity (PCA of the quiz).")
        pts = cl["points"].merge(cohort[["id", "organisation"] + TRAITS], on="id")
        pts["traits"] = pts.apply(lambda r: " · ".join(label(t, r[t]) for t in
                                                       ("sleep_time", "cleanliness", "guests_frequency")), axis=1)
        fig = px.scatter(pts, x="pc1", y="pc2", color="persona", hover_name="name", color_discrete_map=colors,
                         hover_data={"persona": True, "organisation": True, "traits": True, "pc1": False, "pc2": False})
        fig.update_traces(marker=dict(size=8, opacity=0.85, line=dict(width=1, color=tok("surface"))))
        fig = style_fig(fig, 380)
        fig.update_layout(showlegend=False)
        fig.update_xaxes(showticklabels=False, title=None, showgrid=False, showline=False)
        fig.update_yaxes(showticklabels=False, title=None, showgrid=False, showline=False)
        st.plotly_chart(fig, width="stretch", theme=None, config={"displayModeBar": False})
    with right, st.container(key="chart-personas"):
        section("Personas", "Found by k-means; named from their strongest traits.")
        total = len(cohort)
        rows = ""
        for p in sorted(cl["personas"].values(), key=lambda p: -p["size"]):
            share = p["size"] / total
            rows += (f"<div class='persona-row'><div class='pr-top'><span class='dot' style='background:{colors[p['name']]}'></span>"
                     f"<b>{esc(p['name'])}</b><span class='pr-n'>{p['size']} · {share:.0%}</span></div>"
                     f"<div class='meter'><div style='width:{share * 100:.1f}%;background:{colors[p['name']]}'></div></div>"
                     f"<div class='pr-d'>{esc(p['description'])}</div></div>")
        md(rows)

    left, right = st.columns(2, gap="large")
    with left, st.container(key="chart-office"):
        section("Demand by office", "Where people will commute to, by persona.")
        d = cl["points"].merge(cohort[["id", "office_location"]], on="id")
        d = d.groupby(["office_location", "persona"]).size().reset_index(name="people")
        fig = px.bar(d, y="office_location", x="people", color="persona", orientation="h",
                     color_discrete_map=colors, category_orders={"office_location": OFFICES})
        fig.update_traces(marker_line_width=0)
        fig = style_fig(fig, 300)
        fig.update_layout(bargap=0.45)
        fig.update_xaxes(title=None)
        fig.update_yaxes(title=None, showgrid=False)
        st.plotly_chart(fig, width="stretch", theme=None, config={"displayModeBar": False})
    with right, st.container(key="chart-k"):
        section("How many personas?", "Silhouette score by number of clusters; the highest wins.")
        s = pd.DataFrame({"k": list(cl["silhouette_scores"]), "score": list(cl["silhouette_scores"].values())})
        fig = px.line(s, x="k", y="score", markers=True)
        fig.update_traces(line=dict(color=tok("accent"), width=2.5), marker=dict(size=8, color=tok("accent")))
        fig.add_vline(x=cl["best_k"], line=dict(color=tok("line"), width=1, dash="dot"))
        fig.add_annotation(x=cl["best_k"], y=cl["silhouette"], text=f"k = {cl['best_k']}", showarrow=False,
                           yshift=16, font=dict(color=tok("accent"), size=12))
        fig = style_fig(fig, 300)
        fig.update_xaxes(title=None, dtick=1)
        fig.update_yaxes(title=None)
        st.plotly_chart(fig, width="stretch", theme=None, config={"displayModeBar": False})


# ---------------------------------------------------------------------------
# Flat groups
# ---------------------------------------------------------------------------
def flats_page():
    _require_admin()
    cohort, cl, res = _load()
    page_head("Flat groups", "Scores every pair, applies dealbreakers, budget and gender rules, builds flats "
                             "inside each persona, then improves them with swaps.", eyebrow="HR console")
    state = session.state()
    if not state["groups_ready"]:
        # WHY a button: in the demo, HR triggers matching for the cohort; it is the
        # moment the panel sees the whole pipeline run.
        if st.button("Form flat groups", type="primary", icon=":material/group_work:"):
            state["groups_ready"] = True
            st.rerun()
        return
    g = res["groups"]
    placed = sum(x["size"] for x in g)
    stats([("Flat groups", len(g)), ("People placed", f"{placed} / {len(cohort)}"),
           ("Average match", f"{sum(x['score'] for x in g) / max(1, len(g)):.0f} / 100"),
           ("Unmatched", len(res["unmatched"]))])
    table = pd.DataFrame([{"Group": x["group_id"], "Match": x["score"], "Persona": x["persona"],
                           "Members": ", ".join(m["name"] for m in x["members"]),
                           "Size": f"{x['size']} / {x['target']}", "Offices": ", ".join(x["offices"]),
                           "Budget (₹)": f"{x['budget'][0]:,} – {x['budget'][1]:,}"} for x in g])
    st.dataframe(table, hide_index=True, width="stretch", height=420,
                 column_config={"Match": st.column_config.ProgressColumn("Match", min_value=0, max_value=100,
                                                                         format="%.0f", width="small"),
                                "Group": st.column_config.TextColumn(width="small"),
                                "Members": st.column_config.TextColumn(width="large")})
    if res["unmatched"]:
        section(f"Needs follow-up ({len(res['unmatched'])})", "People we couldn't place, and why.")
        st.dataframe(pd.DataFrame(res["unmatched"]).rename(columns={"id": "ID", "name": "Name", "reason": "Reason"}),
                     hide_index=True, width="stretch")


# ---------------------------------------------------------------------------
# People
# ---------------------------------------------------------------------------
def people_page():
    _require_admin()
    cohort, cl, res = _load()
    page_head("People", "Everyone in the joining cohort, with their persona and flat.", eyebrow="HR console")
    group_of = {mid: g["group_id"] for g in res["groups"] for mid in g["member_ids"]}
    df = cohort.merge(cl["points"][["id", "persona"]], on="id")
    df["Flat"] = df["id"].map(group_of).fillna("Unmatched")
    df["Budget (₹)"] = df.apply(lambda r: f"{r['budget_min']:,} – {r['budget_max']:,}", axis=1)

    c1, c2, c3 = st.columns([2, 1.2, 1.2], gap="small")
    q = c1.text_input("Search", placeholder="Name, email or organisation", label_visibility="collapsed",
                      icon=":material/search:")
    personas = c2.multiselect("Persona", sorted(df["persona"].unique()), placeholder="All personas",
                              label_visibility="collapsed")
    offices = c3.multiselect("Office", OFFICES, placeholder="All offices", label_visibility="collapsed")
    if q:
        hay = (df["name"] + " " + df["email"] + " " + df["organisation"]).str.lower()
        df = df[hay.str.contains(q.lower(), regex=False)]
    if personas:
        df = df[df["persona"].isin(personas)]
    if offices:
        df = df[df["office_location"].isin(offices)]
    md(f"<p class='fine' style='margin:4px 0 8px'>{len(df)} of {len(cohort)} people</p>")
    view = df.rename(columns={"name": "Name", "organisation": "Organisation", "office_location": "Office",
                              "joining_month": "Joining", "gender": "Gender", "persona": "Persona",
                              "flat_size_pref": "Flat size", "email": "Email"})
    st.dataframe(view[["Name", "Organisation", "Office", "Joining", "Gender", "Persona", "Flat size",
                       "Budget (₹)", "Flat", "Email"]], hide_index=True, width="stretch", height=560)


# ---------------------------------------------------------------------------
# Model checks
# ---------------------------------------------------------------------------
def model_page():
    _require_admin()
    cohort = load_cohort()
    page_head("Model checks", "How much to trust the personas and groups.", eyebrow="HR console")
    md("<div class='panel'><div class='label'>What these mean</div><p class='fine' style='margin:0'>"
       "<b>ARI</b> compares our clusters with the hidden synthetic archetypes (1 = perfect, 0 = random). "
       "<b>Stability</b> re-runs the pipeline and checks it agrees with itself. The <b>random baseline</b> "
       "uses the same group sizes with random people, so the gap shows what matching adds.</p></div>")
    if st.button("Run checks", type="primary", icon=":material/play_arrow:"):
        with st.spinner("Re-running the pipeline twice…"):
            st.dataframe(pd.DataFrame(cached_eval(cohort).items(), columns=["Check", "Value"]).astype(str),
                         hide_index=True, width="stretch")
