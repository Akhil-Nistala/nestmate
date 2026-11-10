"""
LLM features with a rule-based fallback for EVERY function.

WHY fallbacks: a live demo must never break because of Wi-Fi, quota or a missing
key. Each function returns (result, source) where source is "AI" or "Template",
so the UI can show honestly which one produced the text.

WHY a JSON cache keyed by input hash: repeated demo clicks are instant, cost no
quota, and give the same text every time (reproducible demo).

WHY the LLM only explains and never decides: matching is done by transparent
maths (core/grouping.py). The LLM turns numbers into human language, and is
told to use ONLY the data we pass in, so it can't invent facts.
"""
import hashlib
import json
import os
import re
import warnings

from dotenv import load_dotenv

from core.schema import TRAITS, QUESTIONS, TRAIT_RANGE

load_dotenv()
CACHE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "llm_cache.json")
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")  # pinned: tested fast on our key; -latest aliases timed out
LAST_ERROR = {"msg": None}
TIMEOUT_S = 25  # long enough for a real answer, short enough that the demo falls back quickly

# ---------------------------------------------------------------------------
# PROMPTS (kept together so they can be shown to the panel)
# ---------------------------------------------------------------------------
TRAIT_GUIDE = "\n".join(
    f"- {t}: " + ", ".join(f"{k}={v}" for k, v in q["options"].items()) for t, q in QUESTIONS.items()
)

EXTRACT_TRAITS_PROMPT = """You map a person's description of their ideal flat life to quiz traits.
Traits and allowed integer values:
{guide}

Text: "{text}"

Return ONLY a JSON object. Include every trait the text implies, directly or through a clear
everyday cue (e.g. "I game till late" implies sleep_time=5; "gym at 6am" implies wake_time=1).
Leave out traits the text says nothing about.
Format: {{"trait_name": {{"value": <int>, "reason": "<short quote-based reason>"}}}}"""

EXPLAIN_GROUP_PROMPT = """You explain why a suggested flatmate group works. Use ONLY the data below.
Do not invent facts, names, or habits not present in the data.

Group data (JSON):
{data}

Write in markdown, under 80 words total, exactly these two sections:
**Why this works**
- (bullet 1)
- (bullet 2)
**Watch out for**
- (1-2 bullets naming the specific person and trait from the friction data)"""

HOUSE_AGREEMENT_PROMPT = """Write a short, friendly house agreement for these flatmates. Use ONLY the data below.
Group data (JSON):
{data}

Use markdown with these headings: Quiet hours, Chores rotation, Guests, Kitchen, Bills.
1-2 lines each. Tailor rules to the friction points and members' answers. Max 150 words."""

AREAS_SUMMARY_PROMPT = """In ONE sentence (max 30 words), summarise which area suits this flat group best and why.
Use ONLY this data: {data}"""


# ---------------------------------------------------------------------------
# Gemini call + cache
# ---------------------------------------------------------------------------
_MEM = {"mtime": None, "data": {}}


def _load_cache():
    """Read the JSON cache once and keep it in memory; re-read only if the file
    changed on disk (e.g. warm_cache.py ran while the app was open)."""
    try:
        mtime = os.path.getmtime(CACHE_PATH)
        if mtime != _MEM["mtime"]:
            with open(CACHE_PATH, encoding="utf-8") as f:
                _MEM["data"], _MEM["mtime"] = json.load(f), mtime
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return _MEM["data"]


def _save_cache(cache):
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=1, ensure_ascii=False)
    _MEM["mtime"] = os.path.getmtime(CACHE_PATH)


def _call_llm(prompt):
    """Return model text, or None on any problem (no key, error, timeout)."""
    key_hash = hashlib.sha256((MODEL_NAME + prompt).encode()).hexdigest()
    cache = _load_cache()
    if key_hash in cache:
        return cache[key_hash]

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None
    try:
        # The spec fixes google-generativeai; silence its deprecation notice on import.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            import google.generativeai as genai
        # REST instead of gRPC: more reliable through campus/office firewalls in testing.
        genai.configure(api_key=api_key, transport="rest")
        model = genai.GenerativeModel(MODEL_NAME)
        resp = model.generate_content(prompt, request_options={"timeout": TIMEOUT_S, "retry": None})
        # WHY retry=None: the client's own retries can turn a 25s timeout into 50s+.
        # On failure we fall back to the template instantly instead.
        text = (resp.text or "").strip()
        if not text:
            LAST_ERROR["msg"] = "empty response"
            return None
    except Exception as e:
        # Kept so the warm-up script (and we) can see WHY a template was used.
        LAST_ERROR["msg"] = f"{type(e).__name__}: {str(e)[:120]}"
        return None
    LAST_ERROR["msg"] = None
    cache[key_hash] = text
    _save_cache(cache)
    return text


def llm_available():
    return bool(os.getenv("GEMINI_API_KEY"))


