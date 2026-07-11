"""エージェントビルダー: agents/<name>.json → build/<name>/ + tar.gz。

エージェント定義(JSON):
    {
      "label": "説明",
      "deck": "decks/meta/meta_01.csv",       # 60行のカードID
      "model": "bc_v0",                        # models/<model>/ を ptcg/ に注入(nullで無し)
      "config": {"algo": "bc", "max_move_sec": 8.0}   # agent_config.json として同梱
    }

使い方:
    .venv/bin/python -m ptcglab.build v3.0g            # 組立て+ローダー検証+tar
    .venv/bin/python -m ptcglab.build v3.0g --no-tar   # 組立て+検証のみ(ローカルA/B用)
"""

import argparse
import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def build(name: str, validate: bool = True, tar: bool = True) -> str:
    spec_path = os.path.join(ROOT, "agents", f"{name}.json")
    with open(spec_path) as f:
        spec = json.load(f)

    src = os.path.join(ROOT, "src")
    out = os.path.join(ROOT, "build", name)
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out)

    # コード
    shutil.copy(os.path.join(src, "main.py"), out)
    shutil.copytree(os.path.join(src, "ptcg"), os.path.join(out, "ptcg"),
                    ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(os.path.join(src, "cg"), os.path.join(out, "cg"),
                    ignore=shutil.ignore_patterns("__pycache__"))
    # デッキ
    shutil.copy(os.path.join(ROOT, spec["deck"]), os.path.join(out, "deck.csv"))
    # モデル
    if spec.get("model"):
        mdir = os.path.join(ROOT, "models", spec["model"])
        for fn in os.listdir(mdir):
            if fn != "META.json":
                shutil.copy(os.path.join(mdir, fn), os.path.join(out, "ptcg", fn))
    # 設定
    with open(os.path.join(out, "agent_config.json"), "w") as f:
        json.dump(spec.get("config", {}), f)

    if validate:
        _validate(out)
    if tar:
        tar_path = os.path.join(ROOT, "build", f"{name}.tar.gz")
        members = [m for m in os.listdir(out)]
        subprocess.run(["tar", "czf", tar_path, "-C", out, *members], check=True)
        print(f"built: {tar_path} ({os.path.getsize(tar_path) / 1e6:.1f}MB)")
        return tar_path
    return out


def _validate(agent_dir: str) -> None:
    """Kaggleと同じファイルパスロードで両席1戦ずつ(必須の事前検証)。"""
    from kaggle_environments import make

    main_path = os.path.join(agent_dir, "main.py")
    for agents, seat in (([main_path, "random"], 0), (["random", main_path], 1)):
        env = make("cabt")
        env.run(agents)
        status = env.state[seat].status
        if status != "DONE":
            err = env.steps[0][0].get("error")
            raise SystemExit(f"検証NG: {agent_dir} seat={seat} status={status} error={err}")
    print(f"validated: {agent_dir} (両席DONE)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("names", nargs="+", help="agents/<name>.json の name")
    ap.add_argument("--no-tar", action="store_true")
    ap.add_argument("--no-validate", action="store_true")
    args = ap.parse_args()
    for name in args.names:
        build(name, validate=not args.no_validate, tar=not args.no_tar)
