# Nestmate: find flatmates you'll actually get on with

Working prototype for a live demo. People joining a company or college in a new
city find a flat, flatmates, or both: whole **flat groups** of 2–4 verified people whose lifestyles
fit, and flats or rooms to go with them. People with a flat or a spare room can
list it, pick applicants by fit, and collect rent.

Nothing is tied to one city or company: partner email domains, offices and areas
are data in `core/schema.py`. The sample data is a Hyderabad joining cohort.

## Why it's different
| Existing (NoBroker, Roomster, FB groups) | Nestmate |
|---|---|
| Listing boards, unverified strangers | Verified via company or college email domain |
| 1:1 discovery | Accept or pass one person at a time; each new suggestion fits everyone already in your group. Or take a ready-made group |
| No lifestyle signal | Four-step quiz, "matters a lot" marks, dealbreakers, free text, k-means personas |
| No explanation | Habit grid shows where a group is the same, close or different; the LLM explains why it works |
| Rooms in occupied flats are a gamble | "You'd live with Rahul": fit with the people already living there |
| Fights after move-in | House agreement tailored to the group's friction points, rent and shared bills in one place |
| Scams | Listings are reviewed before they go live; rule-based flags with evidence |

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
streamlit run app.py --server.address 127.0.0.1
python -m core.evaluate            # sanity checks + metrics
```
WHY `--server.address 127.0.0.1` on Windows: in testing, Streamlit's server bound to
all addresses stopped accepting connections after a Windows socket error
(`WinError 64`); bound to loopback it stayed up. Use the plain command if you need
other devices on the network to reach it.

The marketplace data (listings, groups, applications, tenancies, payments, bills)
is created automatically on first start by `data/seed_market.py`.

No API key? Everything still works: each LLM feature falls back to a rule-based
template, and the UI says "Written by AI" or "From a template" next to the text.
LLM answers are cached in `data/llm_cache.json`, so repeat clicks are instant and free.

**Before the demo, warm the cache** for the users you'll show:
`python -m core.warm_cache U001 U042 U102` (about 10 calls per user; U102 also warms
Arjun's invite group and its house agreement). Live Gemini calls take 3–13 s and the
free tier allows only ~20 requests/day per model, so cached answers make the demo
instant and quota-proof. Model: `gemini-3.5-flash-lite` (set in `.env`). U001 is fully
cached today; U042 and U102 are not yet.

## Resetting the demo
| To reset | Do this |
|---|---|
| Marketplace (listings, groups, applications, tenancies, payments, bills, reports, flags) | `python data/seed_market.py` (rewrites every marketplace file; or delete them and restart) |
| New sign-ups' quiz answers | delete `data/signups.csv` |
| Logins | delete `data/accounts.json` (the seeded HR admin is re-created on next start while demo mode is on) |

Seed profiles (`data/profiles.csv`) and the LLM cache are never modified by a reset.

## Demo accounts (login page, demo mode only)
| Button | Account | Story |
|---|---|---|
| Looking for a flat and flatmates | Arjun Gupta (U102), quiz done | Explore, open Mr. Rao's flat in Gachibowli, invite Vamsi (91% fit), apply as a group. After Mr. Rao accepts: pay rent in the mock checkout, add a shared bill. Rahul's spare room shows "You'd live with Rahul". |
| Renting out a flat | Mr. Rao (O001), landlord, no quiz | My listings: a 3BHK let as rooms, one group application already waiting. Book a visit, accept Arjun's group, see the house agreement and rent collection. |
| Tenant with a spare room | Rahul Patel (U167) | Listed his spare room in Madhapur; his landlord isn't on the app, so rent goes to the landlord's UPI ID. |
| Admin | Priya Nair (HR), hr@deloitte.com / nestmate-hr | Cohort overview, flat groups, people, listings to review (approve L008), flags (a listing 50% below the area average, an account with three listings, a user report), model checks. |

"Any member of the synthetic cohort" signs in as any seed profile. Demo mode needs
`NESTMATE_DEMO=1` (set in `.env.example`); without it there are no password-free
logins, and the seeded HR account doesn't exist or accept logins. Real sign-ups can
never be picked.

## Roles and routes
Two roles. Members never pick "seeker" or "owner": what they do is chosen on Home,
and one account can search and list.

| Who | Route | What it is |
|---|---|---|
| Logged out | `/login`, `/signup` | Log in, sign up, demo accounts |
| Member | `/home` | Four options (find a flat, find flatmates, both, list a space) and "continue where you left off" |
| | `/explore` | Flats with people from your batch, flats and rooms (filters), flatmates, or flats for your group; each with a fit score |
| | `/matches` (Flatmates) | Accept or pass one person at a time (each joins your group), or ready-made groups |
| | `/group` (My group) | Members, combined budget, shortlisted flats, apply as a group, house agreement once housed |
| | `/listings` (My listings) | List a space; your listings and their applicants, best fit first; book visits; accept |
| | `/rent` | Your share, who has paid, mock checkout, shared bills; or rent collection as a lister |
| | `/profile`, `/answers` | Profile and AI-read traits; the quiz in edit mode (from the account menu) |
| | `/onboarding` | The quiz, shown until it's done (people who only list a space start on Home) |
| Admin | `/admin`, `/admin-flats`, `/admin-people` | Their own organisation's joiners only |
| | `/admin-listings`, `/admin-flags` | Review new listings; rule-based flags with Dismiss / Remove (platform-wide) |
| | `/admin-model` | Cohort-wide model checks |

The top bar hides member pages that are empty for this person (My group, My listings,
Rent). Routes are built per role with `st.navigation`, so a member has no admin URL
to visit, and every admin page re-checks the role. Matching runs on the whole partner
cohort, so a flat can mix organisations; HR sees only their own joiners by name.
Passwords are salted PBKDF2 hashes in `data/accounts.json`; the session survives a
refresh via a random session-id cookie.

**Light / dark mode** follows the system setting; the sun/moon button switches it.

## What's simulated
- **Other members accepting** a group or an invite: marked accepted straight away, and labelled.
- **Signing** the house agreement: a Sign button per member, no e-signature.
- **Payments**: the checkout says "Demo payment, no money moves" and issues a receipt number.
- **Email verification** by one-time code: the partner-domain check stands in for it.

## How it works
1. **Verify**: email domain must be in the partner list (`core/schema.py`).
2. **Profile**: 11 ordinal questions in four steps, no pre-selected answers. Each can be
   marked "matters a lot" (up to 5), and food, smoking, drinking and noise offer a
   specific dealbreaker (up to 3). Contradictions ("I smoke" + "no smokers") are blocked.
   The LLM reads the free text; the user accepts or ignores what it found.
3. **Personas**: StandardScaler, then ×√weight, then KMeans for k=3..8, best k by
   silhouette. Named from the 2 most extreme centroid traits. PCA for the 2D map.
4. **Groups**: pair score `100·(1 − weighted normalised distance)`; hard rules (budget
   overlap, dealbreakers, gender preference) make it 0. "Matters a lot" multiplies a
   trait's weight by `1 + PRIORITY_BOOST × share of the pair who marked it` (seed
   profiles have none, so their scores are unchanged). Greedy build inside each
   cluster, swap pass, leftovers fill open spots or pair up across personas. Deterministic.
5. **Marketplace** (`core/market.py`, reusing the same pair and group scores):
   seeker vs the people living in a room; house rules as hard filters; rent and
   commute fit for empty flats; group vs flat (enough free rooms, rent inside the
   shared budget); applicants ranked by fit with reasons and one clash.
6. **Explain and agree**: the LLM writes "Why this works / Watch out for" and the
   house agreement using only the data passed in.
7. **Flags**: rent more than 40% below the area average; one account with more than
   2 active listings in different flats; user reports. Each shows its evidence.

All weights live in `WEIGHTS` in `core/schema.py`; all prompts are constants at the
top of `core/llm.py`. The quiz's on-screen wording lives in `QUESTION_UI`, separate
from `QUESTIONS`, whose option text goes into LLM prompts and the cache keys.

## Data files
| File | What | Tracked in git |
|---|---|---|
| `data/profiles.csv` | 200 synthetic cohort profiles | yes |
| `data/llm_cache.json` | cached LLM answers, keyed by model + prompt | yes |
| `data/signups.csv`, `data/accounts.json` | new sign-ups, logins | no |
| `data/listings.json`, `groups.json`, `applications.json`, `tenancies.json`, `payments.json`, `expenses.json`, `people.json`, `reports.json`, `flag_actions.json`, `member_state.json` | marketplace, created by `data/seed_market.py` | no |

## Structure
```
app.py                router: builds the role's routes, top bar, theme toggle
ui/auth_pages.py      log in, sign up, demo accounts
ui/member_pages.py    home, flatmates (one at a time or groups), profile, onboarding and "Your answers"
ui/quiz.py            the four-step lifestyle quiz
ui/market_pages.py    explore, my group, my listings, rent
ui/admin_pages.py     HR overview, flat groups, people, listings to review, flags, model checks
ui/components.py      fit key tag, habit grid, stat strip and other building blocks
ui/theme.py           light/dark design tokens (CSS + charts)
ui/session.py         login session that survives a refresh, flash messages
assets/style.css      design layer (uses the tokens from ui/theme.py)
.streamlit/config.toml  light + dark themes for Streamlit's own widgets
core/auth.py          accounts, password hashing, roles, demo accounts
core/schema.py        questions, screen wording, weights, dealbreakers, areas, listing options
core/encode.py        load/save cohort, profile -> matrix
core/cluster.py       scaling, KMeans, silhouette, PCA, persona names
core/grouping.py      compatibility (with priorities), group formation, swap pass
core/market.py        marketplace fit scores, house rules, flags, bill settlement (pure)
core/actions.py       marketplace state changes (groups, applications, tenancies, rent)
core/store.py         JSON-file storage with atomic writes
core/llm.py           Gemini calls + cache + template fallbacks
core/evaluate.py      ARI vs hidden archetypes, rule checks, determinism, rule-respecting random baseline
data/generate.py      synthetic cohort with 5 hidden archetypes
data/seed_market.py   deterministic demo marketplace
```

## Honest limitations
- Synthetic data; weights are reasoned, not learned (next step: learn from post-move-in satisfaction surveys).
- Acceptance, signing and payments are simulated (see above).
- Rent and commute table is approximate.
- File storage suits one demo machine, not many concurrent users.
