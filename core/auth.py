"""
Accounts: email + password login with two roles.

  member - a fresher/intern. Sees only their own profile, matches and flat.
  admin  - HR at a partner organisation. Sees their own organisation's joiners
           (matching itself runs on the whole partner cohort).

WHY a JSON file (not a DB or an auth provider): a 48h prototype needs real
sign-up/login behaviour the panel can poke at, not production infrastructure.
Swapping this module for Auth0/Cognito later doesn't touch any page code.

WHY PBKDF2 with a per-user salt: it is in the standard library (no new
dependency) and never stores a password in plain text, even in a demo.
"""
import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timezone

from dotenv import load_dotenv

from core.encode import DATA_DIR, seed_ids
from core.schema import ALLOWED_DOMAINS, email_domain, is_allowed_email

load_dotenv()

ACCOUNTS_JSON = os.path.join(DATA_DIR, "accounts.json")
MIN_PASSWORD = 8
_ITERATIONS = 200_000

# Seeded HR account so the admin route can be demoed with a real login.
# WHY only in demo mode: its password is public (README, login page), so on a
# deployment without NESTMATE_DEMO=1 it must not be created or accept logins.
DEMO_ADMIN = {"email": "hr@deloitte.com", "password": "nestmate-hr", "name": "Priya Nair"}


def _hash(password, salt_hex):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), _ITERATIONS).hex()


def _new_record(name, email, password, role, **extra):
    salt = secrets.token_hex(16)
    return {"email": email, "name": name, "role": role,
            "organisation": ALLOWED_DOMAINS.get(email_domain(email), ""),
            "salt": salt, "password_hash": _hash(password, salt),
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **extra}


def _load():
    accounts = {}
    if os.path.exists(ACCOUNTS_JSON):
        with open(ACCOUNTS_JSON, encoding="utf-8") as f:
            accounts = json.load(f)
    if demo_enabled() and DEMO_ADMIN["email"] not in accounts:
        accounts[DEMO_ADMIN["email"]] = _new_record(DEMO_ADMIN["name"], DEMO_ADMIN["email"],
                                                    DEMO_ADMIN["password"], "admin")
        _save(accounts)
    return accounts


def _save(accounts):
    with open(ACCOUNTS_JSON, "w", encoding="utf-8") as f:
        json.dump(accounts, f, indent=2)


def public(record):
    """What the app keeps in the session: never the hash or salt."""
    return {k: v for k, v in record.items() if k not in ("salt", "password_hash")}


def member_id(email):
    # Stable id from the email, so re-signing up maps to the same cohort profile.
    return "N" + hashlib.sha1(email.lower().encode()).hexdigest()[:6]


def sign_up(name, email, password, confirm, gender, office, joining_month):
    """Returns (account, None) on success or (None, error message)."""
    name, email = name.strip(), email.strip().lower()
    if not name:
        return None, "Enter your full name."
    if "@" not in email:
        return None, "Enter a valid email address."
    # WHY a domain allow-list: verified work/college email is our trust & safety layer.
    if not is_allowed_email(email):
        return None, (f"{email_domain(email)} isn't a partner organisation yet. "
                      f"Use an email from: {', '.join(ALLOWED_DOMAINS)}.")
    if len(password) < MIN_PASSWORD:
        return None, f"Password must be at least {MIN_PASSWORD} characters."
    if password != confirm:
        return None, "Passwords don't match."
    accounts = _load()
    # WHY reserved: nobody may claim the demo HR address as a normal account.
    if email in accounts or email == DEMO_ADMIN["email"]:
        return None, "An account with this email already exists. Log in instead."
    accounts[email] = _new_record(name, email, password, "member", user_id=member_id(email),
                                  gender=gender, office_location=office, joining_month=joining_month)
    _save(accounts)
    return public(accounts[email]), None


def log_in(email, password):
    """Returns (account, None) or (None, error). One generic error on purpose:
    don't reveal whether the email exists."""
    email = email.strip().lower()
    if email == DEMO_ADMIN["email"] and not demo_enabled():
        return None, "Email or password is incorrect."
    rec = _load().get(email)
    if rec and hmac.compare_digest(rec["password_hash"], _hash(password, rec["salt"])):
        return public(rec), None
    return None, "Email or password is incorrect."


# ---------------------------------------------------------------------------
# Demo mode: one-click entry for the live demo, clearly labelled in the UI.
#
# WHY opt-in via NESTMATE_DEMO=1: demo mode logs in WITHOUT a password (as HR
# admin or as a cohort member), so it must never be on by accident on a shared
# deployment. WHY only seed profiles: real sign-ups must never be impersonable,
# even with demo mode on.
# ---------------------------------------------------------------------------
def demo_enabled():
    return os.getenv("NESTMATE_DEMO", "").strip().lower() in ("1", "true", "yes")


def _require_demo():
    if not demo_enabled():
        raise PermissionError("Demo mode is off (set NESTMATE_DEMO=1).")


def demo_admin():
    _require_demo()
    return {**public(_load()[DEMO_ADMIN["email"]]), "demo": True}


def _seeded_people():
    from core import store  # local import: store imports encode, which auth also uses
    return {p["id"]: p for p in store.load("people") if p.get("seeded")}


def demo_member(row):
    """Sign in as an existing synthetic seed member, who has no password."""
    _require_demo()
    if row["id"] not in seed_ids():
        raise PermissionError("Demo mode can only sign in as synthetic seed profiles.")
    return {"email": row["email"], "name": row["name"], "role": "member", "user_id": row["id"],
            "organisation": row["organisation"], "gender": row["gender"],
            "office_location": row["office_location"], "joining_month": row["joining_month"], "demo": True}


# One-tap demo accounts, each labelled by the story it shows (seeded by data/seed_market.py).
DEMO_PERSONAS = [
    {"id": "U102", "label": "Looking for a flat and flatmates", "who": "Arjun Gupta, lifestyle quiz done"},
    {"id": "O001", "label": "Renting out a flat", "who": "Mr. Rao, a group application is waiting"},
    {"id": "U167", "label": "Tenant with a spare room", "who": "Rahul Patel, his landlord isn't on the app"},
]


def demo_persona(pid, cohort):
    """Sign in as a seeded demo account: a synthetic cohort member or a seeded
    landlord. Never a real sign-up."""
    _require_demo()
    rows = cohort[cohort["id"] == pid]
    if pid in seed_ids() and len(rows):
        return demo_member(rows.iloc[0].to_dict())
    p = _seeded_people().get(pid)
    if not p:
        raise PermissionError("Demo mode can only sign in as seeded accounts.")
    return {"email": p["email"], "name": p["name"], "role": "member", "user_id": p["id"],
            "organisation": "", "gender": p.get("gender", ""), "office_location": None, "joining_month": None,
            "demo": True}
