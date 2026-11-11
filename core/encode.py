"""
Profile <-> feature vector, plus loading/saving the cohort.

WHY CSV (not SQLite): for a 48h prototype with ~200 rows, a CSV is readable in
any editor, diffable, and easy to show the panel. Seed data (profiles.csv) is
never modified; new sign-ups go to signups.csv so the demo can be reset by
deleting one file.
"""
import os

import numpy as np
import pandas as pd

from core.schema import TRAITS

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
PROFILES_CSV = os.path.join(DATA_DIR, "profiles.csv")
SIGNUPS_CSV = os.path.join(DATA_DIR, "signups.csv")


def _clean(df):
    df = df.copy()
    df["dealbreakers"] = df["dealbreakers"].fillna("").astype(str)
    df["free_text"] = df["free_text"].fillna("").astype(str)
    for t in TRAITS + ["budget_min", "budget_max", "flat_size_pref"]:
        df[t] = df[t].astype(int)
    if "_true_archetype" not in df.columns:
        df["_true_archetype"] = ""
    df["_true_archetype"] = df["_true_archetype"].fillna("")
    return df


def load_cohort():
    """Seed profiles + any new sign-ups (a sign-up replaces a seed row with the same id)."""
    df = pd.read_csv(PROFILES_CSV)
    if os.path.exists(SIGNUPS_CSV):
        new = pd.read_csv(SIGNUPS_CSV)
        df = pd.concat([df[~df["id"].isin(new["id"])], new], ignore_index=True)
    return _clean(df)


def seed_ids():
    """Ids of the synthetic seed profiles (never real sign-ups)."""
    return set(pd.read_csv(PROFILES_CSV, usecols=["id"])["id"])


def save_signup(profile: dict):
    """Upsert one new user's profile into signups.csv."""
    row = pd.DataFrame([profile])
    if os.path.exists(SIGNUPS_CSV):
        old = pd.read_csv(SIGNUPS_CSV)
        old = old[old["id"] != profile["id"]]
        row = pd.concat([old, row], ignore_index=True)
    row.to_csv(SIGNUPS_CSV, index=False)


def dealbreaker_list(value):
    return [d for d in str(value).split(";") if d]


def to_matrix(df):
    """Quiz answers only -> (n_people, n_traits) float matrix.
    WHY only quiz answers: budget, office and gender are hard constraints handled
    in grouping; mixing them into lifestyle distance would blur the personas."""
    return df[TRAITS].to_numpy(dtype=float)
