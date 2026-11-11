"""
Admin (HR) routes: cohort overview, flat groups, people, model checks.

WHY a separate route: HR needs the cohort-wide picture (who is joining, which
lifestyles, how many are placed); a fresher should never see other people's
data outside their suggested groups. The router only registers these pages
for admin accounts, and each page re-checks the role (defence in depth).

WHY scoped to the admin's organisation: in the B2B2C model each partner org is
a separate customer. Matching runs on the WHOLE partner cohort (a Deloitte
joiner can share a flat with an IITH intern), but Deloitte HR only sees
Deloitte joiners. People from other orgs in the same flat are shown as a count,
never by name. Aggregate model checks (ARI, silhouette) contain no personal
data, so they stay cohort-wide.
"""
import pandas as pd
import plotly.express as px
import streamlit as st

from core.encode import load_cohort
from core.schema import OFFICES, TRAITS
from ui import session
from ui.components import (cached_eval, compute, empty, esc, label, md, money, page_head, persona_label, section,
                           stats)
from ui.theme import PERSONA_COLORS, mode, style_fig, tok


def _require_admin():
    acc = session.account()
    if not acc or acc.get("role") != "admin":
        st.error("This page is for HR admins only.")
        st.stop()


def _colors(cl):
    names = [p["name"] for p in cl["personas"].values()]
    pal = PERSONA_COLORS[mode()]
    # Keyed by the stored name and by the on-screen label, so charts and lists agree.
    out = {n: pal[i % len(pal)] for i, n in enumerate(names)}
    out.update({persona_label(n): c for n, c in list(out.items())})
    return out


def _load():
    """Returns (org, org_cohort, clustering, groups) -- clustering and groups are
    computed on the whole cohort, org_cohort is only this admin's joiners."""
    org = session.account().get("organisation")
    if not org:
        st.error("This admin account isn't linked to a partner organisation.")
        st.stop()
    cohort = load_cohort()
    with st.spinner("Clustering the cohort…"):
        cl, res = compute(cohort)
    return org, cohort[cohort["organisation"] == org], cl, res


def _org_view(mine, res):
    """Groups containing at least one of this org's joiners, and this org's unmatched."""
    ids = set(mine["id"])
    groups = [g for g in res["groups"] if ids & set(g["member_ids"])]
    unmatched = [u for u in res["unmatched"] if u["id"] in ids]
    placed = sum(1 for g in groups for m in g["member_ids"] if m in ids)
    return ids, groups, unmatched, placed


