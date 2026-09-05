# 全体計画(2026-07-24改訂 / 初版07-10)

> **07-24の現在地**: canonical Alakazam＋BC×探索のv4.3aは249戦・871.7付近へ収束し、模倣だけでは
> 1100の壁を越えられていない。中核は **「専門家ルールを床、探索・ExItを天井」**。
> ルールは強者を丸ごとコピーせず、破滅手の禁止と戦術候補の保証に限定し、探索の比較結果をExItで蒸留する。
> r5は棄却。r8/AZ008とr46/AZ006は勝ち越しても実注入0でINCONCLUSIVEとして停止した。
> AZ003+004はexact Cynthia順逆で実注入4・採用2、r4比-2/80に収まりSAFE-KEEP。
> 凍結10局面はAZ003採用4・Q支配0でTRACE SAFE。旧Grimはr34 16/20対r4 15/20でもrule発火0のため
> multi-metaはINCONCLUSIVEで止めた。Hammer4 H1もr34 9/20対r4 13/20、注入2/採用1で
> score/coverageが部分未達。07-22独立holdoutでもExact-safe 10/13対Broad-only 12/16、
> 一致率差+1.92ptで事前SUPPORT未達。AZ003はHOLDし、Hammer4 deckと分離する。

目標: **Strategy部門トップ8**(各$30,000 + ファイナル進出)。
残り: Simulation締切(8/16)まで23日 / Strategy Writeup締切(9/13)まで51日。

## 前提となる確定事実(公式ページ・実測で裏取り済み)

### コンペ構造
- **Strategy部門の提出物はKaggle Writeup(2000語)のみ**。審査: Model Score 70%(手法+トラック内パフォーマンス)/ Deck Score 20% / Report Score 10%。審査期間9/14〜10/11
- SimulationのLB成績がWriteupの「パフォーマンスの証拠」になる

### ラダー仕様(2026-07-11実測確認)
- 対戦数は無制限(自動で回り続ける)。新提出ほど高頻度(初日35〜60戦)
- ガウスレーティング(μ0=600)。同格マッチング。**レートは平衡値(真の実力)に収束する** — 早期の好成績は持ち越されない
- **最終評価は「最新2提出」のみ**。3番目以降は対戦停止・レート凍結(実測で確認)
- 締切後さらに約2週間対戦してからLB確定 → 締切直前提出でも収束には十分
- レート判定に必要な戦数: **80〜100戦(約2日)**。10戦未満は完全にノイズ

### 環境(昇格帯07-15 / 1100+生存帯07-22 21:43、帯を分離)

| 帯 | Alakazam | Kangaskhan | Grimmsnarl | Lucario | Rocket | Festival | その他/壁 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1000–1099 (標本60) | **58.3%** | 0% | 16.7% | 16.7% | 0% | 0% | 8.3% |
| 1100+ (全17 team、各teamの現公開replay) | 5.9% | 5.9% | **41.2%** | 0% | 11.8% | 0% | 35.3% |

1100+の「その他」6 teamはDragapult 2 / Cynthia Garchomp 2 / Lopunny–Dudunsparce 1 /
Mega Starmie系1。**→ 1100到達にはAlakazam中心の昇格pool、首位争いにはGrim優勢かつ多様化した
生存poolの両方が必要。** まずcanonical Alakazamとexact 07-21 Grimを二層sentinelにし、
Dragapult/Cynthia等はexact snapshotを揃えてから全体重みを再計算する。単一Top12へ過適合しない。

07-23 22:10固定CSVは1100+が13 team、Top8境界1116.6、首位1156.9。22:25 liveでは1100+ 16、
Top8 1119.3まで動いた。現Top8の最新公開replayはGrim 3 / Alakazam 3 / Kang 1 / Dragapult 1。
Grim 3者は配列順まで同じ60枚で、対戦相手を含む6 teamでも同型を確認した。旧07-21型から
`Handheld Fan -2 / Pokégear 3.0 +1 / Tool Scrapper +1`だけ変えたexact wallを固定した。
Alakazam上位2者は既知Hammer4と一致する。公開標本なので採用率へ外挿せず、再現したdeck techとexact壁にだけ使う。