def _json_from(text):
    m = re.search(r"\{.*\}", text or "", re.S)
    return json.loads(m.group(0)) if m else None


def _group_payload(g):
    """Only the facts the LLM is allowed to use."""
    return json.dumps({
        "score": g["score"],
        "persona": g["persona"],
        "shared_budget_per_person": list(g["budget"]),
        "offices": g["offices"],
        "members": [{
            "name": m["name"].split()[0],
            **{t: QUESTIONS[t]["options"][int(m[t])] for t in TRAITS},
        } for m in g["members"]],
        "matching_traits": g["matching"],
        "friction_traits": g["friction"],
    }, ensure_ascii=False)


# ---------------------------------------------------------------------------
# 1. Trait extraction from free text
# ---------------------------------------------------------------------------
# (regex, trait, value, reason). Order matters: more specific patterns first.
KEYWORD_RULES = [
    (r"non[- ]?veg|chicken|biryani|meat|fish", "food", 3, "mentions non-veg food"),
    (r"\bveg(etarian)?\b|veg kitchen", "food", 1, "mentions vegetarian food"),
    (r"night owl|till late|after midnight|up late|late night|game till", "sleep_time", 5, "describes staying up late"),
    (r"sleep early|early nights|early to bed", "sleep_time", 1, "describes sleeping early"),
    (r"5 ?am|6 ?am|morning person|gym before|early morning|up early", "wake_time", 1, "describes waking early"),
    (r"tidy|neat|clean flat|clean home|organi[sz]ed", "cleanliness", 5, "values a tidy home"),
    (r"messy|relaxed about clean", "cleanliness", 2, "relaxed about cleaning"),
    (r"quiet|silence|peaceful|calm|focus", "noise_tolerance", 1, "wants a quiet home"),
    (r"part(y|ies)|music|friends over|having guests|love having", "guests_frequency", 4, "likes having people over"),
    (r"rarely have guests|guests only occasionally|no guests", "guests_frequency", 2, "rarely has guests"),
    (r"cook my|home[- ]cooked|cook daily|healthy home cooking", "cooking", 3, "cooks at home"),
    (r"swiggy|zomato|order (in|food)|mostly order", "cooking", 1, "orders food"),
    (r"work from home|wfh|remote", "work_mode", 3, "works from home"),
    (r"don'?t smoke|no smoking|non[- ]smoker", "smoking", 1, "doesn't smoke"),
    (r"don'?t (smoke or )?drink|teetotal|no alcohol", "drinking", 1, "doesn't drink"),
    (r"\bdrinks?\b|beer|wine", "drinking", 3, "mentions drinking"),
    (r"very social|love hanging out|extrovert|social", "social_level", 5, "describes being social"),
    (r"homebody|introvert|keep to myself|private", "social_level", 1, "describes being private"),
]


def _rule_extract(text):
    out = {}
    low = (text or "").lower()
    for pattern, trait, value, reason in KEYWORD_RULES:
        if trait not in out and re.search(pattern, low):
            out[trait] = {"value": value, "reason": reason}
    return out


def _valid_traits(d):
    clean = {}
    for t, v in (d or {}).items():
        if t in TRAITS and isinstance(v, dict):
            try:
                val = int(v.get("value"))
            except (TypeError, ValueError):
                continue
            lo, hi = TRAIT_RANGE[t]
            if lo <= val <= hi:
                clean[t] = {"value": val, "reason": str(v.get("reason", ""))[:120]}
    return clean


def extract_traits(free_text):
    if not (free_text or "").strip():
        return {}, "Template"
    raw = _call_llm(EXTRACT_TRAITS_PROMPT.format(guide=TRAIT_GUIDE, text=free_text.replace('"', "'")))
    if raw:
        try:
            parsed = _valid_traits(_json_from(raw))
            if parsed:
                return parsed, "AI"
        except (json.JSONDecodeError, AttributeError):
            pass
    return _rule_extract(free_text), "Template"


# ---------------------------------------------------------------------------
# 2. Group explanation
# ---------------------------------------------------------------------------
def explain_group(g):
    text = _call_llm(EXPLAIN_GROUP_PROMPT.format(data=_group_payload(g)))
    if text:
        return text, "AI"
    lo, hi = g["budget"]
    m = g["matching"]
    why = [f"Aligned on **{m[0]['trait']}** ({m[0]['detail']})" + (f" and **{m[1]['trait']}**." if len(m) > 1 else "."),
           f"Compatibility {g['score']:.0f}/100, shared budget ₹{lo:,}–₹{hi:,}, no dealbreakers violated."]
    watch = [f"**{f['trait'].capitalize()}** — {f['detail']}." for f in g["friction"]] or ["No major differences found."]
    return "**Why this works**\n" + "\n".join(f"- {w}" for w in why) + \
        "\n\n**Watch out for**\n" + "\n".join(f"- {w}" for w in watch), "Template"


