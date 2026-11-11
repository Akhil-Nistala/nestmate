"""
Single source of truth for the quiz: questions, answer labels, numeric encodings,
trait weights and dealbreaker rules.

WHY one file: every other module (encoding, clustering, grouping, LLM prompts, UI)
reads from here, so changing a question or a weight is a one-line edit and the
whole app stays consistent. That matters when a panel asks "what if sleep mattered
less?" -- we can change one number live.
"""

# ---------------------------------------------------------------------------
# Quiz questions. Each answer is stored as an ordinal integer (1..N).
# WHY ordinal: these answers have a natural order (10pm is "closer" to 11pm than
# to 2am), so distances between numbers are meaningful for K-means and scoring.
# ---------------------------------------------------------------------------
QUESTIONS = {
    "sleep_time": {
        "label": "When do you usually sleep?",
        "options": {1: "Before 10pm", 2: "10-11pm", 3: "11pm-12am", 4: "12-1am", 5: "After 1am"},
    },
    "wake_time": {
        "label": "When do you usually wake up?",
        "options": {1: "Before 6am", 2: "6-7am", 3: "7-8am", 4: "8-9am", 5: "After 9am"},
    },
    "cleanliness": {
        "label": "How tidy do you keep shared spaces?",
        "options": {1: "Very relaxed", 2: "Relaxed", 3: "Average", 4: "Neat", 5: "Very neat"},
    },
    "noise_tolerance": {
        "label": "How much noise at home is okay?",
        "options": {1: "Need silence", 2: "Mostly quiet", 3: "Some is fine", 4: "Lively is fine", 5: "Don't mind noise"},
    },
    "guests_frequency": {
        "label": "How often do you have guests over?",
        "options": {1: "Never", 2: "Rarely", 3: "Monthly", 4: "Weekly", 5: "Often"},
    },
    "food": {
        "label": "Kitchen food preference",
        "options": {1: "Veg-only kitchen", 2: "Veg, ok with non-veg", 3: "Non-veg"},
    },
    "cooking": {
        "label": "How often do you cook?",
        "options": {1: "Always order", 2: "Sometimes", 3: "Cook daily"},
    },
    "smoking": {
        "label": "Smoking",
        "options": {1: "No, can't tolerate it", 2: "No, but okay with it", 3: "Yes"},
    },
    "drinking": {
        "label": "Drinking",
        "options": {1: "No, can't tolerate it", 2: "No, but okay with it", 3: "Occasionally", 4: "Often"},
    },
    "work_mode": {
        "label": "Work mode",
        "options": {1: "Full office", 2: "Hybrid", 3: "Mostly WFH"},
    },
    "social_level": {
        "label": "How social are you at home?",
        "options": {1: "Keep to myself", 2: "Fairly private", 3: "Balanced", 4: "Social", 5: "Very social"},
    },
}

TRAITS = list(QUESTIONS.keys())

# Min/max of each trait, used to normalise differences to 0..1 in pair scoring.
TRAIT_RANGE = {t: (min(q["options"]), max(q["options"])) for t, q in QUESTIONS.items()}

# Short human names used in charts, chips and LLM prompts.
TRAIT_SHORT = {
    "sleep_time": "sleep time", "wake_time": "wake time", "cleanliness": "cleanliness",
    "noise_tolerance": "noise tolerance", "guests_frequency": "guests", "food": "food",
    "cooking": "cooking", "smoking": "smoking", "drinking": "drinking",
    "work_mode": "work mode", "social_level": "social level",
}

# ---------------------------------------------------------------------------
# Trait weights: higher = more likely to cause day-to-day conflict.
# WHY these numbers (tunable in ONE place):
#  - sleep_time & cleanliness (3): the two most-cited flatmate fights; they hit
#    every single day and can't be negotiated away easily.
#  - guests_frequency (2.5): affects privacy and safety of everyone in the flat.
#  - noise_tolerance, smoking, food (2): strong shared-space impact (smell,
#    kitchen use, focus), but often manageable with rules.
#  - drinking, wake_time (1.5): matter, but less daily friction than sleep.
#  - work_mode, cooking, social_level (1): mostly personal; differences can even
#    be complementary (e.g. one cooks, one orders).
# Hard "no" cases (e.g. can't tolerate smoking) are handled as DEALBREAKERS, not
# weights, because no amount of similarity elsewhere should override them.
# ---------------------------------------------------------------------------
WEIGHTS = {
    "sleep_time": 3.0,
    "cleanliness": 3.0,
    "guests_frequency": 2.5,
    "noise_tolerance": 2.0,
    "smoking": 2.0,
    "food": 2.0,
    "drinking": 1.5,
    "wake_time": 1.5,
    "work_mode": 1.0,
    "cooking": 1.0,
    "social_level": 1.0,
}

