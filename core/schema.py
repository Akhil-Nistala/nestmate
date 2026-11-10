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
