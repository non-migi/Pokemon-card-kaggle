#!/usr/bin/env python3
"""Rate-limit-friendly replay fetcher for the ladder_matchups cache.

Usage: replay_fetch_slow.py <submission_id> [<submission_id> ...] [--sleep 5]
Downloads every episode replay of the given submissions into ~/.cache/ptcg-replays
(the cache ladder_matchups.py / ladder_stats.py read), skipping files already present,
sleeping between calls and backing off on HTTP 429. Safe to re-run (resumes).
"""
import argparse, json, os, subprocess, sys, time

CACHE = os.path.expanduser("~/.cache/ptcg-replays")


def kg(*args, timeout=180):
    r = subprocess.run(["kaggle", *args], capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stdout, r.stderr


def episode_ids(sub_id):
    _, out, _ = kg("competitions", "episodes", sub_id, "--format", "json")
    # output may carry a trailing "Next Page Token" line after the JSON array
    arr, _ = json.JSONDecoder().raw_decode(out[out.index("["):])
    return [str(e["id"]) for e in arr]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("subs", nargs="+")
    ap.add_argument("--sleep", type=float, default=5.0)
    a = ap.parse_args()
    os.makedirs(CACHE, exist_ok=True)
    for sub in a.subs:
        ids = episode_ids(sub)
        missing = [i for i in ids if not os.path.exists(os.path.join(CACHE, f"episode-{i}-replay.json"))]
        print(f"[{sub}] episodes={len(ids)} missing={len(missing)}", flush=True)
        backoff = 60
        n_ok = 0
        for k, ep in enumerate(missing):
            path = os.path.join(CACHE, f"episode-{ep}-replay.json")
            while True:
                rc, out, err = kg("competitions", "replay", ep, "-p", CACHE)
                if os.path.exists(path):
                    n_ok += 1; backoff = 60; break
                if "429" in (out + err):
                    print(f"  429 at {ep}; sleeping {backoff}s", flush=True)
                    time.sleep(backoff); backoff = min(backoff * 2, 900)
                    continue
                print(f"  failed {ep}: {(out+err).strip()[:120]}", flush=True)
                break
            if (k + 1) % 25 == 0:
                print(f"  [{sub}] {k+1}/{len(missing)} fetched_ok={n_ok}", flush=True)
            time.sleep(a.sleep)
        print(f"[{sub}] done fetched_ok={n_ok}", flush=True)


if __name__ == "__main__":
    main()