# ---------------------------------------------------------------------------
# 3. House agreement
# ---------------------------------------------------------------------------
SLEEP_TO_QUIET = {1: "9:30pm", 2: "10:30pm", 3: "11pm", 4: "12am", 5: "1am"}


def house_agreement(g):
    text = _call_llm(HOUSE_AGREEMENT_PROMPT.format(data=_group_payload(g)))
    if text:
        return text, "AI"
    mem = g["members"]
    names = [m["name"].split()[0] for m in mem]
    earliest = min(m["sleep_time"] for m in mem)
    max_guests = max(m["guests_frequency"] for m in mem)
    any_veg_only = any(m["food"] == 1 for m in mem)
    any_nonveg = any(m["food"] == 3 for m in mem)
    friction = {f["trait"] for f in g["friction"]}

    quiet = f"Quiet from **{SLEEP_TO_QUIET[earliest]}** to 7am (set by the earliest sleeper)."
    if "sleep time" in friction:
        quiet += " Late-nighters use headphones after quiet hours."
    chores = "Weekly rotation: " + " → ".join(names) + " (kitchen, bathroom, trash, common area)."
    if "cleanliness" in friction:
        chores += " Dishes washed same day; 15-min Sunday reset together."
    if max_guests >= 4:
        guests = "Guests welcome; overnight guests max 2 nights/week with a heads-up in the group chat."
    else:
        guests = "Guests by heads-up in the group chat; overnight stays agreed in advance."
    if any_veg_only and any_nonveg:
        kitchen = "Separate shelves and utensils for veg and non-veg; non-veg cooking only on agreed days."
    elif any_veg_only:
        kitchen = "Vegetarian kitchen."
    else:
        kitchen = "Shared kitchen; clean up right after cooking."
    bills = f"Rent split equally (within ₹{g['budget'][0]:,}–₹{g['budget'][1]:,} each); utilities split equally via a shared expense app, settled monthly."
    return "\n\n".join([
        f"**Quiet hours** — {quiet}", f"**Chores rotation** — {chores}", f"**Guests** — {guests}",
        f"**Kitchen** — {kitchen}", f"**Bills** — {bills}",
    ]), "Template"


# ---------------------------------------------------------------------------
# 4. Area suggestions (pure Python; LLM only writes a one-line summary)
# ---------------------------------------------------------------------------
# Approximate rent per person (shared 2-3BHK) and commute minutes to each office.
AREAS = [
    {"area": "Gachibowli",      "rent": 14000, "commute": {"Gachibowli": 10, "Madhapur": 25, "Kondapur": 20, "Hitec City": 20}},
    {"area": "Madhapur",        "rent": 15000, "commute": {"Gachibowli": 25, "Madhapur": 10, "Kondapur": 15, "Hitec City": 10}},
    {"area": "Kondapur",        "rent": 12000, "commute": {"Gachibowli": 20, "Madhapur": 15, "Kondapur": 10, "Hitec City": 15}},
    {"area": "Kothaguda",       "rent": 11000, "commute": {"Gachibowli": 15, "Madhapur": 15, "Kondapur": 10, "Hitec City": 15}},
    {"area": "Nanakramguda",    "rent": 13000, "commute": {"Gachibowli": 10, "Madhapur": 30, "Kondapur": 25, "Hitec City": 25}},
    {"area": "Manikonda",       "rent": 9000,  "commute": {"Gachibowli": 20, "Madhapur": 35, "Kondapur": 30, "Hitec City": 30}},
    {"area": "Serilingampally", "rent": 8500,  "commute": {"Gachibowli": 20, "Madhapur": 30, "Kondapur": 20, "Hitec City": 25}},
    {"area": "Miyapur",         "rent": 7500,  "commute": {"Gachibowli": 35, "Madhapur": 35, "Kondapur": 25, "Hitec City": 30}},
]


def suggest_areas(g):
    lo, hi = g["budget"]
    offices = [m["office_location"] for m in g["members"]]
    scored = []
    for a in AREAS:
        avg = sum(a["commute"][o] for o in offices) / len(offices)
        fits = a["rent"] <= hi
        # Rank: in-budget first, then shortest average commute, then cheaper.
        scored.append({"area": a["area"], "rent": a["rent"], "avg_commute": round(avg), "fits_budget": fits})
    scored.sort(key=lambda s: (not s["fits_budget"], s["avg_commute"], s["rent"]))
    top = scored[:3]
    text = _call_llm(AREAS_SUMMARY_PROMPT.format(data=json.dumps({"areas": top, "budget": [lo, hi], "offices": offices})))
    if text:
        return top, text, "AI"
    b = top[0]
    summary = (f"{b['area']} fits best: ~₹{b['rent']:,}/person, ~{b['avg_commute']} min average commute"
               + ("." if b["fits_budget"] else " (slightly above your shared budget)."))
    return top, summary, "Template"
