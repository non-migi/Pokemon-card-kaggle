# STATUS — 現在の状態と次のアクション

> どのAIエージェント(Claude Code / Codex)も、**作業の開始時にこれを読み、終了時に更新する**。
> 作業中の衝突防止: 大きな作業を始めるときは下の「作業中」欄に記入してcommit+pushする。

最終更新: 2026-07-16 21:10 JST (Codex) — arena watchdog完了、bc_v6/Duns4はExIt負荷解消待ち

## ラダー状況(2026-07-16 19:32 JST、active = 最新2提出のみ)

| 提出 | active | 内容 | ライブレート / 公開対戦 |
|---|---|---|---|
| **v4.3a** (sub 54731784) | **yes** | bc_v2 BCS + **canonical Top Alakazam** | **920.7 / 78戦47勝31敗 (60.3%)** |
| **v4.2t** (sub 54688865) | **yes** | bc_v2 BCS + Great Tusk–Crustle mill | **725.3 / 86戦44勝42敗 (51.2%)** |
| **v4.1a** (sub 54612885) | no | bc_v2 BCS + 旧Alakazam | **869.1 / 149戦79勝70敗 (53.0%)で凍結** |
| **v4.1g** (sub 54601845) | no | BC×探索 + multi-select + bc_v2 + オーロンゲ型 | **751.0 / 93戦で凍結** |
| **v4.0a** (sub 54591345) | no | BC×探索 + bc_v2 + フーディン型 | **826.4 / 67戦** (07-12 23:25 JSTに停止) |

`v4.2t`は68戦で平衡709.9へ低下。調査時62戦の28勝は全て相手deckoutだが、34敗は
ポケモン無17/サイド10/自deckout 7。ポケモン無7敗で、ベンチ空・手札に出せるBasicがあるのに
21の重要選択中15回出さず。timeoutではなく、**Great Tuskとbc_v2の分布不整合**が失敗の主因。

`v4.3a`は同bc_v2でデッキのみをcanonical Alakazamへ変更。純BC直接 **74.67%/300**、
fixed2 BCS **75.0%/80**、二層meta加重 **88.95% vs baseline 83.23%**。最終production 8秒は
凍結した実提出v4.1aに **8–2/10** (P0 3–2 / P1 5–0)、全戦`DONE`、failure 0、最小残りoverage
**215.99秒**。両席buildを通し、07-16 00:48 JSTに提出、01:01 JSTに`COMPLETE`。19:32時点で
78戦47勝31敗・920.7まで上昇し、旧v4.1aを+51.6上回ったが1100には未到達。

**G3通過(予定より3週早い)**: v4.0a = BC×探索が純BC(v3.2a)に **58.1%/400戦**(有意)。
本番ラダーで **826.4/67戦** — これまでの平衡750-780を上抜けしたが、v4.1a投入時にinactive化。
v3.1a(779, 旧アクティブ)は最新2提出から外れ最終評価対象外に。凍結: v3.1g=711 / v3.0系=685-689 / 旧世代540-625

中間の敗戦分析(07-12): v3.0gはオーロンゲミラー0/4・対フーディン38%(ローカル94%との乖離=本物の操縦は強い)。
v3.0aの失点源は雑多デッキ相手43%(分布外脆弱性)。→ 対策はBCの質向上(データ倍増+学習強化)

凍結済み: v2.3=543 / v2.1=606 / v1.1=617(全て最終評価対象外)

## 次のアクション(優先順)

1. **bc_v6 fixed2を負荷解消後に最終判定**: canonical/Hammer純BCの合算は
   **442.5/800 = 55.31%**だがP0 59.0 / P1 51.63%と席差あり。順逆各80戦、candidate換算
   86/160以上・両席/両load-order下限・failure 0の事前gateを、ExIt完了後に最初から回す。