def _no_joiners(org):
    empty(f"No {esc(org)} joiners yet", "People appear here once they sign up with your organisation's email.")


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------
def overview_page():
    _require_admin()
    org, mine, cl, res = _load()
    page_head("Cohort overview", f"Who is joining {esc(org)}, which lifestyles we see, and how they group into "
                                 "flats. Flats can include joiners from other partner organisations.")
    if mine.empty:
        _no_joiners(org)
        return
    ids, groups, unmatched, placed = _org_view(mine, res)
    counts = cl["points"][cl["points"]["id"].isin(ids)]["persona"].value_counts()
    stats([("Joiners", len(mine), f"from {esc(org)}"),
           ("Lifestyle personas", len(counts), f"of {len(cl['personas'])} across the partner cohort"),
           ("Flat groups", len(groups), f"average fit {sum(g['score'] for g in groups) / max(1, len(groups)):.0f}%"),
           ("Placed", f"{placed / len(mine):.0%}", f"{len(unmatched)} need follow-up")])

    colors = _colors(cl)
    left, right = st.columns([3, 2], gap="large")
    with left, st.container(key="chart-map"):
        section("Cohort map", "Each dot is a person, placed by lifestyle similarity (PCA of the quiz).")
        pts = cl["points"].merge(mine[["id"] + TRAITS], on="id")
        pts["persona"] = pts["persona"].map(persona_label)
        pts["traits"] = pts.apply(lambda r: ", ".join(label(t, r[t]) for t in
                                                       ("sleep_time", "cleanliness", "guests_frequency")), axis=1)
        fig = px.scatter(pts, x="pc1", y="pc2", color="persona", hover_name="name", color_discrete_map=colors,
                         hover_data={"persona": True, "traits": True, "pc1": False, "pc2": False})
        fig.update_traces(marker=dict(size=8, opacity=0.85, line=dict(width=1, color=tok("surface"))))
        fig = style_fig(fig, 380)
        fig.update_layout(showlegend=False)
        fig.update_xaxes(showticklabels=False, title=None, showgrid=False, showline=False)
        fig.update_yaxes(showticklabels=False, title=None, showgrid=False, showline=False)
        st.plotly_chart(fig, width="stretch", theme=None, config={"displayModeBar": False})
    with right, st.container(key="chart-personas"):
        section("Personas", "Found by k-means and named from their strongest traits.")
        total = len(mine)
        rows = ""
        for p in sorted(cl["personas"].values(), key=lambda p: -counts.get(p["name"], 0)):
            size = int(counts.get(p["name"], 0))
            if not size:
                continue
            share = size / total
            rows += (f"<div class='persona-row'><div class='pr-top'><span class='dot' style='background:{colors[p['name']]}'></span>"
                     f"<b>{esc(persona_label(p['name']))}</b><span class='pr-n'>{size} people, {share:.0%}</span></div>"
                     f"<div class='meter'><div style='width:{share * 100:.1f}%;background:{colors[p['name']]}'></div></div>"
                     f"<div class='pr-d'>{esc(p['description'])}</div></div>")
        md(rows)

    left, right = st.columns(2, gap="large")
    with left, st.container(key="chart-office"):
        section("Demand by office", "Where people will commute to, by persona.")
        d = cl["points"].merge(mine[["id", "office_location"]], on="id")
        d["persona"] = d["persona"].map(persona_label)
        d = d.groupby(["office_location", "persona"]).size().reset_index(name="people")
        fig = px.bar(d, y="office_location", x="people", color="persona", orientation="h",
                     color_discrete_map=colors, category_orders={"office_location": OFFICES})
        fig.update_traces(marker_line_width=2, marker_line_color=tok("surface"))  # 2px gap between segments
        fig = style_fig(fig, 300)
        fig.update_layout(bargap=0.45)
        fig.update_xaxes(title=None)
        fig.update_yaxes(title=None, showgrid=False)
        st.plotly_chart(fig, width="stretch", theme=None, config={"displayModeBar": False})
    with right, st.container(key="chart-k"):
        section("How many personas?", "Silhouette score for each number of clusters, across the partner cohort. "
                                      "The highest wins.")
        s = pd.DataFrame({"k": list(cl["silhouette_scores"]), "score": list(cl["silhouette_scores"].values())})
        fig = px.line(s, x="k", y="score", markers=True)
        series = PERSONA_COLORS[mode()][0]  # one series: the first categorical slot, not the action pink
        fig.update_traces(line=dict(color=series, width=2), marker=dict(size=8, color=series,
                                                                         line=dict(width=2, color=tok("surface"))))
        fig.add_vline(x=cl["best_k"], line=dict(color=tok("muted"), width=1, dash="dot"))
        fig.add_annotation(x=cl["best_k"], y=cl["silhouette"], text=f"Best: {cl['best_k']} personas", showarrow=False,
                           yshift=18, xshift=58, font=dict(color=tok("ink"), size=12))
        fig = style_fig(fig, 300)
        fig.update_xaxes(title=None, dtick=1)
        fig.update_yaxes(title=None)
        st.plotly_chart(fig, width="stretch", theme=None, config={"displayModeBar": False})


# ---------------------------------------------------------------------------
# Flat groups
# ---------------------------------------------------------------------------
def _members_cell(g, ids):
    """This org's members by name; anyone else only as a count."""
    names = [m["name"] for m in g["members"] if m["id"] in ids]
    others = g["size"] - len(names)
    return ", ".join(names) + (f" + {others} from other organisations" if others else "")


def _offices_cell(g, ids):
    """Offices of this org's members only. WHY not the flat budget too: the budget
    is the flat's shared rent band (what HR books against), not one person's data."""
    return ", ".join(sorted({m["office_location"] for m in g["members"] if m["id"] in ids}))


def flats_page():
    _require_admin()
    org, mine, cl, res = _load()
    page_head("Flat groups", f"Flats with at least one {esc(org)} joiner. Scores every pair, applies dealbreakers, "
                             "budget and gender rules, builds flats inside each persona, then improves them with "
                             "swaps.")
    state = session.state()
    if not state["groups_ready"]:
        # WHY a button: in the demo, HR triggers matching for the cohort; it is the
        # moment the panel sees the whole pipeline run.
        if st.button("Form flat groups", type="primary", icon=":material/group_work:"):
            state["groups_ready"] = True
            st.rerun()
        return
    if mine.empty:
        _no_joiners(org)
        return
    ids, g, unmatched, placed = _org_view(mine, res)
    stats([("Flat groups", len(g)), ("Joiners placed", f"{placed} of {len(mine)}"),
           ("Average fit", f"{sum(x['score'] for x in g) / max(1, len(g)):.0f}%"),
           ("Unmatched", len(unmatched))])
    table = pd.DataFrame([{"Group": x["group_id"], "Match": x["score"], "Persona": persona_label(x["persona"]),
                           "Members": _members_cell(x, ids),
                           "Size": f"{x['size']} of {x['target']}",
                           "Offices": _offices_cell(x, ids),
                           "Flat budget (₹)": f"{x['budget'][0]:,}–{x['budget'][1]:,}"} for x in g])
    st.dataframe(table, hide_index=True, width="stretch", height=420,
                 column_config={"Match": st.column_config.ProgressColumn("Match", min_value=0, max_value=100,
                                                                         format="%.0f", width="small"),
                                "Group": st.column_config.TextColumn(width="small"),
                                "Members": st.column_config.TextColumn(width="large")})
    if unmatched:
        section(f"Needs follow-up ({len(unmatched)})", "Joiners we couldn't place, and why.")
        st.dataframe(pd.DataFrame(unmatched).rename(columns={"id": "ID", "name": "Name", "reason": "Reason"}),
                     hide_index=True, width="stretch")


