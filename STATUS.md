# STATUS — 現在の状態と次のアクション

> どのAIエージェント(Claude Code / Codex)も、**作業の開始時にこれを読み、終了時に更新する**。
> 作業中の衝突防止: 大きな作業を始めるときは下の「作業中」欄に記入してcommit+pushする。

最終更新: 2026-07-23 00:15 JST (Codex) — AZ005単独gateをREJECT、深夜ラダーを再確認

## ラダー状況(2026-07-23 00:10 JST、active = 最新2提出のみ)

| 提出 | active | 内容 | ライブレート / 公開対戦 |
|---|---|---|---|
| **v4.3a** (sub 54731784) | **yes** | bc_v2 BCS + **canonical Top Alakazam** | **862.8 / 249戦126勝123敗 (50.6%)** |
| **v4.2t** (sub 54688865) | **yes** | bc_v2 BCS + Great Tusk–Crustle mill | **708.6 / 204戦101勝103敗 (49.5%)** |
| **v4.1a** (sub 54612885) | no | bc_v2 BCS + 旧Alakazam | **869.1 / 149戦79勝70敗 (53.0%)で凍結** |
| **v4.1g** (sub 54601845) | no | BC×探索 + multi-select + bc_v2 + オーロンゲ型 | **751.0 / 93戦で凍結** |
| **v4.0a** (sub 54591345) | no | BC×探索 + bc_v2 + フーディン型 | **826.4 / 67戦** (07-12 23:25 JSTに停止) |

`v4.2t`は204戦で708.6へ収束。調査時62戦の28勝は全て相手deckoutだが、34敗は
ポケモン無17/サイド10/自deckout 7。ポケモン無7敗で、ベンチ空・手札に出せるBasicがあるのに
21の重要選択中15回出さず。timeoutではなく、**Great Tuskとbc_v2の分布不整合**が失敗の主因。

`v4.3a`は同bc_v2でデッキのみをcanonical Alakazamへ変更。純BC直接 **74.67%/300**、
fixed2 BCS **75.0%/80**、二層meta加重 **88.95% vs baseline 83.23%**。最終production 8秒は
凍結した実提出v4.1aに **8–2/10** (P0 3–2 / P1 5–0)、全戦`DONE`、failure 0、最小残りoverage
**215.99秒**。両席buildを通し、07-16 00:48 JSTに提出、01:01 JSTに`COMPLETE`。早期78戦では
920.7だったが、249戦で862.8へ収束。旧v4.1aの凍結869.1も下回り、1100には未到達。

**G3通過(予定より3週早い)**: v4.0a = BC×探索が純BC(v3.2a)に **58.1%/400戦**(有意)。
本番ラダーで **826.4/67戦** — これまでの平衡750-780を上抜けしたが、v4.1a投入時にinactive化。
v3.1a(779, 旧アクティブ)は最新2提出から外れ最終評価対象外に。凍結: v3.1g=711 / v3.0系=685-689 / 旧世代540-625

中間の敗戦分析(07-12): v3.0gはオーロンゲミラー0/4・対フーディン38%(ローカル94%との乖離=本物の操縦は強い)。
v3.0aの失点源は雑多デッキ相手43%(分布外脆弱性)。→ 対策はBCの質向上(データ倍増+学習強化)

凍結済み: v2.3=543 / v2.1=606 / v1.1=617(全て最終評価対象外)

## 次のアクション(優先順)

1. **AZ008を単独gateへ**: 統合Floor 84/160に続き、`r5` (sole Dudunsparce guard)も
   **68/160、P0 37/P1 31、探索不完全1**で事前REJECT。enforce/production/ExIt floorから外した。
   次は探索不完全のstage/context metricを追加してから、`r8` (draw-to-KO)だけを標準86/160 gateで測る。
   r5や統合Floorの戦績を混ぜず、途中結果にかかわらず順逆を完走する。
2. **最新Grimを主要meta wallへ追加**: 21:43の1100+ 17 teamでは41.2%、トップ3もGrim。
   最多60枚を`snapshot_20260721_grim_canonical.csv`へ固定済み。r8がcanonical gateを通った時だけ、
   exact deck＋bc_v2 BCS proxyを共通壁にしたbase/candidate各40戦へ進む。
3. **Hammer4をproduction候補として保持**: `-1 Nighttime Mine (1266) / +1 Enhanced Hammer (1081)`は
   純BC同型 **54.17%/300 [48.51–59.72]**、fixed2 BCS **52.5%/80 [41.7–63.1]**。
   現1100+の`aaa`も同一60枚で、現環境再現性は上がった。ただしExpert Floorとの組合せは未評価。
4. **ExIt v1を短期設計へ変更**: 59,249判断は健全な3 shardとして保存済み。350,000までの継続は
   実測ペースで長すぎ、探索評価を塞ぐため停止した。夜は既存59kの重み付き混合比を先に固定し、
   追加生成を盲目的に再開しない。次世代から
   root候補に専門家ルールを保証した探索の選択をtrace付きで蒸留する。公式教師との混合を維持し、
   `BC → Expert候補付きBCS → ExIt → 再探索`を1世代ずつA/Bする。