# ---------------------------------------------------------------------------
# Dealbreakers = hard filters. A dealbreaker belongs to the person who sets it,
# and is checked against the OTHER person's answers.
# ---------------------------------------------------------------------------
DEALBREAKERS = {
    "no_smokers": "No smokers",
    "veg_kitchen": "Veg-only kitchen",
    "no_drinking": "No drinking at home",
    "quiet_home": "Quiet home (no noise / frequent guests)",
    "same_gender": "Same-gender flat only",
}


def violates_dealbreaker(key, me, other):
    """True if `other` violates dealbreaker `key` that `me` has set.
    `me` / `other` are dict-like profiles."""
    if key == "no_smokers":
        return other["smoking"] == 3
    if key == "veg_kitchen":
        return other["food"] == 3
    if key == "no_drinking":
        return other["drinking"] >= 3
    if key == "quiet_home":
        return other["noise_tolerance"] >= 4 or other["guests_frequency"] >= 4
    if key == "same_gender":
        return me["gender"] != other["gender"]
    return False


# ---------------------------------------------------------------------------
# Other profile fields
# ---------------------------------------------------------------------------
OFFICES = ["Gachibowli", "Madhapur", "Kondapur", "Hitec City"]
JOINING_MONTHS = ["Jun 2027", "Jul 2027", "Aug 2027"]
GENDERS = ["Female", "Male", "Non-binary"]
GENDER_MIX = ["same only", "any"]
FLAT_SIZES = [2, 3, 4]
BUDGET_MIN, BUDGET_MAX = 6000, 25000

# WHY a domain allow-list: verification by work/college email is our trust layer.
# In production this is the list of partner companies/colleges (B2B2C model).
ALLOWED_DOMAINS = {
    "deloitte.com": "Deloitte",
    "iith.ac.in": "IIT Hyderabad",
    "iiit.ac.in": "IIIT Hyderabad",
    "bits-pilani.ac.in": "BITS Pilani",
    "infosys.com": "Infosys",
    "tcs.com": "TCS",
}


def email_domain(email):
    return email.strip().lower().split("@")[-1] if "@" in email else ""


def is_allowed_email(email):
    return email_domain(email) in ALLOWED_DOMAINS


# ---------------------------------------------------------------------------
# Quiz as shown on screen.
#
# WHY a separate dict instead of editing QUESTIONS: QUESTIONS[...]["options"]
# text goes into LLM prompts, and data/llm_cache.json is keyed on prompt text.
# Changing a single word there silently empties the warmed cache. Screen
# wording lives here and is used by the UI only.
#   ask      - the question as shown
#   choices  - short button labels, same integer keys as QUESTIONS options
#   hint     - optional one-line help
#   widget   - "scale" (ordered: segmented control) or "pick" (categorical: pills)
#   dealbreaker - the DEALBREAKERS key offered under this question, with its wording
# ---------------------------------------------------------------------------
QUESTION_UI = {
    "sleep_time": {"ask": "When do you usually go to sleep?", "widget": "scale",
                   "choices": {1: "Before 10pm", 2: "10–11pm", 3: "11pm–12am", 4: "12–1am", 5: "After 1am"}},
    "wake_time": {"ask": "When do you usually wake up?", "widget": "scale",
                  "choices": {1: "Before 6am", 2: "6–7am", 3: "7–8am", 4: "8–9am", 5: "After 9am"}},
    "work_mode": {"ask": "Where do you work most days?", "widget": "scale",
                  "choices": {1: "At the office", 2: "Hybrid", 3: "Mostly from home"},
                  "hint": "Someone home all day changes how quiet the daytime needs to be."},
    "cleanliness": {"ask": "How tidy do you keep shared spaces?", "widget": "scale",
                    "choices": {1: "Very relaxed", 2: "Relaxed", 3: "Average", 4: "Neat", 5: "Very neat"},
                    "hint": "Think dishes in the sink, the shared fridge, the bathroom."},
    "noise_tolerance": {"ask": "How much noise at home is fine with you?", "widget": "scale",
                        "choices": {1: "I need silence", 2: "Mostly quiet", 3: "Some is fine", 4: "Lively is fine",
                                    5: "I don't mind noise"},
                        "dealbreaker": ("quiet_home", "Dealbreaker: a quiet home, no loud flatmates or frequent guests")},
    "guests_frequency": {"ask": "How often do you have friends over?", "widget": "scale",
                         "choices": {1: "Never", 2: "Rarely", 3: "Monthly", 4: "Weekly", 5: "Often"},
                         "hint": "Overnight guests count too."},
    "social_level": {"ask": "How much do you want to hang out with flatmates?", "widget": "scale",
                     "choices": {1: "Keep to myself", 2: "Fairly private", 3: "Balanced", 4: "Social", 5: "Very social"}},
    "food": {"ask": "What should the kitchen be?", "widget": "pick",
             "choices": {1: "Veg only", 2: "Veg, and non-veg is fine", 3: "I cook or eat non-veg"},
             "dealbreaker": ("veg_kitchen", "Dealbreaker: veg-only kitchen")},
    "cooking": {"ask": "How often do you cook?", "widget": "scale",
                "choices": {1: "I always order in", 2: "Sometimes", 3: "Every day"}},
    "smoking": {"ask": "Do you smoke?", "widget": "pick",
                "choices": {1: "No, and I can't be around it", 2: "No, but I don't mind it", 3: "Yes"},
                "dealbreaker": ("no_smokers", "Dealbreaker: no smokers")},
    "drinking": {"ask": "Do you drink?", "widget": "pick",
                 "choices": {1: "No, and I can't be around it", 2: "No, but I don't mind it", 3: "Occasionally",
                             4: "Often"},
                 "dealbreaker": ("no_drinking", "Dealbreaker: no drinking at home")},
}