# ---------------------------------------------------------------------------
# People
# ---------------------------------------------------------------------------
def people_page():
    _require_admin()
    org, mine, cl, res = _load()
    page_head("People", f"Everyone joining {esc(org)}, with their persona and flat.")
    if mine.empty:
        _no_joiners(org)
        return
    group_of = {mid: g["group_id"] for g in res["groups"] for mid in g["member_ids"]}
    df = mine.merge(cl["points"][["id", "persona"]], on="id")
    df["persona"] = df["persona"].map(persona_label)
    df["Flat"] = df["id"].map(group_of).fillna("Unmatched")
    df["Budget (₹)"] = df.apply(lambda r: f"{r['budget_min']:,}–{r['budget_max']:,}", axis=1)

    c1, c2, c3 = st.columns([2, 1.2, 1.2], gap="small")
    q = c1.text_input("Search", placeholder="Name or email", label_visibility="collapsed",
                      icon=":material/search:")
    personas = c2.multiselect("Persona", sorted(df["persona"].unique()), placeholder="All personas",
                              label_visibility="collapsed")
    offices = c3.multiselect("Office", OFFICES, placeholder="All offices", label_visibility="collapsed")
    if q:
        hay = (df["name"] + " " + df["email"]).str.lower()
        df = df[hay.str.contains(q.lower(), regex=False)]
    if personas:
        df = df[df["persona"].isin(personas)]
    if offices:
        df = df[df["office_location"].isin(offices)]
    md(f"<p class='fine' style='margin:4px 0 8px'>{len(df)} of {len(mine)} people</p>")
    view = df.rename(columns={"name": "Name", "office_location": "Office",
                              "joining_month": "Joining", "gender": "Gender", "persona": "Persona",
                              "flat_size_pref": "Flat size", "email": "Email"})
    st.dataframe(view[["Name", "Office", "Joining", "Gender", "Persona", "Flat size",
                       "Budget (₹)", "Flat", "Email"]], hide_index=True, width="stretch", height=560)


# ---------------------------------------------------------------------------
# Model checks (aggregate only, so cohort-wide)
# ---------------------------------------------------------------------------
def model_page():
    _require_admin()
    cohort = load_cohort()
    page_head("Model checks", "How much to trust the personas and groups, measured on the whole partner cohort.")
    md("<div class='panel'><h3 class='panel-h'>What these mean</h3><p class='fine'>"
       "<b>ARI</b> compares our clusters with the hidden synthetic archetypes (1 = perfect, 0 = random). "
       "<b>Stability</b> re-runs the pipeline and checks it agrees with itself. The <b>random baseline</b> "
       "builds random flats of the same sizes that still obey every hard rule (budget, dealbreakers, gender), "
       "averaged over 20 shuffles, so the gap to the mean group score is what lifestyle matching adds. "
       "<b>Random ignoring rules</b> is shown for reference only.</p></div>")
    if st.button("Run checks", type="primary", icon=":material/play_arrow:"):
        with st.spinner("Re-running the pipeline twice…"):
            st.dataframe(pd.DataFrame(cached_eval(cohort).items(), columns=["Check", "Value"]).astype(str),
                         hide_index=True, width="stretch")


# ---------------------------------------------------------------------------
# Listings to review and Flags (platform-wide: listings aren't org data)
# ---------------------------------------------------------------------------
def _names():
    from core import actions
    return actions.name_lookup(load_cohort())


