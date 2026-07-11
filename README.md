# ポケモンTCG AIバトルチャレンジ 参戦プロジェクト

Kaggleコンペ「Pokémon TCG AI Battle Challenge」で上位入賞を目指すリポジトリ。

**方針: AI主導で開発する。ポケカのドメイン知識に頼らず、シミュレータからの学習・探索・データ分析で勝つ。**

## コンペ概要

株式会社ポケモン × HEROZ × 松尾研究所が主催、Google / Google Cloud / NVIDIA / Kaggle 後援。
ポケモンカードの対戦を自動プレイするAIエージェントを開発し、参加者同士のAIを対戦させて強さを競う。

ポケカは**不完全情報ゲーム**(相手の手札が見えない・ドローがランダム・盤面が毎ターン変化)であり、
チェスや囲碁のような完全情報ゲームとは異なるAI技術が問われる。

### 2部門構成(締切はKaggle CLIで確認済み)

| 部門 | 内容 | 締切 (UTC) | 参加状況 |
|---|---|---|---|
| [Simulation](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle) | エージェント提出→24時間自動対戦。レーティングでLB順位変動。賞金なし(Knowledge) | **2026-08-16 23:59** | **未参加(要Webでルール同意)** |
| [Strategy](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle-challenge-strategy) | 対戦成績+技術レポート審査。賞金総額 $240,000。上位8チームがファイナル進出 | **2026-09-13 23:59** | 参加済み |

- ファイナル: 2026年9月以降に日本で開催、YouTube配信予定
- 賞金: Strategy上位8チーム 各$30,000 + ファイナル優勝 +$50,000 / 準優勝 +$30,000
- チーム: 個人 or 最大5名。Simulation部門の提出は1日5回まで

## 技術仕様(ローカル検証済み)

### シミュレータ: cabt Engine

- 公式ドキュメント: https://matsuoinstitute.github.io/cabt/
- **`pip install kaggle-environments` に同梱**(`kaggle_environments/envs/cabt/`)。コアはネイティブライブラリ(libcg.dylib / .so / .dll)でクローズドソース
- 対戦は爆速: **1試合あたり数ms〜100ms程度** → 大規模自己対戦・強化学習が現実的

### エージェントプロトコル(cabt.py のソースで確認)

```python
def agent(obs: dict) -> list[int]:
    if obs["select"] is None:
        return DECK          # 初回呼び出し: 60枚のカードIDリストを返す(=デッキ提出)
    # 以降: 提示された選択肢からインデックスを選んで返す
    # obs["select"] = {"type", "context", "minCount", "maxCount", "option": [...]}
    # obs["current"] = 盤面(turn, yourIndex, players, stadium, result, ...)
    # obs["logs"] = イベント履歴
    return [0]               # option のインデックスを minCount〜maxCount 個
```

- **デッキ提出もエージェントの初手**。デッキが60枚でない/不正なら即負け(INVALID)
- 持ち時間: `remainingOverageTime = 600秒`(1試合の合計超過時間)。使い切ると負け
- 報酬: 勝ち +1 / 負け -1 / 引き分け 0
- 組み込みベースライン: `"random"`, `"first"` エージェント

### ローカル実行

```bash
# セットアップ(済み。Python 3.14はpygameがビルド不可のため3.12を使用)
python3.12 -m venv .venv
.venv/bin/pip install kaggle-environments

# 動作確認: random vs first を20戦
.venv/bin/python scripts/run_match.py 20
```

### データ(data/strategy/ にダウンロード済み)

- `EN_Card_Data.csv` / `JP_Card_Data.csv`: 使用可能カードプール(約2,100行)。ID・カード名・HP・タイプ・ワザ・効果テキストなど
- `Card_ID List_*.pdf`: カード画像付き一覧(130MB超、git管理外)

### 便利な外部リソース