### 確定した技術知見(experiments.md詳細)
- **有効(現主力)**: bc_v2方策＋BC×決定化探索。G3は純BC比58.1%/400で通過し、ラダー826.4。
- **最新再学習は中立**: bc_v5(07-08〜13、195万手、best top-1 63.144%)はbc_v2に53.0%/400
  [48.1–57.8]で有意差なし。productionはbc_v2継続。
- 有効(旧世代・部品として残存): 決定化フラットMC探索 / メタデッキ照合belief / ヒューリスティック(フォールバック)
- 棄却: MCTS(中立)/ 時間予算増強(G1不発: 量でなく質が律速)/ 価値関数v0(LR)/ H4 / 進化的デッキ最適化
- **BCはデッキとセット**: Great Tuskは全カードがbc_v2語彙内で直接A/Bにも勝ったが、公開戦では
  Basic展開を15/21回逃して失速した。語彙内であるだけでは行動分布内を保証せず、デッキ変更と方策改善を分けて測る。
- **専門家ルール監査**: 07-15強者データのcanonical Alakazam 48,501判断で、Hammer対象162/162、
  単独Dudunsparce自滅回避5/5、複数blocker exact-KO 58/58が整合。AZ008はArticuno aura等の
  偽KO 30件を除くと287 hit / 教師一致247 (86.06%)だが、bc_v2 top-5外は2件だけ。一方「進化をすぐ行う」は
  4,131/10,946=37.7%に留まるため、if文は件数でなく条件の証明度と実治療差でhard/candidate/shadowへ分ける。
- **実治療差を勝率より先に判定**: r8はbase比+8、r46はAZ004-only比+5でも対象candidateの注入0で停止。
  r34はAZ004-only固定controlに対し、Cynthia順逆でAZ003を4回注入・2回採用し、46/80対48/80
  （席差-2/0）で局所SAFE-KEEP。AZ003は教師115/125、top-5外10/10教師一致なのでhardではなくsearch候補。
  凍結top-5外10局面は10/10合法・audit一致。修正後3 runはAZ003採用4/5/4、strict 4/3/3、
  採用局Q劣位0で全てTRACE SAFE。gateは現行5候補を実際に選んだpassのAZ003＋保持4候補Qを使い、
  未評価のdrop済みBC #5だけを後段6候補shadow passで補うため、別乱数passで実選択Qを上書きしない。
  公式episodeにnative RNG seedが無く採否/Qは揺れるので、歴史的bit-exact replayとは区別する。
- **multi-metaはcoverageもgate**: 旧Grim共通壁はr34 16/20対r4 15/20、席差0/+1、全件健全だったが
  AZ003/004が一度も発火しなかった。安全性の弱いnegative evidenceにはなるが治療効果を測れていないため、
  事前登録どおりcanonical phaseを省略し`INCONCLUSIVE_NO_GRIM_RULE_COVERAGE`。productionへ昇格しない。
- **deck×ruleの交互作用も分離**: Hammer4共通deckではr4 control 13/20、r34 candidate 9/20、
  席差-2/-2。AZ003はhit31 / injected2 / injected-selected1で治療差は存在したが、総合SAFE下限-3を
  1勝外し、全注入採用条件も未達。健康性は完全、gross REJECTでもないため
  `INCONCLUSIVE_SCORE_AND_PARTIAL_COVERAGE`。Hammer4 deckの外的再現性とAZ003採用可否を混同しない。
- **Exact-safe guardも独立holdoutで未確認**: 07-22のsemantic top-5外29件はExact-safe 10/13
  （76.92%）、Broad-only 12/16（75.00%）、差+1.92pt。事前条件の80%かつ+20ptを満たさず
  `INCONCLUSIVE_GUARD`。AZ009、個別trace、fresh wall、ExItへ進めず、07-22から条件を後付けしない。

