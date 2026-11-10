"""
Generate 200 synthetic profiles for the demo cohort.

WHY archetypes instead of random answers: real people's habits are correlated
(night owls tend to be social, early risers tend to be neat). Purely random
answers would give K-means nothing to find and make the demo meaningless.
We hide 5 archetypes, add +/-1 noise so they overlap realistically, and keep
the true archetype in a hidden column ONLY to measure how well clustering
recovers it (adjusted Rand index in core/evaluate.py). It is never a model input.

Run:  python data/generate.py
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.schema import TRAITS, TRAIT_RANGE, OFFICES, JOINING_MONTHS, ALLOWED_DOMAINS  # noqa: E402

SEED = 42
N = 200
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "profiles.csv")

# Archetype centres, in TRAITS order:
# sleep, wake, clean, noise, guests, food, cooking, smoking, drinking, work, social
ARCHETYPES = {
    "Early-bird Homebody": [1, 2, 5, 1, 1, 1, 3, 1, 1, 2, 1],
    "Night-owl Social":    [5, 5, 2, 5, 5, 3, 1, 2, 4, 2, 5],
    "WFH Focused":         [3, 4, 4, 1, 2, 2, 2, 1, 2, 3, 2],
    "Fitness Early Riser": [2, 1, 4, 3, 3, 3, 3, 1, 1, 1, 4],
    "Easygoing Middle":    [3, 3, 3, 3, 3, 2, 2, 2, 3, 2, 3],
}

# Dealbreakers that make sense for each archetype (so they are believable).
ARCHETYPE_DEALBREAKERS = {
    "Early-bird Homebody": ["veg_kitchen", "quiet_home", "no_smokers", "same_gender"],
    "Night-owl Social":    ["same_gender"],
    "WFH Focused":         ["quiet_home", "no_smokers"],
    "Fitness Early Riser": ["no_smokers", "no_drinking"],
    "Easygoing Middle":    ["no_smokers", "same_gender"],
}

FREE_TEXT = {
    "Early-bird Homebody": [
        "I sleep early and like a calm, clean home.",
        "Prefer a peaceful vegetarian kitchen and early nights.",
        "I'm a homebody, I keep things tidy and rarely have guests over.",
        "Quiet evenings, home-cooked veg food and a neat flat is my ideal.",
    ],
    "Night-owl Social": [
        "I'm a night owl, I game till late and love having friends over.",
        "Weekends are for parties and music, I'm pretty relaxed about cleaning.",
        "Very social, usually up after midnight, I mostly order from Swiggy.",
        "Love hanging out, having guests and the occasional drink at home.",
    ],
    "WFH Focused": [
        "I mostly work from home so I need a quiet place to focus.",
        "Remote work means calls all day; I value silence and a tidy space.",
        "I work from home and like a calm flat, guests only occasionally.",
    ],
    "Fitness Early Riser": [
        "Up at 5am for the gym, I cook my own meals and don't smoke or drink.",
        "Early morning runs, healthy home cooking and a clean flat.",
        "I'm a morning person, I hit the gym before office and keep things neat.",
    ],
    "Easygoing Middle": [
        "I'm pretty easygoing, happy with most routines.",
        "Flexible about most things, just want friendly flatmates.",
        "Balanced lifestyle, sometimes cook, sometimes order, go with the flow.",
    ],
}

FIRST_F = ["Aanya", "Priya", "Sneha", "Ananya", "Kavya", "Diya", "Ishita", "Meera", "Riya", "Pooja",
           "Lakshmi", "Divya", "Shreya", "Nikita", "Aishwarya", "Sanjana", "Harini", "Tanvi", "Nandini", "Swathi"]
FIRST_M = ["Rahul", "Arjun", "Rohan", "Karthik", "Aditya", "Vikram", "Siddharth", "Aman", "Nikhil", "Varun",
           "Sai", "Pranav", "Harsha", "Manish", "Akash", "Rohit", "Vamsi", "Abhishek", "Tejas", "Kunal"]
FIRST_NB = ["Arin", "Kiran", "Sam"]
LAST = ["Sharma", "Reddy", "Iyer", "Nair", "Patel", "Gupta", "Rao", "Menon", "Singh", "Kulkarni",
        "Joshi", "Das", "Verma", "Chowdary", "Pillai", "Bose", "Mehta", "Naidu", "Kapoor", "Bhat"]

# Deloitte dominates because the pilot is a Deloitte joining cohort.
DOMAINS = list(ALLOWED_DOMAINS.keys())
DOMAIN_P = [0.5, 0.15, 0.1, 0.1, 0.08, 0.07]


def sample_traits(rng, centre):
    """Archetype centre + noise of -1/0/+1, clipped to each trait's valid range."""
    noise = rng.choice([-1, 0, 1], size=len(centre), p=[0.2, 0.6, 0.2])
    vals = []
    for t, c, n in zip(TRAITS, centre, noise):
        lo, hi = TRAIT_RANGE[t]
        vals.append(int(np.clip(c + n, lo, hi)))
    return dict(zip(TRAITS, vals))