- [cabt-viewer](https://x.com/hAru_mAki_ch/status/2067787433614389400): 対戦ログ可視化ツール(OSS)
- [wmh/ptcg-abc](https://github.com/wmh/ptcg-abc): 公開されているルールベースエージェント+メタ分析(参考・要ライセンス確認)
- `env.render(mode="html")` で公式ビジュアライザ出力も可能

## 現在地と戦略(2026-07-12更新 — 詳細は docs/plan.md)

世代の変遷(詳細な数値は docs/versions.md / docs/experiments.md):

| 世代 | 中身 | 結果 |
|---|---|---|
| v1.x (07-09) | 優先度ヒューリスティック | ラダー平衡 ~617 |
| v2.x (07-09〜11) | 決定化フラットMC探索 + 相手デッキ推定belief | 平衡 ~600(ローカルでは強いがラダーで伸びず) |
| **v3.0 (07-12〜)** | **BC方策**(公式トップエピソード37.4万手の模倣、top-1 60.9%)+ トップメタデッキ | 稼働中(オーロンゲ型/フーディン型のペアA/B) |

### 現在の主力: BC方策 + デッキ共適応

- v2世代で「**デッキの強さはプレイヤーの質とセット**」を発見(LB王者のフーディン型は、うちの探索AIでは操縦不能=総当たり最下位)
- 公式の**Daily Top Episodesデータセット**(レート1000+の実プレイ)から勝者の意思決定を模倣学習し、この問題を解決。BC+フーディン型は旧最強(v2.1)に86%勝ち
- 探索・belief・ヒューリスティックはフォールバック・部品として残存(`PTCG_ALGO`で切替可能)

### 今後の主要マイルストーン(ゲート判定はdocs/plan.md)

1. **G2' (7/14)**: v3.0ペアのラダー観測 → 軸デッキ確定
2. 〜7/20: BC改良サイクル(データ日数追加・特徴量v2・BC操縦でのデッキ再最適化)
3. 〜8/3: BCを超える(BC×探索の統合 or RL自己対戦ファインチューニング)— **G3**
4. 8/10フリーズ → 8/14最終2枠 → 8/16 Simulation締切
5. 8/17〜9/13: Strategy部門Writeup(審査配点100%はレポート。Simulation成績はその証拠)

## リポジトリ構成

```
├── README.md            # このファイル(概要・ロードマップ)
├── CLAUDE.md            # AI開発セッション用の要点(コマンド・禁則)
├── docs/
│   ├── plan.md          # 締切までの全体計画(週次スケジュール・判断ゲート)
│   ├── versions.md      # バージョン履歴(変更点・デッキ・戦略・レートの一覧表)
│   ├── observation.md   # エージェントAPI仕様(obs構造・公式探索API)
│   ├── architecture.md  # ランタイム/オフラインの設計
│   ├── development.md   # セットアップ・開発ループ・提出手順・落とし穴
│   └── experiments.md   # 実験ログ(Strategyレポートの素材)
├── submission/          # 提出物(main.py + deck.csv。cg/はgit外→development.mdで復元)
├── scripts/
│   ├── evaluate.py      # 並列A/B対戦 + Wilson CI
│   ├── diagnose.py      # 敗因・ターン数集計
│   ├── package.py       # 提出前検証(ローダー互換)+ tar.gz作成
│   └── run_match.py     # 動作確認
└── data/                # コンペ配布物(git外。カードCSV・エンジンC++・サンプル)
```

※ `data/` と `submission/cg/` はコンペ配布物(再配布禁止)のためgit管理外。クローン後は `docs/development.md` の手順で復元する。

## リスク・注意点

- 提出環境の制約(CPU/GPU、メモリ、追加パッケージ可否)は未確認 → Simulation部門参加後にOverview/Rulesで確認
- 持ち時間600秒/試合。重い推論は失格リスク。ローカルで時間計測を常にログする
- 提出1日5回制限 → ローカル評価基盤の精度が生命線
