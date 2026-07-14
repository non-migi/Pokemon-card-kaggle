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
    tar_path = os.path.join(ROOT, "build", f"{name}.tar.gz")
    # 検証失敗後に同名の古い提出物を誤送信しないよう、full build開始時に除去する。
    if tar and os.path.exists(tar_path):
        os.remove(tar_path)
    _validate_spec(spec, spec_path)
    if tar and (spec.get("config") or {}).get("fixed_search_worlds") is not None:
        raise ValueError(f"{spec_path}: fixed_search_worlds入りagentはtar化禁止(ローカル評価専用)")

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
            src_file = os.path.join(mdir, fn)
            if fn != "META.json" and os.path.isfile(src_file):
                shutil.copy(src_file, os.path.join(out, "ptcg", fn))
    # 設定
    with open(os.path.join(out, "agent_config.json"), "w") as f:
        json.dump(spec.get("config", {}), f)

    if validate:
        _validate(out)
    if tar:
        members = [m for m in os.listdir(out)]
        subprocess.run(["tar", "czf", tar_path, "-C", out, *members], check=True)
        print(f"built: {tar_path} ({os.path.getsize(tar_path) / 1e6:.1f}MB)")
        return tar_path
    return out


def _validate_spec(spec: dict, spec_path: str) -> None:
    """設定事故をビルド前に止める(ランタイムの例外フォールバックへ隠さない)。"""
    config = spec.get("config") or {}
    algo = str(config.get("algo", ""))
    if "bc" in algo:
        model = spec.get("model")
        if not model:
            raise ValueError(f"{spec_path}: {algo}にはmodel指定が必要")
        model_dir = os.path.join(ROOT, "models", model)
        for filename in ("policy_params.npz", "policy_vocab.py"):
            if not os.path.isfile(os.path.join(model_dir, filename)):
                raise ValueError(f"{spec_path}: model asset不足: {model}/{filename}")
    fixed = config.get("fixed_search_worlds")
    if fixed is not None and (not isinstance(fixed, int) or isinstance(fixed, bool)
                              or not 2 <= fixed <= 24):
        raise ValueError(f"{spec_path}: fixed_search_worldsは2..24の整数")


def _validate(agent_dir: str) -> None:
    """Kaggleと同じファイルパスロードで両席1戦ずつ(必須の事前検証)。"""
    from kaggle_environments import make

    main_path = os.path.join(agent_dir, "main.py")
    for agents, seat in (([main_path, "random"], 0), (["random", main_path], 1)):
        env = make("cabt")
        env.run(agents)
        status = env.state[seat].status
        if status != "DONE":
            err = next(
                (step[seat].get("error") for step in reversed(env.steps)
                 if step[seat].get("error")),
                None,
            )
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