# Four short steps instead of one long screen. "The flat" step has its own
# fields (budget, flat size, who you share with, free text), not quiz traits.
QUIZ_STEPS = [
    {"key": "day", "title": "Your day", "traits": ["sleep_time", "wake_time", "work_mode"]},
    {"key": "shared", "title": "Shared spaces",
     "traits": ["cleanliness", "noise_tolerance", "guests_frequency", "social_level"]},
    {"key": "kitchen", "title": "Kitchen and habits", "traits": ["food", "cooking", "smoking", "drinking"]},
    {"key": "flat", "title": "The flat", "traits": []},
]
assert sorted(t for s in QUIZ_STEPS for t in s["traits"]) == sorted(TRAITS)

GENDER_MIX_UI = {"same only": "Same gender only", "any": "Any gender"}

# "Matters a lot to me": a pair who both mark a trait weigh it twice as much
# (weight x (1 + PRIORITY_BOOST x share of the pair who marked it)). With no
# priorities (every seed profile) scores are exactly what they were before.
PRIORITY_BOOST = 1.0
MAX_PRIORITIES = 5
MAX_DEALBREAKERS = 3


def self_contradictions(answers, dealbreakers):
    """Dealbreakers the person would break themselves (e.g. smokes + 'no smokers').
    Reuses violates_dealbreaker with the person on both sides."""
    out = []
    for d in dealbreakers:
        needed = {"no_smokers": ["smoking"], "veg_kitchen": ["food"], "no_drinking": ["drinking"],
                  "quiet_home": ["noise_tolerance", "guests_frequency"]}.get(d, [])
        if needed and all(answers.get(t) is not None for t in needed):
            me = {**answers, "gender": None}
            if violates_dealbreaker(d, me, me):
                out.append(d)
    return out


# ---------------------------------------------------------------------------
# Hyderabad areas: approximate rent per person (shared 2-3BHK) and commute
# minutes to each office. Used by area suggestions, listings and the scam check.
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# Listings
# ---------------------------------------------------------------------------
LISTING_KINDS = {"whole_flat": "A whole flat", "room": "Rooms in a flat"}
LISTER_TYPES = {"owner_away": "I own it and don't live there",
                "owner_lives_here": "I own it and live there",
                "tenant_spare_room": "I rent it and have a spare room"}
LISTING_GENDER = {"any": "Anyone", "male": "Men only", "female": "Women only"}
SCAM_DISCOUNT = 0.40       # flag rent more than 40% below the area average
MIN_SHOWN_FIT = 50         # interested people below this fit aren't shown (weak matches add noise)
MAX_ACTIVE_LISTINGS = 2    # flag an account with more listings than this, in different flats
# Fixed visit slots (deterministic: no clock at render time).
VISIT_SLOTS = ["Sat 12 Jun, 11:00", "Sat 12 Jun, 17:00", "Sun 13 Jun, 11:00", "Sun 13 Jun, 17:00",
               "Sat 19 Jun, 11:00", "Sun 20 Jun, 11:00"]
