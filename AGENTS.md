# AGENTS.md — AIエージェント共通の作業マニュアル

このリポジトリは複数のAIコーディングエージェント(Claude Code / Codex 等)が交代・並行で作業する。
**引き継ぎ状態はすべてリポジトリ内に置く**(エージェント固有のメモリに依存しない)。

## まず読むもの(順に)

1. `STATUS.md` — 今の状態と次のアクション(**作業を終えるたび必ず更新**)
2. `docs/plan.md` — 締切までの計画と判断ゲート
3. `docs/versions.md` — 提出履歴 / `docs/experiments.md` — 実験ログ(採用も棄却も記録)
4. `docs/architecture.md` — 設計 / `docs/development.md` — セットアップと手順詳細

## リポジトリ構成

```
src/            ランタイム(main.py + ptcg/)。cg/はコンペ配布物(git外、development.md参照)
agents/         エージェント定義(JSONのみ)。変種はここに宣言し、コードをコピーしない
models/         学習済みモデルのレジストリ(META.json付き)。上書き禁止・追加のみ
ptcglab/        オフライン共通ライブラリ(arena=対戦評価の唯一の実装, build=組立て)
scripts/        薄いCLI・分析ツール
results/        測定台帳(arena.jsonlに全A/B結果が自動追記される)。過去の測定はまずここを検索
decks/          デッキCSV(sample.csv, meta/=メタスナップショット, 候補)
docs/           ドキュメント一式
```

## 主要コマンド

```bash
# エージェントの組立て+検証+tar(提出物は必ずこれで作る)
.venv/bin/python -m ptcglab.build v3.0g

# A/B評価(結果は results/arena.jsonl に自動記録)
.venv/bin/python scripts/evaluate.py build/v3.0g --vs build/v3.0a -n 200 -j 8 --note "説明"

# BC学習(モデルは models/<name>/ へ。上書き不可)
.venv/bin/python scripts/bc_extract.py <エピソードdir> --out data/bc/X.jsonl.gz
.venv/bin/python scripts/train_bc.py --data data/bc/X.jsonl.gz --epochs 5 --name bc_vN

# ラダー状況
kaggle competitions submissions -c pokemon-tcg-ai-battle | head -5
.venv/bin/python scripts/ladder_stats.py
```

## 絶対ルール

1. **提出前に必ず `ptcglab.build` の検証を通す**(Kaggleローダーは`exec(code,{})`: `__file__`無し、
   main.pyの最後のcallableがagent。ファイルパスロード両席テストが唯一の事前検証)
2. **提出は1日5回まで・最終評価は「最新2提出」のみ**。提出前に必ず
   `kaggle competitions submissions`で現状確認(他エージェントが先に提出している可能性)。
   提出したら `docs/versions.md` に1行追記+`STATUS.md`更新
3. **設定は agent_config.json**(agents/*.jsonのconfig)。環境変数での挙動切替は禁止
   (同一プロセスのA/B相手に漏れる事故が実際に起きた)
4. **測定の前に results/arena.jsonl を検索**(同じ比較が済んでいないか)。実験結果は
   `docs/experiments.md` に記録(棄却も含む)
5. **重負荷ジョブ(学習・大量自己対戦)と時間依存の評価(search系)を並走させない**
6. models/ は追加のみ(上書き禁止)。data/ と src/cg/ はコミット禁止(ライセンス)
7. **作業開始時に `git pull`、区切りごとに commit+push**(他エージェントとの衝突防止。
   同時作業する場合は STATUS.md の「作業中」欄に名前と対象を書いてから触る)
8. enumはintで比較(コンペ期間中に要素追加がありうる)。例外時は必ず下段フォールバック
9. **BCモデル入りのptcgが必要なツールは build/<agent>/ を参照する**(src/ptcgはモデル非同梱)。
   かつ ptcg を他のimport(特にdeck_lib — src をsys.path先頭に挿す)より**先に**importする。
   結果が急に弱くなったら、まず `policy.ENABLED` を疑う(assertを入れておくのが正解)

## ドメイン知識の要点

- レートは平衡収束する(早期の成績は持ち越されない)。判定は80戦/±50を同格とみなす
- BC方策はデッキとセット(訓練分布外のデッキでは弱い)
- 1000+帯の51.7%がフーディン型。三すくみ: オーロンゲ > フーディン > サンプル系 > オーロンゲ
- 詳細は docs/study-guide.md(ポケカ入門)と docs/research-notes.md(コミュニティ調査)