5. **bc_v6 fixed2を負荷解消後に最終判定**: canonical/Hammer純BCの合算は
   **442.5/800 = 55.31%**だがP0 59.0 / P1 51.63%と席差あり。順逆各80戦、candidate換算
   86/160以上・両席/両load-order下限・failure 0の事前gateを、ExIt完了後に最初から回す。
6. **Dunsparce 4枚案を次の低距離techとして準備**: `-1 Nighttime Mine / +1 Dunsparce`。
   公開31敗中7件のポケモン切れを狙うが、ExIt中は組立てまでで重いscreenは行わない。
7. **belief更新は別枝**: Rocket/Festival等のexact library追加は、旧候補との同率時に
   暗默priorが変わる問題を先に解決する。v4.3a提出物には含めない。
8. **ラダー監視**: v4.3a/v4.2tは各249/204戦でほぼ平衡。次の提出は上記gate通過時だけにし、
   Grim/Kang/Alakazam/新規Dragapult・Cynthia・Froslass-Lopunny別の実勝率を追う。

**確定した知見(今セッション)**:
- AZ005単独gateはr5換算 **68/160=42.5%**、load-order 35/33、P0 37/P1 31で、
  事前REJECT条件69以下。hit9/blocked2、全160 scored/DONE、最小overage 564.24秒。
  forwardの`fixed_search_incomplete` 1件はsidecarでrollout系へ絞ったがrule因果未確定。
  性能条件だけでREJECTが成立するため再試験せず、次のr8へ混ぜない。
- 00:10公式LBは5,521 team、median 647.2、1000+ 95、1100+ 18、1200+ 0、
  top-8境界1120.5、首位1194.1、自チーム493位/862.8。21:43に分類済みの17 teamは
  Grim 41.2%（トップ3全て）、Rocket/Dragapult/Cynthia各11.8%。新規18番目は未分類。
- 公式native engineはPyPI最新版とは別に更新されていた。Team Rocket Energyのindex bug修正版4 binaryを
  `src/cg`へ同期し、`scripts/sync_cg_engine.py`の実動checkで4/4 `MATCH`。e0717 buildは両席`DONE`。
- Expert Floor統合正式gateは **84/160=52.5%**、load-order 42/80ずつ、P0 46/P1 38、
  TIMEOUT 1。総合86・各席39・failure 0の3条件を外したため棄却。AZ005 hit13/blocked4、
  AZ008 hit35/selected25、他ruleはcanonical mirrorで発火0。分離したr5もREJECTとなり、次はr8単独。
- arena failure診断を追加。今後はpair/game identityとfailure-only replay/log sidecarを残し、同一gauntlet
  run内も`invocation_id`で衝突しない。native seedは取得不能のため完全再実行ではなく事後診断用。
  unit 44件＋意図的ERRORの実process 2戦でsidecar/SHA/raw非漏洩を確認。
- 07-22 19:16時点の1100+全13 teamはGrim 38.5%、Alakazam/Kang各15.4%、Rocket/Dragapult/Cynthia/
  Froslass-Lopunny各7.7%、Festival 0。Grim 10/11は同一18-Pokémon coreで、最多型6/11を保存した。
- activeは00:10再確認でv4.3a **862.8/249戦**、v4.2t **708.6/204戦**。19:16時点のLBは5,497 team、
  median 647.1、1000+ 90、1100+ 13、top-8境界1126.0、自チーム402位。
- ExIt v1は **59,249/350,000判断 (16.93%)**、3 shard。全gzip/JSON/必須key/deck60が正常、
  `.tmp`/`.broken`なし。新規200試合は15,175判断（75.875/試合）。6 workerは健全だったが、
  スリープ込みでは完走約12日となるためcheckpoint停止し、全CPUを解放した。
- `v4.5a-base-fixed2`（Expert code no-op）と`v4.5a-floor-fixed2`を同一source/model/deckから組み、
  ファイルパスロードを**両席DONE**で検証。旧ExIt teacher buildは上書きしていない。
- **Expert Rulesを床、探索・ExItを天井にする基盤を実装**。`shadow/candidate/enforce`、
  rule ID単位ablation、BC top-1を残した最大2候補注入（総数5のまま）、hard/negative guard、
  実行時フォールバック、arenaのrule metrics集約まで追加。既存agentは設定なしでno-op、unit 36件通過。
- 07-15強者データのcanonical Alakazam **48,501判断**を監査。`AZ004` Hammer対象162/162、
  `AZ005`単独Dudunsparce自滅回避5/5、`AZ006`複数blocker exact-KO 58/58、
  `AZ007`山札0 Sacred Ash 1/1が整合。`AZ008`draw-to-KOは252/317=79.5%、
  `AZ003`Hammer playは115/125=92.0%なので探索候補。進化即実行`AZ002`は37.7%のためshadow専用。
