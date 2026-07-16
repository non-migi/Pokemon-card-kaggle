# アーキテクチャ設計(2026-07-12更新: BC世代)

## 全体像

```
┌─ オフライン(このリポジトリ) ──────────────────────────────┐
│  学習:   bc_extract.py(公式トップエピソード→意思決定ペア)          │
│          train_bc.py(2タワーランカー、torch/MPS→numpyエクスポート)  │
│  評価:   arena.py(schema v2 A/B) / evaluate.py / gauntlet.py          │
│  分析:   ladder_stats.py / meta_scrape.py / band_meta.py /         │
│          diagnose.py / render_replay_jp.py(日本語リプレイ)          │
│  デッキ: deck_lib.py / deck_opt.py / deck_tournament.py             │
└──────────────────────────────────────────────┘
                 │ 検証済みのロジック・学習済みパラメータだけを反映
                 ▼
┌─ ランタイム(src/ + agents/ + models/ → build/ → Kaggle) ────────┐
│  main.py     意思決定カスケード(ALGO: 探索→BC→ヒューリスティック)  │
│  deck.csv    デッキ(60行のカードID)— BC方策とセットで選ぶ          │
│  ptcg/       自作パッケージ(下記)+ policy_params.npz(150KB)      │
│  cg/         公式ライブラリ(git管理外。配布物から復元)              │
└──────────────────────────────────────────────┘
```

## ランタイムの構成

| モジュール | 責務 | 状態 |
|---|---|---|
| `ptcg/policy.py` + `policy_features.py` | **BC方策(現主力)**。2タワー(state塔×option塔の内積)のnumpy推論。単数・複数選択、1決定<1ms | v3.0〜 |
| `ptcg/bc_search.py` | **BC×決定化探索(現主力)**。BC top-5候補をBCロールアウトで比較。`algo=bcs` | v4.0〜 |
| `ptcg/heuristics.py` | 優先度ヒューリスティック。BC/探索の例外・分布外フォールバック | 全世代 |
| `ptcg/search.py` | 旧・ヒューリスティック決定化フラットMC探索。value打ち切りは常時無効 | v2系互換 |
| `ptcg/belief.py` + `meta_decks.py` | 相手デッキ推定(可視カード×メタライブラリ照合、ミラーフォールバック) | v2.1〜 |
| `ptcg/value.py` + `features.py` | 盤面勝率の学習器。value_v1はAUC 0.851、A/B 47.8%/400で現形棄却 | 無効 |
| main.py の時間管理 | productionは残り時間の線形配分。`_spent`はdeck handshakeごとに初期化 | — |

### 設計原則(不変)
- **落ちない**: どの段も例外・分布外で下段にフォールバック。INVALIDは即負け
- **enumはintで比較**(コンペ中の追加に耐える)/ Kaggleローダーは`exec(code,{})`(`__file__`無し、最後のcallableがagent)
- **BCはデッキとセット**: 方策は訓練分布内のデッキでのみ強い。デッキ変更時は再評価必須
- **構成不良は落とす**: BC指定で`policy.ENABLED=False`なら起動失敗。実行中の例外だけを下段へ救済

## 評価基盤（arena schema v2、2026-07-14）

- `ptcglab.arena`がA/Bの唯一実装。1 processにつき席反転1ペアをロードし、native cg状態と
  agent moduleを測定ペア間で分離する。席順とペア内実行順の両方を均等化する。
- fresh-pair runnerはspawn `Process`を`Pipe`＋`connection.wait`でpair単位に監視する。
  timeout/crash/protocol errorは両席分のsynthetic failure行へ変換し、strict ledgerを残して失敗する。
  payload取得後だけ子processが終了しない場合は強制回収し、取得済み対戦結果は維持する。
- ledgerはW/D/L/unscored、P0/P1、failure、run ID/suite、git commit、kaggle-environments version、
  agent tree/config/deck/model/cg SHA、watchdog eventを持つ。終了時rehashで評価中のbuild変更も検出する。
- `production`: wall-clock探索。本番と同じだがCPU負荷に敏感なため`jobs=1`強制。
- `fixed-worlds`: ローカル比較専用。両search agentの`fixed_search_worlds`（2〜24）を一致させ、
  壁時計budgetから分離する。未完遂はmetricsでfailure。buildはこの設定入りtarを拒否する。
- `standard`: 純BC/heuristic用の高速並列screen。
- 本番時間制御のgate用に、全stepの`remainingOverageTime`最小値を全体・席別でledgerへ記録する。
- gauntletの加重勝率は入力対面内の点推定。pooled Wilson CIは重みなしで別表示する。

`train_bc2.py`はnumpy/torch seedを固定し、各epochのholdout top-1が最良のcheckpointへ戻してから
numpyへexportする。`META.json`にseed/best_epoch/holdout_top1を保存する。

---

# 目標アーキテクチャ(2026-07-12設計、AI管理性の改善)

## 動機(実際に踏んだ摩擦)

