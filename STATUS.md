# STATUS — 現在の状態と次のアクション

> どのAIエージェント(Claude Code / Codex)も、**作業の開始時にこれを読み、終了時に更新する**。
> 作業中の衝突防止: 大きな作業を始めるときは下の「作業中」欄に記入してcommit+pushする。

最終更新: 2026-07-24 19:25 JST (Codex) — 4引分だけを正常skipする回復protocolを固定中

## ラダー状況(2026-07-23 22:10 JST、active = 最新2提出のみ)

| 提出 | active | 内容 | ライブレート / 公開対戦 |
|---|---|---|---|
| **v4.3a** (sub 54731784) | **yes** | bc_v2 BCS + **canonical Top Alakazam** | **871.7** / 249戦126勝123敗 (50.6%、対戦集計00:10) |
| **v4.2t** (sub 54688865) | **yes** | bc_v2 BCS + Great Tusk–Crustle mill | **699.5** / 204戦101勝103敗 (49.5%、対戦集計00:10) |
| **v4.1a** (sub 54612885) | no | bc_v2 BCS + 旧Alakazam | **869.1 / 149戦79勝70敗 (53.0%)で凍結** |
| **v4.1g** (sub 54601845) | no | BC×探索 + multi-select + bc_v2 + オーロンゲ型 | **751.0 / 93戦で凍結** |
| **v4.0a** (sub 54591345) | no | BC×探索 + bc_v2 + フーディン型 | **826.4 / 67戦** (07-12 23:25 JSTに停止) |

`v4.2t`は204戦で49.5%、現在score 699.5。調査時62戦の28勝は全て相手deckoutだが、34敗は
ポケモン無17/サイド10/自deckout 7。ポケモン無7敗で、ベンチ空・手札に出せるBasicがあるのに
21の重要選択中15回出さず。timeoutではなく、**Great Tuskとbc_v2の分布不整合**が失敗の主因。

`v4.3a`は同bc_v2でデッキのみをcanonical Alakazamへ変更。現在score 871.7。純BC直接 **74.67%/300**、
fixed2 BCS **75.0%/80**、二層meta加重 **88.95% vs baseline 83.23%**。最終production 8秒は
凍結した実提出v4.1aに **8–2/10** (P0 3–2 / P1 5–0)、全戦`DONE`、failure 0、最小残りoverage
**215.99秒**。両席buildを通し、07-16 00:48 JSTに提出、01:01 JSTに`COMPLETE`。早期78戦では
920.7だったが1100には未到達し、現在も旧v4.1a凍結869.1と同格帯。

**G3通過(予定より3週早い)**: v4.0a = BC×探索が純BC(v3.2a)に **58.1%/400戦**(有意)。
本番ラダーで **826.4/67戦** — これまでの平衡750-780を上抜けしたが、v4.1a投入時にinactive化。
v3.1a(779, 旧アクティブ)は最新2提出から外れ最終評価対象外に。凍結: v3.1g=711 / v3.0系=685-689 / 旧世代540-625

中間の敗戦分析(07-12): v3.0gはオーロンゲミラー0/4・対フーディン38%(ローカル94%との乖離=本物の操縦は強い)。
v3.0aの失点源は雑多デッキ相手43%(分布外脆弱性)。→ 対策はBCの質向上(データ倍増+学習強化)

凍結済み: v2.3=543 / v2.1=606 / v1.1=617(全て最終評価対象外)

## 次のアクション(優先順)

1. **07-22 Daily TopからAZ003の独立反例を採掘**: Hammer4 H1はAZ003注入2・探索採用1で、
   総合差もSAFE下限を1勝外した。同じCynthia壁を再抽選せず、top-5外の採用/棄却局面を分け、
   blocker数・Hammer残数・後続KO等から適用guardを狭める。事前登録・監査CLIは`c05bb7c`へ固定済み。
   固定blind rerunは完走したが、勝者のない`[0,0]` 4引分をschema errorへ誤分類してINVALID_RUN。
   旧結果を上書きせず、引分を正常skipへ分ける技術修正だけをcommit後、同一条件を新規pathへ再実行する。
   guard・閾値・29件のcohortは変更しない。十分な独立正例が無ければAZ003はHOLD。