def _listing_summary(li, names):
    from ui.market_pages import lister_sentence, listing_title, rules_sentence
    rents = [r["rent"] for r in li["rooms"] if r["rent"] > 0 and not r.get("occupied_by")]
    from core import market
    avg = market.area_rent(li["area"])
    rows = "".join(f"<tr><td>{r['room_id']}</td><td class='num'>{money(r['rent']) if r['rent'] else 'Lister'}</td>"
                   f"<td>{esc(names(r['occupied_by'])) if r.get('occupied_by') else 'Free'}</td></tr>"
                   for r in li["rooms"])
    return (f"<h3 class='card-h'>{listing_title(li)}</h3>"
            f"<p class='card-p'>{esc(li['address_hint'])}. {lister_sentence(li, names)} {rules_sentence(li)}</p>"
            f"<p class='fine'>Rent {money(min(rents)) if rents else 'n/a'} to {money(max(rents)) if rents else 'n/a'} "
            f"a room; {esc(li['area'])} average is {money(avg)}. Deposit {li['deposit_months']} month"
            f"{'s' if li['deposit_months'] != 1 else ''}. Listed {li['created_at'][:10]}.</p>"
            f"<div class='grid-wrap'><table class='list'><thead><tr><th>Room</th><th class='num'>Rent</th>"
            f"<th>Who's there</th></tr></thead><tbody>{rows}</tbody></table></div>")


def review_page():
    _require_admin()
    from core import actions, market, store
    page_head("Listings to review", "New listings stay out of Explore until you approve them. "
                                    "Check the flags under each one first.")
    names = _names()
    listings = store.load("listings")
    pending = [li for li in listings if li["status"] == "pending"]
    flags = market.flags(listings, store.load("reports"), store.load("flag_actions"), names)
    stats([("Waiting for review", len(pending)), ("Live", sum(li["status"] == "approved" for li in listings)),
           ("Open flags", len(flags))])
    if not pending:
        empty("Nothing to review", "New listings will appear here as soon as someone sends one.")
    acc = session.account()
    for li in pending:
        mine = [f for f in flags if li["id"] in f["listing_ids"]]
        with st.container(key=f"review-{li['id']}"):
            md(_listing_summary(li, names))
            for f in mine:
                md(f"<p class='warnline'><b>{esc(f['kind'])}.</b> {esc(f['evidence'][0])}</p>")
            with st.container(horizontal=True, gap="small", vertical_alignment="bottom"):
                if st.button("Approve", type="primary", key=f"approve-{li['id']}"):
                    actions.review_listing(li["id"], True, by=acc["email"])
                    session.flash(f"Approved {li['id']}. It now shows in Explore.")
                    st.rerun()
                with st.popover("Reject", key=f"rejpop-{li['id']}"):
                    reason = st.text_input("Reason the lister will see", key=f"rejr-{li['id']}",
                                           placeholder="Rent far below the area; please confirm the price.")
                    if st.button("Reject listing", key=f"reject-{li['id']}"):
                        if not reason.strip():
                            st.error("Give the lister a reason so they can fix the listing.")
                        else:
                            actions.review_listing(li["id"], False, reason, by=acc["email"])
                            session.flash(f"Rejected {li['id']}. The lister sees your reason.")
                            st.rerun()


def flags_page():
    _require_admin()
    from core import actions, market, store
    page_head("Flags", "Listings and accounts our rules think need a look, with the evidence. "
                       "Dismiss a flag if it's fine, or remove the listings.")
    names = _names()
    listings = {li["id"]: li for li in store.load("listings")}
    flags = market.flags(list(listings.values()), store.load("reports"), store.load("flag_actions"), names)
    if not flags:
        empty("No open flags", "Rent far below the area, accounts with many listings, and user reports show up here.")
        return
    acc = session.account()
    for f in flags:
        with st.container(key=f"flag-{f['id'].replace(':', '-')}"):
            ev = "".join(f"<li>{esc(e)}</li>" for e in f["evidence"])
            md(f"<p class='flag-kind'>{esc(f['kind'])}</p><h3 class='card-h'>{esc(f['title'])}</h3>"
               f"<p class='card-p'>Account: {esc(names(f['owner_id']))}.</p><ul class='reasons'>{ev}</ul>")
            with st.container(horizontal=True, gap="small"):
                if st.button("Dismiss", key=f"dismiss-{f['id']}"):
                    actions.act_on_flag(f, "dismissed", by=acc["email"])
                    session.flash("Dismissed the flag.")
                    st.rerun()
                n = len(f["listing_ids"])
                if st.button(f"Remove {'the listing' if n == 1 else f'all {n} listings'}", type="primary",
                             key=f"remove-{f['id']}"):
                    actions.act_on_flag(f, "removed", by=acc["email"])
                    session.flash(f"Removed {', '.join(f['listing_ids'])}. They no longer show in Explore.")
                    st.rerun()
