# コミュニティ調査ノート(2026-07-12)

Kaggleディスカッション・note/X・Qiitaを横断調査。他の参加者の方向性と、うちが見落としていた資源。

## 1. フィールドの構成(30,000試合の思考時間分析より — Abhyuday氏の投稿)

思考時間の指紋(起動時間×1手あたり時間)からエージェント種別を推定した分析が公開されている:

- **フィールドの約半分はルールベース**(手書き or 公開サンプルのコピー)。1手0.03秒で即応
- 数秒考える探索系は少数派(うちはここ)
- **首位は「重いモデルをロード+持ち時間をフル活用」= RL+有界探索と推定**。それ以外のトップ勢は探索なし(高速NN or ルール)
- 含意: うちの「探索+時間活用」は方向としてトップと同型。足りないのは**学習されたモデル**

## 2. RL勢のスレッドから得た実践知(38コメントの活発なスレ)

- 純RL勢が複数、silver〜1000ELO帯に到達(Aji Samudra: 170万パラメータ、Jake: Archaludonデッキで約1000)
- **共通の教訓**:
  - 盤面表現(観測エンコーディング)が最重要
  - **ユニークカード250種でLBの95%のゲームをカバーできる**(全1267種を扱う必要なし)
  - 公式エンジンバイナリのままで単一GPUで7k steps/sec — 再実装不要
  - ローカル評価プールが弱いとLBとの乖離が起きる(← うちと同じ問題を全員が踏んでいる)
  - 自己対戦+カリキュラムで機能。BC(模倣学習)+RL+探索の組み合わせ勢も存在
- RLの停滞例も多い(700-800で頭打ち→表現やデッキプール見直しでブレイクスルー)

## 3. 見落としていた公式資源(最重要)

- **公式「Daily Top Episodes Dataset」**: レート上位のエピソードを毎日データセット化して公開
  (kaggle.com/datasets/kaggle/pokemon-tcg-ai-battle-episodes-index)。**トップ勢のプレイの教師データが公式に毎日供給されている** — 模倣学習(BC)の即戦力。うちの手動スクレイピングの上位互換
- 6/30にシミュレータ更新あり(ステップ上限による引き分け→ループ側の時間切れ負けに変更)。環境は動く前提で追随が必要
- 「公式ルールとシミュレータの差異」スレ(17コメント)— ルール細部の罠に注意

## 4. 戦術・運用の知見

- Yohei Nakajima氏のポストモーテム: 「AI自動化だけで回した結果、公開された強い方策のコピーに勝てなかった」
  — 提出枠と24時間の収束待ちが実験速度を縛る、ローカル対戦相手の不完全さが結論を狂わせる(全てうちの経験と一致)
- ボスの指令/ハイパーボールの使い方はコミュニティでも未解決の難所(サポート運用が難しいのは共通認識)
- 先攻/後攻の統計スレ: 選択権を持つ側は圧倒的に先攻を選ぶ
- 日本語圏(note/Qiita)は入門記事が中心。ポケカプレイヤー視点の知見:「**AI専用デッキを作り探索空間を絞るのが重要**」(=デッキ×プレイヤー共適応、うちの結論と同じ)

## 5. うちへの含意(優先度変更)

1. **BCパイプラインを最優先に格上げ**: 公式トップエピソードデータセット→(obs, 行動)ペア抽出→方策ネット学習。
   トップ勢のフーディン操縦をそのまま学べる = 「強いデッキを操縦できない」問題の最短解
2. **デッキ乗り換え候補にオーロンゲ型**(2026-07-12ローカル検証): うちの探索AI操縦で対フーディン94%
   (サンプルデッキは72-76%)。弱点の対エネ物量デッキは850+帯にほぼ生息しないため無視できる
3. 表現設計は250カードで足りる(全カード対応を目指さない)
4. ペア提出でデッキA/B(オーロンゲ vs V3サンプル、同一エージェント)が次の提出の本命

## 6. 2026-07-16 20:40 JST 更新

- Kaggle公式Leaderboard CSV（取得時刻2026-07-16 20:40 JST）は **5,120 teams**、median 659.3。
  1000+は89、1100+は17、1200+は3。首位1267.2、Strategy top-8 cutoffは1156.8。
  ライブ値なので、短時間でも閾値人数は上下する。
  <https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/leaderboard>