2. **Hammer4 deckとAZ003を分離して保持**: Hammer4自体は純BC54.17%/300、fixed2 52.5%/80、
   Top8のMajkel/Yushinでも再現した。一方Hammer4＋AZ003はH1未通過なので、次のdeck候補へ自動合成しない。
3. **最新Grim壁は次段まで凍結**: Top8のLuca / me and the lads / Rmyを含む6 teamで一致した
   `-2 Handheld Fan / +1 Pokégear 3.0 / +1 Tool Scrapper`型を
   `snapshot_20260723_grim_top8.csv`へ固定し、fixed2壁の両席loaderを通した。H1がINCONCLUSIVEなので
   現AZ003のまま再戦せず、新しいguardを事前固定できた時だけnegative/meta safety wallに使う。
4. **ExItは反証済み介入だけを蒸留**: 凍結10局のTRACE SAFEはExIt source候補だが、
   旧Grimはcoverage 0、Hammer4 H1はpartial coverageでINCONCLUSIVE。`SAFE-MULTI-META`、
   production、提出へは未昇格。
5. **AZ006/AZ008はHOLD**: r46は26/40対H 21/40、r8は26/40対base 18/40でも実注入0。
   Phase 2/production/ExItを停止。AZ006はより広いAZ003へ分解し、AZ008は付属なしDudunsparceの
   top-5外独立正例が5–10件集まるまで再戦しない。
6. **Hammer4をproduction候補として保持**: `-1 Nighttime Mine (1266) / +1 Enhanced Hammer (1081)`は
   純BC同型 **54.17%/300 [48.51–59.72]**、fixed2 BCS **52.5%/80 [41.7–63.1]**。
   最新Top8のMajkel/Yushinも同一60枚で、現環境再現性は上がった。AZ003との組合せH1はINCONCLUSIVE。
7. **ExIt v1を短期設計へ変更**: 59,249判断は健全な3 shardとして保存済み。350,000までの継続は
   実測ペースで長すぎ、探索評価を塞ぐため停止した。夜は既存59kの重み付き混合比を先に固定し、
   追加生成を盲目的に再開しない。次世代から
   root候補に専門家ルールを保証した探索の選択をtrace付きで蒸留する。公式教師との混合を維持し、
   `BC → Expert候補付きBCS → ExIt → 再探索`を1世代ずつA/Bする。
8. **bc_v6 fixed2を負荷解消後に最終判定**: canonical/Hammer純BCの合算は
   **442.5/800 = 55.31%**だがP0 59.0 / P1 51.63%と席差あり。順逆各80戦、candidate換算
   86/160以上・両席/両load-order下限・failure 0の事前gateを、ExIt完了後に最初から回す。
9. **Dunsparce 4枚案を次の低距離techとして準備**: `-1 Nighttime Mine / +1 Dunsparce`。
   公開31敗中7件のポケモン切れを狙うが、ExIt中は組立てまでで重いscreenは行わない。
10. **belief更新は別枝**: Rocket/Festival等のexact library追加は、旧候補との同率時に
   暗默priorが変わる問題を先に解決する。v4.3a提出物には含めない。
11. **ラダー監視**: v4.3a/v4.2tは各249/204戦でほぼ平衡。次の提出は上記gate通過時だけにし、
   Grim/Kang/Alakazam/新規Dragapult・Cynthia・Froslass-Lopunny別の実勝率を追う。

**確定した知見(今セッション)**:
- 07-22固定holdoutのblind rerunは完走したが`episode_schema_errors=4`で **INVALID_RUN**。
  corpus/build/model/除外SHA、policy/rule error 0、privacy/schemaは正常。header集計で4件は全て
  勝者なし`[0,0]`の引分と確認し、残り4,635件には勝者がいる。引分はBC抽出でも除外され、
  AZ003 cohortへ入らないため、次は正常skip counterへ分離する技術修正だけを行う。
- AZ003 Exact-safe独立holdoutを結果確認前に`c05bb7c`へ事前登録。07-22 rawは
  4,639 file/unique、集合SHA `9ff468f2...`、07-15除外は366,457 decision / `66b15e69...`。
  専用bc_v2 audit buildはagent `0ca440e3...` / model `be8146d7...`、両席DONE。
  全Hammer copyのsemantic同値、Exact-safe fail-closed guard、固定入力のscan前後照合、
  aggregate-only schema、gate優先順位を実装し全Unit **92件**通過。初回scanは固定preflight後の
  episode parse中にユーザー指示で停止し、結果JSON/tmp/集計stdoutなし、残存processなし。
