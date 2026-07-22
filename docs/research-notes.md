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