- 07-15 Daily Top Episodesは公開済みで **4,825 episodes**。そこから369,083 decisionsを抽出し、
  07-08〜15の直近8日窓でbc_v6を学習した。07-16版は20:40時点でKaggle API検索に存在しない。
  <https://www.kaggle.com/datasets/kaggle/pokemon-tcg-ai-battle-episodes-2026-07-15>
  / <https://www.kaggle.com/datasets/kaggle/pokemon-tcg-ai-battle-episodes-index>
- 公式Discussionの「Alakazamが0 damage」例は、Rock Fighting Energyのattack effect遮断で説明され、
  シミュレータ不具合の証拠ではなかった。Enhanced Hammerはこの局面への直接回答だが、v4.3aの公開31敗中
  17敗は特殊energy 0だったため、主力全体の改善とはみなさない。
  <https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/726485>
- 上位submissionのepisode割当頻度に差があるという参加者報告が出たが、host確認前の観測値であり、
  ラダー仕様の確定事実にはしない。
  <https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/726690>
- Xは通常検索・ドメイン指定検索とも、当日メタを裏付ける検証可能な投稿を取得できなかった。
  「投稿がない」とは推論せず、今回もKaggle公式CSV / dataset / replayを採用判断の主根拠にする。

## 7. 2026-07-22 更新

- 19:16の公式Leaderboardは5,497 teams、median 647.1、1000+ 90、1100+ 13、top-8 cutoff 1126.0。
  前回より全体にratingが圧縮され、21:20再確認ではv4.3a 873.1（244戦）、v4.2t 712.2（203戦）。
  <https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/leaderboard>
- 最新07-21 Daily Top 4,612 episodesと07-22公開replayで1100+全13 teamを同定。Grim 38.5%、
  Alakazam/Kang各15.4%、Rocket/Dragapult/Cynthia Garchomp/Froslass–Mega Lopunny各7.7%、Festival 0。
  Grimは11 team中10 teamが同じ18-Pokémon coreで、最多型は07-15 bono型から
  `Aoki's Search -1 / Hikari +1`だけ。最新meta wallとして保存した。
  <https://www.kaggle.com/datasets/kaggle/pokemon-tcg-ai-battle-episodes-2026-07-21>
- Tony Li氏らは約21–22k replayのpure imitation learningで1088帯へ到達し、同一checkpointでもdeck差が
  大きいと報告。少量高品質ILとdeck共適応の価値を支持するが、学習詳細・計算量は参加者自己申告である。
  <https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/728071>
- host説明では約4分ごとのmatchmaking、rating/sigma/経過時間/新しさでpriorityを調整し、rating差だけで
  最大約8倍、10% random、全submit最低48 games/dayを期待。最終評価でも新episodeを生成する。
  未回答の公平性質問が残るため、public ladderの単発A/Bよりlocal multi-meta leagueを主証拠にする。
  <https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/726690>
- 公式native engineはPyPI 1.32.0とは独立に更新され、Team Rocket Energyのshadowed index bugが修正された。
  competition dataのnative binaryと毎回SHA比較する。別件のNinetales #660 × Amarys #1207 SIGSEGV報告は
  host未回答なので、当面その組合せを候補deckから除外する。
  <https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/727094>
  / <https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/728068>
- Xではユーザー提示の「強者行動をルールベース化」投稿の完全一致原文や、その後の具体的if-cascadeを
  再取得できなかった。方向性はExpert Floorへ反映済みだが、個々のrule採否は公式強者decision監査と
  順逆local A/Bで決める。

## 8. 2026-07-23 00:10 JST 更新

- Kaggle公式Leaderboard CSV（snapshot `2026-07-22T15:10:10Z`）は **5,521 teams**、median 647.2、
  1000+ 95、1100+ 18、1200+ 0、top-8 cutoff 1120.5、leader 1194.1。自チームは
  **493位 / 862.8**で、1100まで237.2、top-8まで257.7の差がある。
  <https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/leaderboard>
- active 2枠はv4.3a **862.8 / 249戦126勝123敗 (50.6%)**、v4.2t
  **708.6 / 204戦101勝103敗 (49.5%)**。v4.3aは旧v4.1aの凍結869.1も下回り、
  canonical deck模倣＋現行BCSだけでは上位へ届かないことが収束値でも明確になった。
  <https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/submissions>