- Hammer4共通deckのH1はr4 control **13/20（P0 8/P1 5）**、r34 candidate
  **9/20（6/3）**、差-4（席-2/-2）。全40戦DONE、failure/error/incomplete/watchdog 0、
  最小overage 505.34秒。AZ003はhit31 / outside=injected 2 / injected-selected 1、
  AZ004はhit=enforced=selected 21。総合SAFE下限-3を1勝外し、`injected==injected_selected>=1`も
  未達だがgross REJECT下限には達しないため **INCONCLUSIVE_SCORE_AND_PARTIAL_COVERAGE**。
  同じCynthia壁は再抽選せず、最新Grim/production/提出へ進めない。
- 凍結top-5外10局のlocal介入traceを実装。row SHAでpairsと完全episodeを二重照合し、各局fresh processで
  現行5候補を先に選択、その後だけ元BC top-5＋AZ003の6候補を影評価する。raw観測・非公開札は出力しない。
  gateは実選択passのAZ003＋保持4候補Qを使い、そこで未評価のdrop済みBC #5だけを後段shadow Qで補う。
  修正後3 runは10/10完走・合法注入・audit一致、AZ003採用4/5/4局、strict 4/3/3局、採用局のQ支配0で
  **3/3 TRACE SAFE**。native branch RNGは再現不能で採否/Qは揺れるため、歴史的bit-exact replayとは呼ばない。
  凍結10件の縮小拒否、実`bc_search.decide`との順序/tie-break同値、timeout/target mismatch、
  nested raw・非有限Q拒否、derived gate値のQ配列再計算照合まで含む全Unit **79件**通過。
- TRACE SAFE後の旧07-21 Grim壁はr4 **15/20（P0 8/P1 7）**、r34
  **16/20（8/8）**、差+1（席0/+1）。全40戦DONE、failure/error/incomplete/watchdog 0、
  最小overage 542.93秒。ただしAZ003/004のhit・注入・採用が全て0なので、事前登録どおり
  **INCONCLUSIVE_NO_GRIM_RULE_COVERAGE**。canonical sentinelは省略し、production/提出へ進めない。
- 22:10公式LB snapshotは5,571 team、median 647.6、1000+ 92、1100+ 13、首位1156.9、
  Top8境界1116.6、自チーム454位/871.7。22:25 live値は1100+ 16・Top8 1119.3まで動いたため、
  CSV時刻を固定して扱う。本日提出0/5、activeはv4.3a 871.7 / v4.2t 699.5。
- 最新Top8 replayはGrim 3 / Alakazam 3 / Kang 1 / Dragapult 1。Grim 3者の60枚は配列順まで同一で、
  さらに対戦相手を含む6 teamが同型。新Grim deck SHA `92b92bac...`、fixed2壁SHA `b8a57e37...`。
  Majkel/YushinのAlakazamは既存Hammer4と一致し、Hammer4＋Expert Floorの組合せを次候補にした。
- AZ003+004のexact Cynthia順逆screenは、r34 **46/80（P0 23/P1 23）**、固定r4 control
  **48/80（25/23）**。差-2（席-2/0）は事前許容overall -8・各席-6内。全160戦scored/DONE、
  failure/error/incomplete 0、最小overage 496.41秒。r34累積はAZ003 hit93 / selected30 /
  outside=injected 4 / injected-selected 2、AZ004 hit=enforced=selected 73で、**SAFE-KEEP_TO_MULTI_META**。
  ただし単一proxy壁の局所安全性で、標準160戦昇格・優越性・production・提出の証明ではない。
- Cynthia三群はB 22/40（12/10）、H 21/40（11/10）、C 26/40（15/11）。全120戦DONE、failure 0、
  最小overage 306.59秒以上。HのAZ004はhit=enforced=selected=32、Cは35で直接介入した。
- CのAZ006はhit25 / selected13でも`outside_topk=injected=injected_selected=0`。C–H +5は候補集合差がなく
  ruleへ帰属不能。joint gateはINCONCLUSIVE、逆順なし。Hだけを事後昇格もしない。
- AZ003+004の実行mode監査はAZ003 125 hit / 教師115、top-5外10件を全件注入し**10/10教師一致**。
  広いHammer playはhardにせずsearch候補。r34 fingerprint `5bce6c49...`、両席loader DONE。
