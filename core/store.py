"""
File-based storage for the marketplace: one JSON list of dicts per entity.

    listings.json      flats and rooms people list
    groups.json        flat groups people form (from the deck or by inviting)
    applications.json  a person or a group applying to a listing
    tenancies.json     who lives where, rent shares, the house agreement
    payments.json      monthly rent shares, due or paid (mock checkout)
    expenses.json      shared bills inside a tenancy
    people.json        seeded people who are not in the matching cohort (landlords)
    reports.json       users reporting a listing
    flag_actions.json  admin decisions on flags (dismissed / removed)
    member_state.json  small per-member settings (what they chose on Home)

WHY JSON files (not a database): same reason as profiles.csv. A one-day demo
needs data you can open in an editor and reset by re-running one script.
Writes go to a temp file and are renamed into place, so a crash or two
sessions saving at once can't leave a half-written file.

Reset: python data/seed_market.py  (rewrites every file above from scratch).
The app also seeds them on first start if listings.json is missing.
"""
import importlib.util
import json
import os
import tempfile
import threading

from core.encode import DATA_DIR

ENTITIES = ("listings", "groups", "applications", "tenancies", "payments", "expenses", "people", "reports",
            "flag_actions", "member_state")
_LOCK = threading.Lock()  # Streamlit serves sessions on threads of one process


def path(name):
    return os.path.join(DATA_DIR, f"{name}.json")


def load(name):
    try:
        with open(path(name), encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return []


def save(name, rows):
    fd, tmp = tempfile.mkstemp(dir=DATA_DIR, prefix=f".{name}.", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=1, ensure_ascii=False)
    os.replace(tmp, path(name))


def next_id(prefix, rows, width=3):
    """Short, stable ids: L001, GR002 ... (max existing + 1, never reused)."""
    nums = [int(r["id"][len(prefix):]) for r in rows if str(r.get("id", "")).startswith(prefix)
            and r["id"][len(prefix):].isdigit()]
    return f"{prefix}{(max(nums) + 1 if nums else 1):0{width}d}"


def get(name, item_id):
    return next((r for r in load(name) if r.get("id") == item_id), None)


def insert(name, row, prefix=None):
    """Append a row (assigning an id from `prefix` if it has none). Returns the row."""
    with _LOCK:
        rows = load(name)
        if prefix and not row.get("id"):
            row = {"id": next_id(prefix, rows), **row}
        rows.append(row)
        save(name, rows)
    return row


def update(name, item_id, **changes):
    """Merge `changes` into one row. Returns the updated row (or None)."""
    with _LOCK:
        rows = load(name)
        for r in rows:
            if r.get("id") == item_id:
                r.update(changes)
                save(name, rows)
                return r
    return None


def mutate(name, fn):
    """Load, let fn change the list in place (or return a new one), save. Atomic per call."""
    with _LOCK:
        rows = load(name)
        out = fn(rows)
        save(name, rows if out is None else out)
        return rows if out is None else out


def ensure_seeded():
    """Create the marketplace files on first start (fresh clone or after a reset)."""
    if os.path.exists(path("listings")):
        return
    spec = importlib.util.spec_from_file_location("seed_market", os.path.join(DATA_DIR, "seed_market.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.main(quiet=True)