1. エージェント変種がscratchpad(揮発)に散在し再現不能 → 毎回の考古学
2. 環境変数設定が同一プロセスの両エージェントに漏れる(2回事故)
3. scripts/17本に対戦ハーネスが重複コピー → pickle事故・モジュール共有バグの温床
4. 測定結果が散文にしかなく機械参照不能 → 再測定の無駄
5. 学習モデルが提出物を直接上書き → 「提出済みのモデルはどれ」問題

## 目標構造

```
├── src/
│   ├── main.py            エントリ(同梱の agent_config.json を読む。環境変数は廃止)
│   └── ptcg/              ランタイムパッケージ(現 submission/ptcg)
├── agents/                エージェント定義 = JSONのみ(コードのコピーを持たない)
│   └── v3.0g.json         {"algo":"bc","deck":"decks/meta/meta_01.csv","model":"bc_v0","label":"..."}
├── models/                学習成果物のレジストリ(上書きしない)
│   └── bc_v0/             policy_params.npz + policy_vocab.py + META.json(データ・精度・日付)
├── ptcglab/               オフライン共通ライブラリ(pip installしない、sys.path参照)
│   ├── arena.py           対戦ランナー(モジュール分離ロード・並列・Wilson CI・結果ledger追記)
│   ├── build.py           agents/*.json → build/<name>/ を組立て→ローダー検証→tar.gz
│   ├── kaggle_io.py       CLIラッパ(submissions/episodes/replay/scrape)
│   └── stats.py           集計ユーティリティ
├── scripts/               薄いCLI(ptcglabを呼ぶだけ)。分析系ノートブック的スクリプトはそのまま
├── results/               測定ledger(arena が自動追記するJSONL: 日時,agentA,agentB,n,勝率,CI,環境)
├── decks/ docs/ data/ replays/  (現状維持)
└── build/                 生成物(git管理外)
```

## 設計のポイント

- **エージェント=設定、コード=単一**: 変種はJSONで宣言し、`build.py`が src+models+deck から組み立てる。
  過去のどのバージョンも `agents/vX.json` から1コマンドで再現可能(scratchpad考古学の廃止)
- **設定は同梱ファイル**: `agent_config.json`をビルド時に埋め込み、main.pyが読む。
  ローカルA/Bはビルド済みディレクトリ同士で行うため、プロセス内で設定が混ざる事故が構造的に消える
- **arenaの一本化**: モジュール分離ロード・並列実行・CI計算・敗因集計を1実装に集約。
  実験スクリプトはハーネスを再発明しない(バグの温床を除去)
- **結果ledger**: すべての対戦測定が results/*.jsonl に自動追記される。
  将来のセッションが「その比較は07-12に済んでいて52%だった」を機械的に引ける
- **モデルレジストリ**: 学習は models/bc_vN/ に書き、提出物へはビルド時にコピー。上書き事故の根絶

## 移行計画(段階的・各段でローダー検証)

1. ptcglab/arena.py + build.py + agents/*.json(現行 v3.0g/v3.0a/v2.1 を定義)— 既存scriptsは当面併存
2. src/ へ submission/ を移設、main.py を agent_config.json 読み込みに変更
3. train_bc.py の出力先を models/ に変更
4. evaluate/vs_deck_test/bc_matchups/deck_tournament を arena ベースに置換(旧版は削除)
5. CLAUDE.md / development.md のコマンド集を更新

リスク管理: 提出tarの内部構造(main.py+cg/+ptcg/+deck.csv)は不変。各段で `build.py --validate` が
ファイルパスロード両席テストを通すことを確認してから次へ進む。

### 設計原則

- **落ちない**: 例外・未知enum・時間切れは必ずヒューリスティックか先頭選択にフォールバック。INVALIDは即負け
- **enumはintで比較**: コンペ期間中にenum要素が追加されると公式が明言している
- **Kaggleローダー制約**: `exec(code, {})`でロードされるため`__file__`/`__name__`は無い。main.pyの**最後に定義されるcallableがagent**になる
- **ロジックはオフラインで検証してから反映**: 提出は1日5回しかない。evaluate.pyのCIで有意な改善のみ提出

## オフラインの設計

- **評価プロトコル**: 新エージェント vs (旧版・random・first) を各300戦以上、Wilson 95%CI下限が旧版勝率を上回ったら採用
- **自己対戦データ**: `env.steps[0][0]["visualize"]` に両者の全隠れ情報(山札の中身まで)が入る → 模倣・価値学習の教師データはここから採る
- **デッキ最適化(Phase 3)**: デッキ候補の集団を総当たり自己対戦させ、勝率上位を変異(カード入替)させる進化的探索。プレイ方策とデッキは共進化させる
- **学習(Phase 3)**: 特徴量→勝敗の価値回帰から始め、AlphaZero系(方策+価値でMCTSガイド)へ。**推論はKaggle CPU上で高速に動く形式(numpy)でエクスポート**

## データフロー(1手の意思決定、Phase 2)

```
obs → belief更新(logsを消化) → 世界をKサンプル決定化
    → 各候補手を search_begin/search_step で展開 → value評価
    → K世界の平均値が最大の手を選択(時間予算内で反復深化)
    → 予算切れ/例外時: heuristics.py にフォールバック
```