- AZ008 Phase 1はbase 18/40、r8 26/40（両席13/20）だが、r8のhit9 / selected4は全てBC top-5内で
  **injected=0 / injected-selected=0**。勝差をruleへ帰属できず事前規則どおりINCONCLUSIVE、Phase 2なし。
- baseのfixed-search incomplete 3件は08:16:05–08:28:00のClamshell Sleep約715秒と、sidecarの
  `game sec - log合計`713.68–713.85秒が一致したfalse hard-stop。各call最大1.368秒、全試合DONE。
  fixed評価だけmonotonic clockへ直しproduction経路を不変とした。全unit **60件**通過。
- 19:29公式LBは5,560 team、median 646.45、1000+ 95、1100+ 9、1200+ 0、首位1182.2、
  Top 8境界1108.9。active scoreはv4.3a 873.6 / v4.2t 699.5。
- 最新上位25 replay / 50枠の選択標本はGrim core 18、canonical Alakazam core 17、Cynthia 5、
  Archaludon–Cinderace 4。現6位junlee789のCynthiaは5 replay同一60枚、闘active＋Rockを3件観測。
  20 unique IDはbc_v2語彙内だが、方策共適応は未証明なのでtargeted proxy壁としてだけ使う。
- r46実行mode再監査はAZ004 162/162教師一致、AZ006 58/58。AZ006はtop-5外5件を全件注入し、
  **5/5教師一致**。監査toolは複数proposal共有2枠・hard bypass・forbidを実行時と同じにし、行SHAも保存。
- base/r4/r46/Cynthia壁を現sourceからbuildしファイルパス両席DONE。fingerprintは順に
  `09e4c497...` / `5c1f74c0...` / `fac34f85...` / `7dad42a2...`。
- AZ008の旧317 hitには、Team Rocket's Articunoの場全体aura等によりHand Power効果が通らない30件が
  混入していた。見えるblockerとCarracostaの特殊Energy条件を実装し、修正後は287 hit / 教師一致247。
  bc_v2 rankは1位200、2位59、3位16、4位8、5位2、6位2で、真の候補注入は2/287だけ。
  以後はhit/selectedではなく`injected`と`injected_selected`を因果的な機構指標にする。
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

## 外部情報スキャン(07-23 22:25 JST)

- 22:10固定CSVは5,571 team、1100+ 13、Top8 1116.6（`results/meta_snapshot_20260723_2210.json`）。
  22:25 liveでは1100+ 16、Top8 1119.3へ動き、単一live値は判断gateに使わない。
  07-22 Daily Top datasetは07-23 09:01 JSTに公開済み。
- 最新Top8の60枚を公式replayで照合し、Grim 3者は新しい同一60枚、Alakazam上位2者は既知Hammer4。
  公開標本の採用率は外挿せず、exact壁・外的再現性としてだけ使う。
- Xで直接確認できた07-15投稿は、短期LBぶれで良い提出を壊さず、単一ログ完全一致でなく同型局面へ
  一般化し、少量変更をログで因果確認する方針。提示された「強者行動を愚直にルール化」の原文自体は
  再取得できず、同一投稿とは扱わない。
- 最新Discussionはrule-based一時2位の自己申告、policy accuracyとLBの非相関、ILのdeck依存、
  弱いvalueでsearchが悪化する経験を報告。巨大if-cascadeを目的化せず、
  `guard→候補保証→Q反証→採用介入だけExIt`を維持する。

## 作業中(衝突防止欄)

- 07-24 19:14 Codex: `c05bb7c`で固定した07-22 AZ003 Exact-safe holdout scanを同一条件で再開。
  `scripts/mine_az003_guard.py`、関連Unit、`results/az003_guard_holdout_20260722_r2.json`、
  `docs/experiments.md`、`docs/plan.md`、`STATUS.md`のみ。guard/rank/gateは変更しない。

## 今日の提出枠

- 07-24: **0/5 使用**（提出なし）
- 07-23: **0/5 使用**（提出なし）
- 07-22: **0/5 使用**（提出なし）
- 07-16: **1/5 使用** (`v4.3a`, sub 54731784, COMPLETE)
- 07-15: 0/5使用
- 07-14: 1/5使用 (`v4.2t`, sub 54688865, COMPLETE)
