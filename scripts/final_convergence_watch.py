"""最終ペア(sub 55565273 / 55565063)の収束観察ログ。6時間間隔で2週間、CSVに追記する。

締切後のレート収束過程をWriteup用の一次データとして残す。
起動: nohup .venv/bin/python scripts/final_convergence_watch.py > /tmp/final_watch.log 2>&1 &
"""
import csv
import datetime
import os
import re
import subprocess
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "results", "final_convergence_log.csv")
SUBS = [("55565273", "v6.0o"), ("55565063", "v5.12g")]
INTERVAL = 6 * 3600
ROUNDS = 56  # 2週間

def snapshot():
    r = subprocess.run(["kaggle", "competitions", "submissions", "-c", "pokemon-tcg-ai-battle"],
                       capture_output=True, text=True, timeout=300)
    scores = {}
    for line in r.stdout.splitlines():
        m = re.match(r"\s*(\d+)\s+\S+.*COMPLETE\s+([0-9.]+)", line)
        if m:
            scores[m.group(1)] = m.group(2)
    rows = []
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M")
    for sub_id, name in SUBS:
        e = subprocess.run(["kaggle", "competitions", "episodes", sub_id],
                          capture_output=True, text=True, timeout=300)
        n = sum(1 for l in e.stdout.splitlines() if re.match(r"\s*\d{6,}\s", l))
        rows.append([ts, sub_id, name, n, scores.get(sub_id, "")])
    return rows

def main():
    new = not os.path.exists(OUT) or os.path.getsize(OUT) == 0
    for _ in range(ROUNDS):
        try:
            rows = snapshot()
            with open(OUT, "a", newline="") as f:
                w = csv.writer(f)
                if new:
                    w.writerow(["utc", "sub_id", "name", "episodes", "score"])
                    new = False
                w.writerows(rows)
                f.flush()
            print(rows, flush=True)
        except Exception as e:
            print("snapshot failed:", e, flush=True)
        time.sleep(INTERVAL)

if __name__ == "__main__":
    main()