- Rock Fighting Energyは**闘Pokemonに付いた時だけ**Hand Powerを防ぐ。Great Tusk+Rockはblocker、
  Crustle+Rockは非blockerとしてmetadata判定と回帰testを追加した。
- bc_v6 recent8はcanonical 56.37%/400、Hammer4 54.25%/400、合算55.31%/800だが、
  P0 59.0 / P1 51.63%の席差がある。fixed2は順逆160戦の事前gateを負荷解消後に再実行する。
- arena fresh-pairをProcess＋Pipe watchdog化。timeout/crashはschema互換failureとして台帳へ残し、
  payload後の終了hangは強制回収する。unit 19件＋実process 2戦がfailure 0で完走。
- 公開31敗のうちポケモン切れ7敗を狙うDunsparce4（Mine3→2 / Dunsparce3→4）を組立て、
  60枚差分と両席buildを検証済み。性能測定はExIt終了後。
- 07-15時点のメタは二層。1000–1099帯はAlakazam 58.3%、1100+全14チームはKang 28.6 / Alakazam 21.4 /
  Grim 21.4 / Rocket 14.3 / Festival 14.3%。昇格poolと1100+生存poolを分けて評価する。
- v4.2tの失敗はデッキ単体ではなくBCとの共適応不足。canonical Alakazamの7枚差は
  純BC/fixed2/gauntlet/productionの4種で一貫して優位。
- arena schema v2に全体・席別の最小`remainingOverageTime`を追加。production 10戦の候補最小は
  215.99秒で、本番時間安全性を自動gate化できた。
- 公式Top12最新6件(重複除外66 replay/132枠): Alakazam 47.7%、Kangaskhan–Crustle 25.8%、
  Froslass–Starmie 5.3%、Lucario 0.8%。X情報は仮説、公式episodesを判断の主根拠にした
- Great Tusk純BCは現行Alakazamに **62.0%/300 [56.4–67.3]**、fixed2 BCSは
  **61.25%/80 [50.3–71.2]**。v4.2tとして採用・提出し、v4.1gを置換
- arena schema v2を導入: 席均衡、fresh process、strict failure、fingerprint、production `-j 1`、
  fixed-worldsの壁時計分離、gauntlet ledger。9件の回帰テストが通過
- bc_v5(07-08〜13、195万手)はbc_v2に **53.0%/400 [48.1–57.8]**で有意差なし、bc_v2継続
- v4.1g(オーロンゲ)失敗=**一騎打ちA/Bはラダー非予測**。提出前はガントレット+本番予算で
- **search系のwall-clock A/BはCPU負荷に敏感** — 単一クリーン実行 or compute固定で測る
- route B価値網は2.26M行でもAUC **0.851**、クリーンA/B **47.8%/400**で現形棄却。
  `models/value_v1`へ退避し、実行時はフルロールアウトへフォールバック
- Kaggleは目標48試合/日、各マッチ10%でランダム相手。短期レート/順位には対面運が残る

## 外部情報スキャン(07-22 19:16–07-23 00:10 JST)

- 00:10 Leaderboardは5,521 team、median 647.2、1000+ 95、1100+ 18、1200+ 0、top-8境界1120.5。
  最新Daily Topは07-21版4,612 episodesで、07-22版は未公開。21:43時点の1100+全17 teamを分類したが、
  00:10に増えた1 teamはreplay取得停止のため未分類とし、比率へ推測で混ぜない。
- Discussion 728071の模倣学習21–22k replayで1088帯という報告は短期ExIt設計を支持するが、参加者自己申告。
  728068のNinetales #660 × Amarys #1207 SIGSEGVはhost未回答のため当面その組合せを避ける。
- X通常検索ではユーザー提示投稿の完全一致原文や新しい具体的if-cascadeを取得できず、
  「存在しない」とは断定しない。採用根拠はKaggle公式Leaderboard / episodes / replayとlocal A/B。

## 作業中(衝突防止欄)

- **Codex (2026-07-23 00:18 JST)**: `AZ008_DRAW_TO_EXACT_KO`単独の公式e0717 fixed2 gateを準備する。
  r5/統合Floorの結果は混ぜない。先に`FixedSearchIncomplete`へworld begin / candidate step / rollout /
  hard-stopとactive rule contextの診断metricを追加し、AZ008の境界fixtureを監査する。unit・同一sourceからの
  base/r8再build・両席loader・fingerprint/config-only差を確認後、標準gate（86/160、各席39、
  各load-order38、全failure/error/incomplete/invalid/conflict/violation 0、最小overage60秒）を結果前に固定する。

## 今日の提出枠

- 07-23: **0/5 使用**（提出なし）
- 07-22: **0/5 使用**（提出なし）
- 07-16: **1/5 使用** (`v4.3a`, sub 54731784, COMPLETE)
- 07-15: 0/5使用
- 07-14: 1/5使用 (`v4.2t`, sub 54688865, COMPLETE)