## 1100突破の中核: Expert Floor → Search Ceiling → ExIt

1. **Expert Floor**: `forbid`で即敗北手を除外し、証明済み`hard`だけを直接適用する。一般に良さそうな手は
   強制せず`candidate`としてBC top-5のうち最大2枠へ入れる。既存BC top-1はnegative guard時以外必ず残す。
2. **Search Ceiling**: 同じ最大5候補・同じfixed worldsで、ルール候補とBC候補をシミュレータが比較する。
   ルールは探索を置換せず、BCがtop-k外へ落とした独自手を読む権利だけを保証する。
3. **ExIt Ceiling**: 探索の最終選択と候補Qをtraceし、公式強者データと混合して次世代方策へ蒸留する。
   次世代でもExpert Floorを残して再探索し、`BC → BCS → ExIt → BCS`を一世代ずつ改善判定する。
4. **昇格gate**: ルールIDを一つずつshadow→candidate/enforceへ進める。まず対象ruleが
   `BC top-k外へ注入 → searchで選択`された機構指標を共通meta wallで確認する。治療差0の勝率は昇格根拠にしない。
   治療差がある候補だけfixed2順逆160戦で候補換算86/160以上、各席39/80以上、各load-order38/80以上、
   failure/error/invalid 0へ進め、その後に二層meta、production `-j 1`、最終300戦/Wilson下限>50%へ延長する。

## 提出運用ポリシー

- **イベント駆動**(ローカル有意改善 or 本番でしか検証できない仮説があるときのみ)。結果として約2日に1回
- 判定は「両者80戦以上」で。レート±50は同格扱い、実勝率(ladder_stats.py)を併読
  - ※収束調査(scripts/rating_convergence.py)より **40戦で±63・80戦で±48**(逓減が強く40戦で大半収束)。
    別ティア(>100点)の判別は40戦で可、〜50点の接戦のみ80戦+勝率併読が要る
- 僅差の2候補は**同日ペア提出でラダーA/B**(最新2枠が同条件で回る)
- **提出前検証は純BC高速screen→fixed-worlds性能比較→production `-j 1`完走確認**の順で行う。
  単一相手の一騎打ち勝率はラダーレート(多様な相手との平衡)を予測しない=非推移性
- **8/11以降は実験停止。8/14までに検証済み最強2構成で最終2枠を確定**
- 提出前に必ず `.venv/bin/python -m ptcglab.build <name>`(両席ローダー互換検証+tar)

## スケジュール

### 〜7/13(月) — v3.0観測(完了済み: G1判定・MCTS再検証・BC構築・ペア提出)
- [x] G1確定: 時間予算4倍は不発(v2.3=543 < v2.1=606)
- [x] MCTS再検証: 中立 → フラットMC確定
- [x] BCパイプライン構築・学習・**v3.0ペア提出**(オーロンゲ型/フーディン型)
- [x] **ゲートG2'**: Alakazam系が勝者。v4.1a=837.6、Grimmsnarl系v4.1g=740.8。

### 7/14〜7/20 — BC改良サイクル(主力の磨き込み)
- [x] データ拡張: 07-08〜13、195万手でbc_v5を学習。best checkpoint対応も実装
- [x] multi-select対応とBC×探索統合。G3を前倒し通過
- [x] 独自メタ候補4種をscreenし、Great Tusk–Crustleを300戦＋fixed80戦で採用判定
- [x] Expert Rules基盤: 宣言rule、shadow/candidate/enforce、negative guard、root候補注入、metrics、監査tool
- [x] 公式e0717 engineで`v4.5a-floor-fixed2`相当をclean baselineと順逆160戦で判定。
  Floor換算84/160、P1 38/80、TIMEOUT 1で統合版を棄却。次は実発火したr5/r8を分離する
- [x] r5 (sole Dudunsparce guard)を公式engine・順逆160戦で分離。候補換算 **68/160**、
  P0 37/P1 31、探索不完全1で事前REJECT。enforce/production/ExIt floorから外し、r8へ混ぜない
