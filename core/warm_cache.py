"""
Pre-fill data/llm_cache.json before a demo.  Run:  python -m core.warm_cache U001 U042

WHY: live Gemini calls take ~10-15s each. Warming the cache for the demo users
means every click during the demo is instant and works even on bad Wi-Fi.
For each user it warms exactly what the app will request: profile trait
extraction, and for every card in their deck the explanation, area summary and
house agreement. Template fallbacks are never cached, so just re-run on failure.
"""
import sys
import time

from core import llm
from core.cluster import run_clustering
from core.encode import load_cohort
from core.grouping import build_all, user_deck

PAUSE_S = 4


def warm(user_ids):
    if not llm.llm_available():
        sys.exit("No GEMINI_API_KEY in .env -- nothing to warm.")
    df = load_cohort()
    cl = run_clustering(df)
    res = build_all(df, cl)
    for uid in user_ids:
        if uid not in set(df["id"]):
            print(f"{uid}: not in cohort, skipped")
            continue
        jobs = [("traits", llm.extract_traits, df[df["id"] == uid].iloc[0]["free_text"])]
        deck, _ = user_deck(df, cl, res, uid)
        for g in deck:
            jobs += [("explain", llm.explain_group, g), ("areas", llm.suggest_areas, g),
                     ("agreement", llm.house_agreement, g)]
        for name, fn, arg in jobs:
            t = time.time()
            source = fn(arg)[-1]
            print(f"{uid} {name:9s} {source:8s} {time.time() - t:5.1f}s"
                  + (f"  <- {llm.LAST_ERROR['msg']}" if source == "Template" and llm.LAST_ERROR["msg"] else ""))
            # WHY pause: the free tier limits requests per minute; pacing avoids 429s.
            if source == "AI" and time.time() - t > 0.5:
                time.sleep(PAUSE_S)


if __name__ == "__main__":
    warm(sys.argv[1:] or ["U001"])
