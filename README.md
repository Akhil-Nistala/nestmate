# Nestmate — Find your flat group before you land.

Working prototype for a live demo. Freshers and interns relocating to Hyderabad
(Deloitte offices in Gachibowli / Madhapur / Hitec City / Kondapur) get matched
into whole **flat groups** of 2–4 verified people whose lifestyles fit.

## Why it's different
| Existing (NoBroker, Roomster, FB groups) | Nestmate |
|---|---|
| Listing boards, unverified strangers | Verified via company / college email domain |
| 1:1 discovery | Whole flat groups (2–4), swipe on groups not people |
| No lifestyle signal | Quiz + free text, K-means personas |
| No explanation | LLM explains why the group works and where friction may come from |
| Fights after move-in | Auto-generated house agreement tailored to friction points |

## Business model (B2B2C)
Companies and colleges offer Nestmate as an **onboarding benefit** for their
joining cohort (per-joiner fee). Employees use it free. Partner orgs get happier,
safer joiners and fewer relocation drop-offs; verification by domain is only
possible because the org is the customer.

## Run
```bash
python -m venv .venv
.venv\Scripts\activate            # Windows  (source .venv/bin/activate on Mac/Linux)
pip install -r requirements.txt
python data/generate.py            # creates data/profiles.csv (200 people, seed 42)
copy .env.example .env             # turns on demo mode; optionally add GEMINI_API_KEY
streamlit run app.py
python -m core.evaluate            # sanity checks + metrics
```
No API key? Everything still works — each LLM feature falls back to a rule-based
template and the UI shows an **AI** or **TEMPLATE** tag. LLM answers are cached in
`data/llm_cache.json`, so repeat clicks are instant and free.

**Before the demo, warm the cache** for the users you'll show:
`python -m core.warm_cache U001 U042` (about 10 calls per user). Live Gemini calls take 3–13 s
and the free tier allows only ~20 requests/day per model, so cached answers make the
demo instant and quota-proof. Model: `gemini-3.5-flash-lite` (set in `.env`).

Reset the demo: delete `data/signups.csv` (new sign-ups' quiz answers) and `data/accounts.json`
(logins; re-created with the seeded HR admin on next start). Seed data is never modified.

## Roles, routes and login
| Who | Routes | Sees |
|---|---|---|
| Logged out | `/` log in · `/signup` | Brand panel, login / sign-up, demo mode |
| Member (fresher) | `/onboarding` until the quiz is done, then `/` matches · `/flat` · `/profile` · `/preferences` | Only their own profile, suggested groups and flat |
| Admin (HR) | `/` overview · `/admin-flats` · `/admin-people` · `/admin-model` | Their own organisation's joiners only: stats, personas, flats, people table; cohort-wide model checks |

Matching runs on the whole partner cohort, so a flat can mix organisations. HR sees
only their own joiners by name; flatmates from other organisations appear as a count.

Routes are built per role with `st.navigation`, so a member has no admin URL to visit
(it falls back to their home page), and every admin page re-checks the role.
Passwords are salted PBKDF2 hashes in `data/accounts.json`. The session survives a
browser refresh via a random session-id cookie.

**Demo mode** (on the login page, only when `NESTMATE_DEMO=1` is set, as in `.env.example`):
one click as the HR admin, or as any synthetic seed member. Real sign-ups can never be
picked, and demo mode is off by default so a shared deployment doesn't allow password-free logins.
Seeded admin login: `hr@deloitte.com` / `nestmate-hr`.

**Light / dark mode**: follows the system setting; the sun/moon button in the top bar switches it.

## How it works
1. **Verify** — email domain must be in the partner list (`core/schema.py`). OTP mocked.
2. **Profile** — 11 ordinal quiz questions + free text. The LLM extracts traits from the text; the user accepts or ignores them.
3. **Personas** — StandardScaler → ×√weight → KMeans for k=3..8, best k by silhouette. Personas auto-named from the 2 most extreme centroid traits. PCA for the 2D map.
4. **Groups** — K-means can't control cluster size, so it only narrows the search. Inside each cluster: pairwise score `100·(1 − weighted normalised distance)`, hard rules (budget overlap, dealbreakers, gender preference) → 0. Greedy build (hardest-to-place first, add best average-scoring compatible person), swap improvement pass (≤200), leftovers placed or marked unmatched with a reason. Deterministic.
5. **Explain & agree** — LLM writes "Why this works / Watch out for" and a house agreement using ONLY the data passed in. Areas are ranked in pure Python from a hardcoded rent/commute table.

All weights live in one dict (`WEIGHTS` in `core/schema.py`); all prompts are constants at the top of `core/llm.py`.

## Structure
```
app.py              router: builds the role's routes, top bar, theme toggle
ui/auth_pages.py    log in, sign up, demo mode
ui/member_pages.py  onboarding quiz, matches, my flat, profile, preferences
ui/admin_pages.py   HR overview, flat groups, people, model checks
ui/components.py    shared HTML building blocks + cached pipeline
ui/theme.py         light/dark design tokens (CSS + charts)
ui/session.py       login session that survives a refresh
assets/style.css    design layer (uses the tokens from ui/theme.py)
.streamlit/config.toml  light + dark themes for Streamlit's own widgets
core/auth.py        accounts, password hashing, roles, demo logins
data/generate.py    synthetic cohort with 5 hidden archetypes
core/schema.py      questions, encodings, weights, dealbreakers
core/encode.py      load/save cohort, profile -> matrix
core/cluster.py     scaling, KMeans, silhouette, PCA, persona names
core/grouping.py    compatibility, group formation, swap pass
core/llm.py         Gemini calls + cache + template fallbacks
core/evaluate.py    ARI vs hidden archetypes, rule checks, determinism, random baseline
```

## Honest limitations
- Synthetic data; weights are reasoned, not learned (next step: learn from post-move-in satisfaction surveys).
- Other members' acceptance is simulated in the demo.
- Rent/commute table is approximate.