- [ ] v4.2tのラダー収束を観測し、Froslass弱点と長期戦時間を確認

### 7/21〜8/3 — BCを超える(Expert Floor付きExItを主路線にする)
- [x] **路線A: BC×探索の統合** — BCをロールアウト方策にした決定化探索、
  または root-only(BCの上位候補だけを探索で検証)
- [ ] **主路線B': Expert Floor付きExIt** — 第1世代は59,249判断でcheckpoint済み。350kへ盲目的に戻らず、
  r5は棄却、r8/r46は実注入0でHOLD。AZ003+004は最新Cynthia壁で実注入・探索採用と局所安全性を確認した。
  凍結10局面のdecision traceはSAFE、旧Grim勝敗下限も通したがcoverage 0でmulti-metaは未通過。
  Majkel/Yushinで外的再現したHammer4を共通deckにしたH1はscore/coverage部分未達でINCONCLUSIVE。
  07-22 Daily TopのExact-safe独立検証も一致率差+1.92ptでINCONCLUSIVEとなり、AZ003はHOLD。
  同じcorpusから別guardを作らず、変更なしの再確認は次の未開封Daily Topを取得前に事前登録する。
  別ruleは07-22を除外した開発根拠で条件を固定できた場合だけ、未来corpusと最新Top8 Grimへ進める。
  両壁を通った介入だけ公式教師との混合比を事前固定してbc_x1へ入れる。
  第2世代からはrule候補・探索Q・最終選択を同時に記録し、
  hard ruleをラベルへ盲目的に固定せず、探索が採用した行動を蒸留する。世代ごとの改善実測がない限り
  Elo加算を計画値として扱わない。重い場合はGoogle Cloudクーポン($3,000)投入。
- [ ] **独自性の核**: 公開トップのif文を複写するのでなく、自軍の公開敗戦から反例局面を採掘し、
  強者データ整合→シミュレータ反証→ExIt蒸留の三段でルールを育てる。終盤は二層メタに合わせて
  8/11 snapshotからcounter rule/deckを第2枠へ分岐する。
- [x] **ゲートG3**: v4.0aが純BCに58.1%/400で通過。route B value_v1は47.8%/400で棄却

### 8/4〜8/10 — 頑健化と最終構成
- [ ] 時間・例外・未知enum・低速CPUの総点検
- [ ] **ゲートG4 (8/10)**: 最終構成(デッキ+エージェント)フリーズ
- [ ] Writeupのアウトライン作成開始

### 8/11〜8/16(月) — Simulation最終
- [ ] 8/14までに最終2枠を提出(実験的提出は厳禁)
- [ ] 以後は観測のみ。締切後2週間の収束を待つ

### 8/17〜8/31 — Writeup初稿(配点100%がここ)
**言語: 英語で執筆**(規約に明示は無いがKaggle慣例・審査員の可読性から。ユーザーレビュー用に日本語対訳を併走。
8月に公式Discussionで言語指定の有無を再確認)。
構成案(07-12更新: BC転換を物語の軸に):
1. アプローチの進化(探索→「デッキ×プレイヤー共適応」の発見→模倣学習で解決→[RL/統合])— Model 70%
2. 実験の定量記録(アブレーション表・棄却実験含む・レート/勝率推移・BCのマッチアップ表)— experiments.mdから
3. デッキ論(三すくみの定量分析、BC操縦を前提としたデッキ選択の根拠)— Deck 20%
4. 環境分析(レート帯別メタ・収束力学・思考時間分析への言及)— 独自性の主張点
5. 人間協働(リプレイレビュー→仮説→機構指標での検証、日本語ビューアの開発)— 独自性
6. 図表(アーキテクチャ図・帯別遭遇率・総当たり表)— Report 10%

### 9/1〜9/13(日) — Writeup最終化
- [ ] 2000語制限の厳守、Track選択、**9/10までにWeb UIから提出**(下書き放置は審査対象外)
- [ ] 添付アセット整理(非公開リソースは締切後自動公開に注意)

