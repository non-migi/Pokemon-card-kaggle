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

## 戦略ロードマップ(AI主導・ドメイン知識最小)

ポケカの知識がなくても戦える根拠: 合法手リストが毎ターン与えられるため、ルールの理解はシミュレータに任せられる。
必要なのは「どの合法手が良いか」の評価であり、これは探索と自己対戦学習で獲得できる。
1試合数十msで回るため、数百万試合規模の自己対戦が可能 = データ駆動アプローチと相性が良い。

### Phase 0: 環境構築 — 完了
- [x] 両部門に参加登録・Kaggle CLI(pipx, v2.2.3)・`kaggle auth login`
- [x] カードデータ・エンジンC++ソース・サンプル提出物のダウンロード
- [x] ローカルで自己対戦が回る状態(.venv + kaggle-environments)

### Phase 1: ベースライン — 完了 (2026-07-09)
- [x] Observation / 行動空間の解析 → `docs/observation.md`(公式`cg/api.py`が完全な型定義)
- [x] 評価基盤 `scripts/evaluate.py`(並列A/B対戦+Wilson95%CI)、敗因分析 `scripts/diagnose.py`
- [x] ヒューリスティックv1 (`submission/main.py`): **vs random 93%、vs first 49.7%**(サンプルデッキのミラー戦)
  - アブレーションで確認: 自発的な「逃げる」は悪手(41%→51%)/ワザは最大ダメージ選択が正解/効果発動YES/NOは差なし
- [x] 初回提出完了(`submission-v1.tar.gz`)

### Phase 2: 探索ベース(〜3週目)
- **公式探索API `search_begin`/`search_step`**(cg/api.py)が決定化シミュレーションを提供 — 相手の隠れ情報(手札・山札・サイド)をサンプリングして与えると、エンジン内で任意の手を試し分岐できる(=そのままMCTSの木になる)
- 自分のデッキリストは既知なので、ログから自分の隠れゾーンはほぼ確定できる。相手はデッキ推定(メタ読み)が価値を持つ
- 600秒/試合の持ち時間内に収める時間管理(1手あたりの探索打ち切り)

### Phase 3: 学習ベース(〜締切)
- 自己対戦データから価値関数・方策を学習(模倣学習 → 強化学習 / AlphaZero系)
- 学習した評価関数で探索を強化(推論は高速に保つ)
- デッキ構築の最適化: カードプール内でデッキ同士を総当たり自己対戦させ、強いデッキをデータ駆動で発見

### Phase 4: Strategy部門対策
- 技術レポート執筆(手法の独創性・実験結果・デッキ構築の根拠を定量的に示す)
- LB上位デッキ・エージェントのメタ分析と対策

## リポジトリ構成

```
├── README.md            # このファイル(概要・ロードマップ)
├── CLAUDE.md            # AI開発セッション用の要点(コマンド・禁則)
├── docs/
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