- 21:43時点の1100+全17 teamを現公開replayで分類すると、Grim 7 (41.2%、トップ3全て)、
  Rocket / Dragapult / Cynthia Garchomp各2 (11.8%)、Alakazam / Kang / Lopunny–Dudunsparce /
  Mega Starmie系各1 (5.9%)。00:10には新たに1 teamが1100へ入り18 teamになったため、
  17-team分類は時刻付きsnapshotとして扱い、新規1 teamを未分類のまま既存比率へ混ぜない。
- 07-22 Daily Top datasetは00:10時点では未公開だったが、07-23 09:01 JSTに公開された（次節）。
  この時点の最新datasetが07-21だったという観測記録は残し、現在状態とは分ける。
  <https://www.kaggle.com/datasets/kaggle/pokemon-tcg-ai-battle-episodes-2026-07-21>

## 9. 2026-07-23 22:25 JST 更新

- Kaggle公式Leaderboardの22:10:09固定CSVは **5,571 teams**、median 647.6、1000+ 92、
  1100+ 13、1200+ 0、leader 1156.9、top-8 cutoff 1116.6。自チームは454位 / 871.7。
  activeはv4.3a 871.7 / v4.2t 699.5、本日提出0/5。22:25 live値は1100+ 16、
  top-8 cutoff 1119.3へ動いたため、短時間のlive値でgateを変えず固定CSVを時刻付きで扱う。
  <https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/leaderboard>
- 07-22 Daily Top Episodesは07-23 09:01 JSTに公開済み（740,375,805 bytes）。
  07-21止まりという前節の状態は解消した。追加学習へ即混合せず、最新deck別・top-5外介入・反復失敗に
  分けて採掘し、既存bc_v2とのA/Bを通す。
  <https://www.kaggle.com/datasets/kaggle/pokemon-tcg-ai-battle-episodes-2026-07-22>
- 現Top8の最新公開replayを1件ずつ照合すると、Grim 3 / Alakazam 3 /
  Kangaskhan–Crustle 1 / Dragapult 1。Luca、me and the lads、RmyのGrimは60枚の配列順まで一致し、
  対戦相手を含む計6 teamで同型を確認した。07-21 canonicalから
  `Handheld Fan -2 / Pokégear 3.0 +1 / Tool Scrapper +1`。
  episode 87663925 / 87663311 / 87663980を根拠にexact wallへ固定した。
  Alakazam上位のMajkel/Yushinは既知Hammer4と一致する。これは公開標本の母集団採用率ではなく、
  deck techの複数上位再現とexact対戦壁の証拠として使う。
- active rule-based agentが「一時2位、通常top10」とする07-23の匿名自己申告がある。
  rule方式の上限が低いとは言えない一方、本人・提出物を照合できないので採用根拠の信頼度は低〜中。
  <https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/728168>
- Tony Li氏はpolicy accuracy 79%→95%がLB改善と相関せず、類似checkpointで30–80pt差、
  旧版・公開agentとのlocal tournamentで選ぶと報告。同じcheckpointでもdeck変更の影響が大きく、
  pure IL約21k gamesで大差が出るとの参加者報告もある。単一accuracyよりdeck共適応と代表wallを重視する。
  <https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/728071>
- 30,000試合の思考時間分析は約半数をrule系、当時首位をRL＋bounded searchと推定するが、
  時間指紋による分類には誤分類反論がある。同スレでは「valueが弱いとsearchがraw policyを悪化させる」
  という実体験も報告され、候補Qの反証gateが必要な外的理由になる。
  <https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/724362>
- BCへRLとsearchを重ね、heuristic agentでlocal評価し、episodeに一貫する失敗をRLで補ったという
  参加者報告がある。BC単独は成果の20–30%という自己評価で、Expert Floor＋Search＋ExItに近いが、
  数値は自己申告なので方向性の傍証に留める。
  <https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/717697>
- Xで本文と日時を直接確認できた07-15投稿は、短期LBぶれで良い提出を壊さない、メタ変化で古いlogicは
  陳腐化する、単一ログ完全一致でなく同型局面へ一般化する、変更を少量ずつ入れログで因果確認するという要旨。
  現在のrow-SHA凍結traceとrule単位ablationを支持する。
  <https://x.com/tanuproojisan/status/2077346664449274132>
- ユーザー提示の「強者行動を愚直にルールベースへ書き起こす」原文は、完全一致・部分一致検索でも
  再取得できず、上記X投稿と同一とは扱わない。結論は巨大if-cascadeの模写ではなく、
  **破滅手guard → 専門家手をroot候補へ保証 → search Qで反証 → 採用介入だけExItへ蒸留**
  という検証可能な閉ループを維持すること。
