"""提出物のパッケージング + Kaggleローダー互換の検証。

使い方:
    .venv/bin/python scripts/package.py [バージョン名]

1. submission/main.py を「ファイルパスとして」ロードして1戦ずつ先手/後手で実行
   (Kaggleサーバと同じ exec ベースのローダーを通す。__file__問題などを検出)
2. 通ったら submission-<version>.tar.gz を作成
"""

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUB = os.path.join(ROOT, "submission")


def validate() -> None:
    from kaggle_environments import make

    main_path = os.path.join(SUB, "main.py")
    for agents, seat in ((
        [main_path, "random"], 0), (["random", main_path], 1)):
        env = make("cabt")
        env.run(agents)
        status = env.state[seat].status
        if status != "DONE":
            err = env.steps[0][0].get("error")
            raise SystemExit(f"NG: seat={seat} status={status} error={err}")
        print(f"OK: seat={seat} reward={env.state[seat].reward}")


def package(version: str) -> None:
    out = os.path.join(ROOT, f"submission-{version}.tar.gz")
    pycache = os.path.join(SUB, "cg", "__pycache__")
    if os.path.exists(pycache):
        subprocess.run(["rm", "-rf", pycache], check=True)
    members = [m for m in os.listdir(SUB) if not m.startswith(".") and m != "__pycache__"]
    subprocess.run(["tar", "czf", out, "-C", SUB, *members], check=True)
    size = os.path.getsize(out) / 1e6
    print(f"created: {out} ({size:.1f}MB)")
    print(f"submit: kaggle competitions submit -c pokemon-tcg-ai-battle -f {os.path.basename(out)} -m '<説明>'")


if __name__ == "__main__":
    validate()
    package(sys.argv[1] if len(sys.argv) > 1 else "dev")
