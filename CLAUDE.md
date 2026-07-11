# Pokemon TCG AI Battle Challenge

Kaggleコンペで上位入賞を狙う。**AI主導開発・ポケカのドメイン知識に頼らない**(探索・自己対戦学習・データ駆動で勝つ)。

## 必読ドキュメント

- `README.md` — コンペ概要・ロードマップ(Phase 0-4)・現在地
- `docs/plan.md` — 締切までの週次計画と判断ゲート(**週次でレビュー・更新**)
- `docs/observation.md` — エージェントAPI仕様(obs構造・探索API)
- `docs/architecture.md` — ランタイム/オフラインの設計
- `docs/development.md` — 開発ループ・提出手順・落とし穴
- `docs/experiments.md` — 実験ログ(**変更したら必ず追記**)
- `docs/versions.md` — バージョン履歴の一覧表(**提出したら必ず1行追加+詳細節を書く**)

## よく使うコマンド

```bash
.venv/bin/python scripts/evaluate.py submission/main.py --vs <dir>/main.py -n 300 -j 8  # A/B評価
.venv/bin/python scripts/ladder_stats.py                                        # LB実戦成績(リプレイ集計)
.venv/bin/python scripts/bc_extract.py <エピソードdir> --out data/bc/X.jsonl.gz  # BC教師データ抽出
.venv/bin/python scripts/train_bc.py --data data/bc/X.jsonl.gz --epochs 5       # BC学習→params出力
.venv/bin/python scripts/bc_matchups.py 200                                     # BC×デッキのマッチアップ表
.venv/bin/python scripts/package.py vX.Y                                        # 提出前検証+tar作成
kaggle competitions submissions -c pokemon-tcg-ai-battle | head -5              # 提出状況/レート
```

主力はBC方策(ptcg/policy.py)。`PTCG_ALGO`環境変数で bc / search / bc_search を切替(A/Bは環境変数でなくコピーにハードコード — 同一プロセスで両者に効いてしまうため)。

## 絶対に守ること

- **提出前に `scripts/package.py` を通す**(Kaggleローダーは`exec(code, {})`: `__file__`無し、main.py最後のcallableがagentになる)
- 提出は1日5回まで。evaluate.pyで有意改善(Wilson CI)を確認してから提出
- `data/` と `submission/cg/` はコンペ配布物(再配布禁止)— **絶対にコミットしない**。復元手順はdocs/development.md
- enum(SelectContext等)はコンペ期間中に追加されうる — intで比較し、未知値で落ちない実装を維持
- 実験結果(採用も棄却も)を `docs/experiments.md` に記録(Strategy部門レポートの素材)

## 環境メモ

- venvはPython 3.12(3.14はpygameビルド不可)
- kaggle_environmentsの`make("cabt")`がシミュレータ本体。1試合数十ms
- 締切: Simulation 2026-08-16 / Strategy 2026-09-13(UTC)