2. **Hammer4をproduction候補として保持**: `-1 Nighttime Mine (1266) / +1 Enhanced Hammer (1081)`は
   純BC同型 **54.17%/300 [48.51–59.72]**、fixed2 BCS **52.5%/80 [41.7–63.1]**
   (P0 23/40 / P1 19/40、failure 0)。ただし公開31敗中17敗は特殊energy 0で、1100突破の本命ではない。
3. **Dunsparce 4枚案を次の低距離techとして準備**: `-1 Nighttime Mine / +1 Dunsparce`。
   公開31敗中7件のポケモン切れを狙うが、ExIt中は組立てまでで重いscreenは行わない。
4. **belief更新は別枝**: Rocket/Festival等のexact library追加は、旧候補との同率時に
   暗默priorが変わる問題を先に解決する。v4.3a提出物には含めない。
5. **ラダー監視**: v4.3aは1100確約ではなく、874.4基準のElo中心は約1065–1070。
   投入後はRocket/Kang/Grim/Festival別の実勝率と収束レートを追う。

**確定した知見(今セッション)**:
- bc_v6 recent8はcanonical 56.37%/400、Hammer4 54.25%/400、合算55.31%/800だが、
  P0 59.0 / P1 51.63%の席差がある。fixed2は順逆160戦の事前gateを負荷解消後に再実行する。
- arena fresh-pairをProcess＋Pipe watchdog化。timeout/crashはschema互換failureとして台帳へ残し、
  payload後の終了hangは強制回収する。unit 19件＋実process 2戦がfailure 0で完走。
- 公開31敗のうちポケモン切れ7敗を狙うDunsparce4（Mine3→2 / Dunsparce3→4）を組立て、
  60枚差分と両席buildを検証済み。性能測定はExIt終了後。
- メタは二層。1000–1099帯はAlakazam 58.3%、1100+全14チームはKang 28.6 / Alakazam 21.4 /
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

## 外部情報スキャン(07-16 20:40 JST)

- Leaderboardは5,120チーム、median 659.3、1000+ 89、1100+ 17、1200+ 3、top-8境界1156.8。
  07-15 Daily Top 4,825 episodesはbc_v6へ取込済み。07-16版は未公開。
- 公式DiscussionのRL/search手法は参考にするが、自己申告とreplayからの推測を分離する。
- Xは通常検索で新しい検証可能情報を取得できず、署名済みbrowser sessionもunavailableだった。
  今回はKaggle公式Leaderboard/episodes/replayだけを採用根拠にした。

## 作業中(衝突防止欄)

- Codex: **Expert Rules基盤** — canonical Alakazam向けの宣言的ルール層、BC top-k外の
  候補注入、発火/shadow計測、回帰テストを担当。進行中ExItには触れず、重いarenaは完了後に実施
- Codex: arena watchdog/Dunsparce4組立て完了。bc_v6 fixed2順逆160戦とDuns4 screenはExIt完了後
- Claude Code: **ExIt(探索の蒸留、1200戦略レバー1)** — v4.3a-fixed2同士の自己対戦から
  探索エージェントの決定を収集(scripts/exit_gen.py)→ **bc_x1** を学習(bc_v6と名前分離)。
  **生成ジョブ実行中(07-16開始、4500試合≈35万決定、-j6、~19h、→ data/bc/exit_pairs_v1.jsonl.gz)**。
  **production `-j1` wall-clock確認とは並走不可**(fixed-worlds gateは併走OK)。
  bc_x1の学習方針: 公式10日分(bc_v2と同一)+ExItミラー混合(ミラー単独は分布外崩壊のためNG)。
  deck tech/Hammer4/belief/bc_v6には触れない。
  ⚠️発見: cgネイティブは**同一パスの2回ロードでC++クラッシュ**(buffer full. capacity:7)。
  ミラー自己対戦は別パスコピーからロードする(exit_gen.py参照)

## 今日の提出枠

- 07-16: **1/5 使用** (`v4.3a`, sub 54731784, COMPLETE)
- 07-15: 0/5使用
- 07-14: 1/5使用 (`v4.2t`, sub 54688865, COMPLETE)