def main():
    rng = np.random.default_rng(SEED)
    names_used = set()
    rows = []
    arch_names = list(ARCHETYPES)
    for i in range(N):
        arch = arch_names[i % len(arch_names)]  # balanced archetypes (40 each)
        traits = sample_traits(rng, ARCHETYPES[arch])

        gender = rng.choice(["Female", "Male", "Non-binary"], p=[0.46, 0.52, 0.02])
        pool = {"Female": FIRST_F, "Male": FIRST_M, "Non-binary": FIRST_NB}[gender]
        while True:
            name = f"{rng.choice(pool)} {rng.choice(LAST)}"
            if name not in names_used:
                names_used.add(name)
                break
        domain = rng.choice(DOMAINS, p=DOMAIN_P)
        email = name.lower().replace(" ", ".") + "@" + domain

        # Budgets: fresher salaries in Hyderabad -> mostly 8k-16k per person.
        bmin = int(rng.integers(16, 31)) * 500          # 8000..15000
        bmax = min(25000, bmin + int(rng.integers(6, 15)) * 500)  # +3000..7000

        # 5-15% of people get 1-3 dealbreakers (target ~10%).
        dealbreakers = []
        if rng.random() < 0.10:
            opts = ARCHETYPE_DEALBREAKERS[arch]
            k = int(rng.integers(1, min(3, len(opts)) + 1))
            dealbreakers = list(rng.choice(opts, size=k, replace=False))
        # Keep people consistent with their own dealbreakers.
        if "veg_kitchen" in dealbreakers:
            traits["food"] = 1
        if "no_smokers" in dealbreakers:
            traits["smoking"] = 1
        if "no_drinking" in dealbreakers:
            traits["drinking"] = 1
        if "quiet_home" in dealbreakers:
            traits["noise_tolerance"] = min(traits["noise_tolerance"], 2)
            traits["guests_frequency"] = min(traits["guests_frequency"], 2)

        rows.append({
            "id": f"U{i + 1:03d}",
            "name": name,
            "email": email,
            "verified": True,
            "organisation": ALLOWED_DOMAINS[domain],
            "office_location": rng.choice(OFFICES),
            "joining_month": rng.choice(JOINING_MONTHS),
            "gender": gender,
            "preferred_gender_mix": "same only" if rng.random() < 0.6 else "any",
            "budget_min": bmin,
            "budget_max": bmax,
            "flat_size_pref": int(rng.choice([2, 3, 4], p=[0.3, 0.45, 0.25])),
            **traits,
            "free_text": rng.choice(FREE_TEXT[arch]),
            "dealbreakers": ";".join(dealbreakers),
            "_true_archetype": arch,  # HIDDEN: evaluation only, never a feature
        })

    df = pd.DataFrame(rows)
    df.to_csv(OUT, index=False)
    print(f"Wrote {len(df)} profiles to {OUT}")
    print(df["_true_archetype"].value_counts().to_string())
    print(f"With dealbreakers: {(df['dealbreakers'] != '').mean():.0%}")


if __name__ == "__main__":
    main()