## 定常ルーチン

| 頻度 | 作業 |
|---|---|
| 毎朝 | `ladder_stats.py` + `submissions`で成績確認 → versions.md更新(観測日付き) |
| 提出時 | `ptcglab.build`検証 → 提出 → COMPLETE確認 → versions.md/experiments.md追記 |
| 週次(月) | meta_scrape.py + band_meta.pyでメタ再収集 / **最新のDaily Top EpisodesでBC再学習判断** |
| 週次 | 本計画のゲート判定・改訂 |

## リスクと対策(07-12改訂)

- **BCの天井 = 模倣元の強さ**: 模倣だけでは首位を狙う独自性がない → Expert Floorで未学習の戦術候補を保証し、
  simulator searchで反証可能にし、採用された手だけをExItで方策へ戻す
- **模倣元のメタ固定**: production bc_v2は07-01〜10。bc_v5(07-08〜13)は有意改善なし →
  単純な最新化は自動採用せず、同一デッキ400戦A/Bを通す
- **BCの分布外脆弱性**: 訓練で見ない局面(珍しいデッキ・終盤の異常盤面)で誤る → negative guard＋
  ヒューリスティックフォールバックを維持し、敗戦リプレイからrule ID単位で穴を監視
- **if文の過適合**: 強者一致率が高くても因果を保証しない → hardは破滅回避/対象選択など局所支配手だけ。
  candidateは必ず探索とA/Bに通し、低一致ルールはshadowから動かさない
- **最新2枠の事故**(良提出の押し出し): 提出はイベント駆動+この計画のゲートに従う
- **メタシフト**: 週次収集で追随。旧07-21 Grimだけを固定せず、07-23 Top8で6 teamに再現した
  Pokégear＋Tool Scrapper型 `snapshot_20260723_grim_top8.csv`を最新wallにする
- **測定の交絡**: 重負荷ジョブと時間依存評価の並走禁止。BC同士の評価は高速なので影響小
- **公式engine drift**: PyPI版とKaggle配布native binaryの更新日は一致しないことがある →
  search評価・build前に`scripts/sync_cg_engine.py`をread-only実行し、差分時だけ`--apply`後に全buildを作り直す
- **提出事故**: 500エラー/認証失効の経験あり → 最終提出は8/14までのバッファ運用

## Strategy Writeup 計画(2026-09-05 更新、締切 09-13 23:59 UTC = 09-14 08:59 JST)

ルールと配点は docs/writeup-rules.md。言語は英語、ユーザーレビュー用に日本語対訳を併作。
リポジトリは公開(MIT、LICENSE追加済み)。Kaggle Web UIでの作成・添付・Submitは**APIに無い**ので
ユーザーが行う(こちらはMarkdown本文・図・デッキCSVを `docs/writeup/` に用意する)。

| 日 | 作業 |
|---|---|
| 09-05〜06 | 素材確定: 最終2提出の対面別勝率(`scripts/replay_fetch_slow.py`で取得中)、図8点の生成、英語アウトラインと語数配分 |
| 09-07〜08 | 英語初稿(≤1,950語)+日本語対訳 → ユーザーレビュー |
| 09-09 | 図の最終化・語数調整・デッキリスト画像/CSV |
| 09-10 | Kaggle Web UIでWriteup作成・Media Gallery添付・Track選択・保存(ユーザー) |
| **09-11** | **Submit(締切2日前をバッファ)**。以後は誤字修正のみ、Submitted状態を維持 |

構成(本文≈1,950語): 1 Summary 150 / 2 Problem framing 200 / 3 Approach evolution 500 /
4 Consistency & robustness evidence 400 / 5 Deck concept 350 / 6 What we'd do differently 200 /
7 Reproducibility 150。図: 収束曲線・対面別ヒートマップ・LB分布・探索A/B・データ日数×holdout表・
判断カスケード図・メタ時系列・デッキリスト。画像は自作グラフと公式ビジュアライザのスクショのみ。
