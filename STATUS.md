# STATUS — 現在の状態と次のアクション

> どのAIエージェント(Claude Code / Codex)も、**作業の開始時にこれを読み、終了時に更新する**。
> 作業中の衝突防止: 大きな作業を始めるときは下の「作業中」欄に記入してcommit+pushする。

最終更新: 2026-08-15 19:30 JST (Claude Code) — ✅ **最終日前夜の態勢完了。
active = v5.11g(74戦54.1%/814.2) + v6.0o(40戦60.0%/855.6=提出史上最高、Ogerponアーキ転換試験)。**

## 最終日(08-16)の実行手順(締切 = 08-16 23:59 UTC = 08-17 08:59 JST)

1. 朝9時頃(JST): `zsh scripts/bc_fetch_days.sh 2026-08-15`(08-11〜14分は取得済み)
2. pairs_grim7構築(bc_grim3レシピのsources+0811〜0815=21日分。bc_filter_deck --key Grimmsnarl)
3. **bc_grim7学習(確定レシピ)**: `train_bc.py --data data/bc/pairs_grim7.jsonl.gz --epochs 12
   --seed 42 --lr-halve-after 7 --export-best --name bc_grim7`(約15分)
4. ミラー退化検査: v5.12g-bc vs v5.4g-bc 400戦(agents定義済み)。**REJECT=45%以下のみ**。
   REJECTならbc_grim6_e12ベース(v5.11g同等)に差し替え
5. v6.0o判定(事前登録bead882): **試験50%以上なら2枠目採用**、未満ならv5.11g同等を2枠目
6. **最終2本を提出**(この順で: 先に2枠目→最後に1枠目v5.12g)。提出前に
   `kaggle competitions submissions`で他提出がないか確認(絶対ルール2)
7. versions.md/STATUS更新・commit・push。締切後2週間の収束で最終順位確定(docs/plan.md:26)

## 現況の要点(08-15夜)

- **v6.0o(Ogerpon+bc_ogerpon)が40戦60.0%/855.6** — 壁実験の「対Grim 90-99%」がラダーでも
  通用している。最終ペアは{v5.12g=Grim安全枠, v6.0o=Ogerpon上振れ枠}の無相関2本柱が有力
- bc_grim7の最終レシピ確定: epochs12+ep8以降LR半減+export-best(75.3-75.4%×3実行で検証)
- soup(重み平均)は44.41%で反証済み(異初期化の平均は関数を壊す)。エリート加重・容量拡大も反証済み
- 忠実度の天井は74-75%付近。ルール系はGR001/2のみ既定(GR003/4/ミラー脅威は反証済み)
- データ: pairs_0811〜0814取得済み。明朝は0815のみ

(以下は08-14未明までの記録)
✅ e12が全関門通過、v5.11gをラダー試験へ提出(sub 55487260)。
方針の要点(docs/plan.md:26): **締切後2週間対戦してからLB確定・最終評価は最後の2提出のみ**。
よって現在のレートや押し出しは最終評価に無関係で、**08-16に最終ペアを選び直して最後に2本提出**する。
候補: bc_grim7(e12レシピ+08-15までのデータ、08-16朝に学習) / v5.11g(試験結果次第) /
v5.6g同等(bc_grim3+guard、実績91戦59.3%)。e12はholdout75.2%(再実行2回)+ミラー53.25%/400で
日次更新系初のプラス圏。エリート加重(+0.13pt)と容量拡大(74.94%)は反証済み。
忠実度天井は74〜75%付近と確定。

(以下は08-13の記録)
✅ v5.6gの80戦判定完了(82戦58.5%)。当時「これ以上提出しない」と決定したが、
これは締切=評価終了という誤前提で、同日中に撤回した(上記参照)。
active = v5.6g(82戦58.5%) + v5.10g(66戦54.5%)、両方50%超でscore上昇中。
guardのOgerpon/Lopunny効果は本番でも証拠なし(n=7)だが害もなし。ミラー70.6%・(other)改善は
guard起因ではない(分散・語彙効果)。総合58.5%にはAlakazamシェア3倍の追い風が混在。
残タスク: 収束監視のみ。08-14〜15のbc_grim7は両提出が急落した場合の保険としてのみ判断。

(以下は08-11時点の記録)
✅ v5.10g(bc_grim6+ohko_guard)を提出(sub 55435709)。08-11の提出枠 1/5 使用。
経緯: ユーザー指示「80戦待ちは悠長」で前倒し。v5.6gは55戦時点で中間判定=健全
(総合62.5%、ミラー55.6%回復、Alakazam 76.9%。ただしAlakazamシェア3倍の追い風混在)。
アンカーv5.1g再は55戦46.4%と収束不調のため押し出し対象とし、最新データ(08-10込み16日/
語彙203/holdout 74.7%)×guardのv5.10gに置き換えた。ミラーA/B 47.13%/400は事前規則ADOPT。
⚠️ **日次更新モデルのミラーA/Bは3連続で50%割れ(48.75/46.12/47.13)だが全てCI内。
ミラーは更新価値を測れない設計なので、判断はラダー実測で行う。**
⚠️ **次に提出する場合、押し出されるのはv5.6g(61.8%形成中)。原則これ以上提出しない。**

## 08-11未明の追加測定(チームセッション第2部)の結論

1. **ミラー(シェア最大17.5%)はルールで直せない**: v5.4gミラー5敗の「一撃死圏」は昇格ではなく
   MAIN局面の攻撃/逃走判断で、**勝ち試合でも同率発生(集中度0.88倍)=悪手ではなく負けの言い換え**。
   ミラー脅威拡張(v5.9g-bc)はゲート不合格、ミラー直接A/Bも52.5%でINCONCLUSIVE。
   GR005(リトリート強制)は着手しない(決定)。**v5.9gは提出しない、v5.6g体制維持**。
   収穫: 発火116/blocked 47が起きた状態で52.5%=「guardがミラーで発火しても退化しない」初の実測。
2. **LB帯フィルタでは壁は弱くならない**(重要な機構発見): 学習元が勝者側の判断なので、
   中間帯(650-1000)壁でも床効果再発(基準9.75%)。壁を弱めるにはプレイの質への介入が必要。
3. **guard(GR001/2)のΔ累積: +0.25 / −1.50 / −4.25pt**(全てINCONCLUSIVE、床効果下)。
   効いている証拠はローカルでは得られず。**決着はv5.6gのラダー実測**(対Ogerpon/Lopunny対面の
   勝率がv5.1gの16.7%/0%やv5.4g凍結値から動くか)。
4. v5.4gのOgerpon系4敗中3敗7局面でguardが介入可能だったことは確認済み(効果があるなら
   ここに現れるはず)。
5. 引き継ぎ注意: ①ミラーでfired=0の測定を安全性の根拠にしない ②評価の起動直前にSHAを取り直す
   ③新資産 = bc_grim5 / bc_ogerpon / bc_ogerpon_mid / wall-ogerpon(-mid)-bc /
   bc_filter_deckの--min-copies・--max-team-score / v5.6g〜v5.9g系agent群。

## 08-10夜のチームセッション成果(19:30〜21:15 JST、4+1エージェント並列)

**①敗因機構を特定・対策実装(最重要)**: 対Lopunny/Ogerpon 15戦13敗の全リプレイ精読で、
「相手の可視エネから計算可能な一撃死圏に主力を出す」悪手が**13敗中12試合34局面**に関与と確定。
明示ルール **ohko_guard(GR001=昇格/入替、GR002=進化)** を純BC経路に実装(27a27a6〜f8193dc、
既定OFF、agent_config.jsonの`ohko_guard`キー、テスト194件、発火カウンタでno-op検出可能)。
**bc_grim3でもbc_grim5でも同じ悪手を選ぶことを実測 = 日次データ更新とは独立の対策**。
再生検証: ブロック17手が14敗1勝に集中、介入率0.022%。
⚠️ **GR003(アタッカー優先)とGR004(進化ライン温存)は反証済みで恒久的に既定外**
(GR004は壁A/Bで−4.0pt、唯一CI分離した差。docs/experiments.md参照)。

**②bc_grim5(15日/303万判断/語彙196/holdout 74.2%)**: 08-08/09データで日次更新。
ミラーA/B 46.12%/400(規則上ADOPT、実態は「bc_grim3と区別できない」)。
**対Ogerpon壁でも−0.5ptで優位なし → 提出はbc_grim3系を維持**(事前登録の+8pt条件不成立)。

**③Ogerpon壁を構築**: `bc_ogerpon`(mill除外の主軸39.1万判断/86チーム、holdout 69.2%)+
合意60枚 `decks/meta/snapshot_20260809_ogerpon_teal.csv` = `wall-ogerpon-bc`。
⚠️ `--key Ogerpon`素朴抽出はKangミル(Cornerstone 1枚差し)が大量混入する。`--min-copies 4`必須。
⚠️ **壁は床効果あり**(全アーム勝率1〜7%)。±5pt閾値の設計はここでは機能しない。次回はオッズ比か弱い壁で。

**④guard(GR001/2)の壁A/BはINCONCLUSIVE**(Δ1=+0.25/Δ2=−1.50、発火実在663〜919/400戦)。
ミラー50.0%は**発火0のトートロジー**でありguard安全性の証拠に使わない(bcdata申し送り)。
事前既定により**実験枠の提出候補としては許容**(候補: `v5.6g`=bc_grim3+GR001/2)。

**⑤診断**: タイプ別top-1(holdout)で**失点源はMAIN行動選択(65.8%、総誤りの62%)**、
語彙拡張はMAINに不動(+0.2pt)。attachは90%台で公開知見(63.5%)は再現せず。
PLAY⇄ABILITY取り違えが最大セル(実害未切り分け)。**Ogerpon対面は語彙の問題ではない**
(両カードともbc_grim2時点で語彙内、壁でもgrim5優位なし)。

**⑥計測ツールの修正**: bc_accuracy_by_typeのcid2idxオフバイワン(a4f21b8)、
ladder_matchupsのARCHETYPE_KEYSにLopunny/Ogerpon追加(これまで(other)に埋もれていた)。
新ツール: replay_log_trace.py / ohko_commit_pattern.py / bc_main_confusion.py。
v5.5g(bc_grim4)ではなくv5.1g再を選んだ理由: bc_grim4はA/B 48.75%/400で優越の証拠がなく、
未検証2枚をactiveに並べるより「実績アンカー+実験枠」の構成が最終評価(最新2提出)に安全なため。
以下は08-10午前〜18:57までの記録。
**探索の是非が本番で決着。失点源はOODの長い裾と特定し、語彙拡張で対処**。
①探索は本番でも有害と確定: v5.1g(純BC) **840.0/210戦** vs v5.0g(探索) **751.6/158戦** = **-88.4点**。
②v5.1gの対面別210戦で、主戦場は勝っている(ミラー55.7% / 対Alakazam 58.5%)のに
**(other) 26戦3勝23敗=11.5%** が総合50.0%を押し下げていた。
③機構を特定: `bc_grim2`の語彙143枚では、相手の場のChandelure/Applin/Iono's系など
**43枚(うち41枚がポケモン)が索引0=unknownに潰れて見えていなかった**。
④`bc_grim3`(13日276万判断/329チーム/**語彙186**)を学習しA/B 54.87%/400でADOPT、`v5.4g`を提出。

## ⚠️ 最重要(2026-08-10 更新)

1. **探索は使わない(本番で確定)**。同一デッキ・同一モデルで探索の有無だけが違う2提出を
   本番で並走させ、**-88.4点**(210戦 vs 158戦、両方とも判定基準超え)。
   ローカル(同一壁で純BC 67.1%/400 vs fixed2 46.0%/200 = -21.1pt)と符号一致。
   温度サンプリングでの救済も**DEAD**(温度0.5で50.0% / 温度1.0で34.3%と単調悪化)。
2. **失点源はOOD(分布外)の長い裾**。主戦場ではなくここを直す。
   語彙に無いカードは**索引0に潰れて区別できない**ので、
   **データ更新を止めると新デッキが自動的に見えなくなる**。これが劣化の主経路。
   → **BCデータの日次更新は「あれば良い」ではなく必須**。
3. **天井ではなく忠実度が制約**。学習データの重心はLB約1050なのに実測は840。
   模倣対象より210点下にいる。top-1 74%(判断の26%が違い、約140判断で複利)が効いている。
   08-02のエリート限定BCが互角だったのは、質を上げる代わりに量を1/3にしたため。
4. **同レシピ・データ量差のA/Bは400戦では解像できない**(CI±5%)。
   公開知見(citerne)も「ローカルで10点未満の改善は検証不能」。
   → こういうA/Bの役割は**優越性の証明ではなく退化の検出**と割り切り、
   判定規則を「REJECT=45%以下のみ」と事前に置く。事後に閾値を動かさない。
5. **`--profile production`は純BC同士のペアでは成立しない**(standardに解決される)。
   時間安全性を測るときは探索エージェント(例: `build/v4.3a`)を相手にする。
6. **提出前に必ず日付順を確認する**。最新2提出がactiveなので、
   08-01にv5.1gを出したとき押し出されたのはv4.3h(07-25)ではなく**v4.3a(07-15)**だった。
7. **公開リプレイに使えるアンチGrim信号は無い**(自botの混入とElo交絡)。判断は公式Daily Topを使う。

## ラダー状況(2026-08-10 18:57 JST 実測、active = 最新2提出のみ)

🚨 **v5.4gの提出で押し出されたのは v5.0g ではなく v5.1g(我々の最高スコア837.8)だった。**
提出日時は **v5.1g 08-01 23:57 UTC < v5.0g 08-02 01:47 UTC** で、v5.0gの方が新しい。
STATUS「最重要6」で07-25に同じ罠を踏んだのに、**08-10に再発させた**。

| 提出 | active | 内容 | score | 戦数 | 生勝率 |
|---|---|---|---:|---:|---:|
| **v5.4g** (sub 55399895) | **yes** | bc_grim3(13日/語彙186) + Grim合意60枚 + 純BC | 752.3 | **33** | 53.0% |
| **v5.0g** (sub 55174905) | **yes** | bc_grim2 + 同左 + **探索BCS 8s** | **760.0** | 196 | 54.1% |
| v5.1g (sub 55172873) | **no(押し出された)** | bc_grim2 + 同左 + 純BC | **837.8** | 249 | 50.2% |
| v4.3a (sub 54731784) | no | bc_v2 + Alakazam | 795.7 | 496 | 49.4% |

active判定の根拠(episodesの最終試合時刻、UTC): v5.4g **09:44** / v5.0g **08:16** で継続中、
v5.1gは **06:56** を最後に停止(v5.4g提出07:16の直前)。
LBのチームscore **760.0** = max(752.3, 760.0) とも一致する。

**現在: 1332位 / 760.0**(6,700チーム、08-10 09:57 UTC公式LB)。
メダル基準: 金 1090.5(23位) / **銀 903.8(328位)** / **銅 839.9(656位)**。
**銅ラインから -79.9点**。08-08時点(668位/840.0、銅-1.6点)から **664位後退**した。
後退の原因は実力低下ではなく**上記の押し出し事故**(837.8が外れ760.0が残った)。

**復旧方法**: 今日もう1回提出すれば、押し出されるのは v5.0g(08-02)で
active = v5.4g + 新提出 となり、探索版が消える。本日の提出枠は **1/5 使用**。

⚠️ v5.4gの33戦のscoreは読まない。v4.3aは78戦で920.7 → 496戦で795.7へ収束した。

## メタの時系列(公式Daily Top、チーム単位シェア)

| 日 | 勝者チーム | Grim | Alakazam | Kang | Lopunny | Ogerpon |
|---|---|---|---|---|---|---|
| 07-22 | 119 | 33.6% | 34.5% | 9.2% | 4.2% | 0.0% |
| 07-31 | 142 | **62.7%** | 13.4% | 15.5% | 3.5% | 2.8% |
| 08-05 | 276 | 40.6% | 24.3% | 13.0% | 8.3% | 10.5% |
| 08-07 | 298 | **41.9%** | **24.2%** | 13.4% | **12.4%** | **9.1%** |

**環境は一極集中(07-31) → 分散(08-07)へ再転換した**。上位帯のチーム数も142→298とほぼ倍増。
分散したメタでは「デッキを当てる」価値が下がるので、**08-08時点ではデッキを変えない判断をした**
(Grimは首位維持、ミラー55.7% / 対Alakazam 58.5%と主戦場では勝っている)。

⚠️ **Lopunny 3.5倍 / Ogerpon 3.3倍**の急増は、我々の失点源そのもの
(Lopunny 6戦16.7% / Ogerpon 4戦0.0%)。合計21.5%(6日前は6.3%)。
**この2つは既に`bc_grim2`の語彙にあったので、語彙拡張では説明できない**(26戦中10戦)。
原因は未特定で、次の最有力調査対象。

## 次のアクション(2026-08-10 21:20 全面更新、優先順)

1. **v5.4gの80戦判定を待つ(それまで提出しない)**。08-10 21:00時点で36戦48.6%、
   ペース鈍化により到達は08-11中の見込み。判定時は `ladder_stats.py` +
   `ladder_matchups.py 55399895`(新ARCHETYPE_KEYSでLopunny/Ogerponが個別に見える)で
   **(other)が11.5%から改善したか**を見る。
2. **判定後の提出候補(押し出されるのはv5.4g)**: 第一候補 **`v5.6g`(bc_grim3+GR001/2、
   出荷ラベル版ビルド済み・両席DONE)**。根拠: モデルはv5.4gと同一なのでラダー比較が
   guardの効果測定になる/ミラーコスト構造ゼロ/再生検証でブロックが敗戦に集中。
   bc_grim5系は壁・ミラーとも優位が出なかったので保留(悪くもないので、判定次第で
   v5.8g-bcを実験枠に回す選択肢は残る)。アンカーv5.1g再は温存。
3. **BCデータ日次更新の最終回を08-14〜15に1回**(08-10〜13分)。bc_grim3レシピで学習し、
   REJECT(45%以下)でなければ最終提出の材料にする。それ以外の中間更新は
   「Ogerpon対面は語彙の問題ではない」と判明した今、優先度を下げてよい。
4. **GR003/GR004は有効化しない**(反証済み)。ohko_guardの打点モデル拡張もしない
   (壁の床効果で局所検証が不能なため、検証できない複雑さを積まない)。
5. MAIN誤りの実害切り分け(PLAY⇄ABILITYが順序違いか実害か)は締切までの残工数次第。
   optional。

## 次のアクション(2026-08-10 18:57 更新、優先順)

0. ~~押し出し事故の復旧~~ → **完了(08-10 19:09 JST)**。ユーザー承認のうえ v5.1g を
   同一ビルドで再提出(sub **55403337**)。active = v5.4g + v5.1g再となり探索版v5.0gは押し出し。
   v5.5g(bc_grim4)は見送り(A/B 48.75%/400で優越の証拠なし。未検証2枚を並べない)。
   ⚠️ v5.1g再は**新規提出なのでレートは初期値から収束し直す**(837.8が即時に戻るわけではない)。
   以後に提出する場合、押し出されるのは**v5.4g**になる点に注意(日付順: v5.4g 07:16 < v5.1g再 10:09 UTC)。
1. **v5.4gの判定**(80-100戦到達後、約2日)。`scripts/ladder_stats.py`と
   `scripts/ladder_matchups.py <sub_id>`で**(other)が11.5%から改善したか**を必ず見る。
   これが語彙拡張の効果測定そのもの。**それまで別物に差し替えない**。
2. **BCデータを日次更新する**。上記「最重要2」のとおり必須。
   `zsh scripts/bc_fetch_days.sh 2026-08-08 ...` → `bc_filter_deck` → `train_bc`。
   締切08-16まで、最低でも提出前にもう1回は回す。
3. **Lopunny/Ogerpon対策の原因調査**。語彙にあるのに負けている10戦。
   `scripts/render_replay_jp.py`で実際の敗戦を読むのが早い。
   これが解ければ21.5%のフィールドに効く。
4. **`meta_decks.py`の更新は保留のまま**。純BCでは探索を使わないので**効かない**。
   探索を復活させる場合の前提条件としてのみ意味がある。
5. **`scripts/bc_accuracy_by_type.py`を回す**(未実行)。選択タイプ別のtop-1精度を出し、
   どの判断クラスで外しているかを特定する。公開知見ではプラン型attachだけが有意(63.5%)。
   複数選択(maxCount>1)の精度は当リポジトリで一度も検証していない。
   ⚠️ 未コミットの修正が作業ツリーにある(`vocab_mod.VOCAB` → `vocab_mod.CARD_VOCAB`)。
   このまま走らせないと`AttributeError`になる。
6. **BCデータは08-07までしか無い**(`data/bc/pairs_0808`以降が不在)。
   `pairs_grim4`は新規データではなく`pairs_grim3`の**再サンプリング**なので日次更新の代わりにならない。

## 外部情報(08-02 取得)

- `kaggle forums`はAPI 403、Web版はJSレンダリングで**ディスカッションは読めない**。
  代わりに`kaggle kernels list/pull`で公開ノートブックの実体を取得できる。
- **公開ルールベースagentが950+**(`romanrozen/strong-start-baseline-agent-v10-lb-950`、607行、
  NN無し)。中核は`class AttackPlan(attacker, target, attack_index, remain_hp, needs_energy)`。
  ⚠️ ただしデッキは**Mega Lucario ex**で、950+は**07-20時点**の値。現環境での再現は未確認。
- 2ヶ月/13アーキテクチャ/約30提出で800.7に留まった参加者(citerne)の報告:
  - **価値網は序盤で機能しない**(AUC ターン2で**0.521**=コイン投げ。試合は中央値10ターン、
    判断の32%がターン4以下)。かつ**弱い相手で較正すると強い相手に対して自信過剰**
    (950+相手のバイアス+0.494)。→ **価値網の作り直し案は取り下げた**。
  - 「40戦のアリーナは±15点の窓。200戦で有望に見えた5変種が600戦で全て消えた」
  - 「探索は**クラッシュせずに100% no-op**になりうる。実行されたことをassertせよ」


## ⚠️ 最重要(2026-08-02 更新)

1. **`bc_grim2`では探索を使わない**。同一壁・同一デッキ・同一モデルで自陣設定だけ変えると
   純BC **67.1%/400** に対し BCS fixed2 **46.0%/200**(-21.1pt、CI非重複)。
   フーディン側は同一壁で **+14.5pt** だったので**符号が反転している**。
   `fixed_search_errors`/`incomplete`とも0・全戦DONEで、機構異常ではなく判断そのものが劣る。
2. **Grimでは`fixed8`をA/Bに使えない**。T4は`failure_count=12`(TIMEOUT)で
   `min_remaining_overage_sec = -5.20秒`。`fixed_worlds`指定時のループは意図的に時計を無視して
   回し切る設計のため、8世界×5候補×最大200手が600秒予算を食い破る。
   **本番で到達できるのは2〜5世界**で、その下端(fixed2)が46.0%。やり直すなら`fixed4`まで。
3. **世界(determinization)は隠れ情報しかサンプルしない**。`belief.sample_world()`の返り値は
   カード配置のみで、相手の行動は`policy.choose`の**argmax(決定的)**。世界を1つ決めると
   終局まで一本道で、**相手の戦略分岐は一切探索していない**。`ROLLOUT_MAX=200`・
   `value.ENABLED=False`なので約140手を打ち切りなしで回す。
   → 未決着の仮説: **A 分散**(世界を増やせば回復) vs **B 複利誤差**(増やしても回復しない)。
   既知の傍証はB寄り(`opp_policy`は完全中立50.0 vs 50.0/400、価値網はAUC 0.851でもA/B 47.8%で棄却)。
4. **公開リプレイに使えるアンチGrim信号は無い**。自チームの試合を除くと300戦・各セルn=8〜17。
   Lopunny(生勝率71.4%・首位ら採用)は**Elo補正で超過+1.9ptに消える**。
   Kang/Lucarioの対Grim優位は**旧v4.1g(我々の壊れたGrim bot)の敗戦が混入**していたもの。
   **奇策の根拠にはできない**。判断は公式Daily Top(大標本・クリーン)を使う。
5. **非Alakazamデッキ相手のローカル勝率を根拠に使わない**(旧知見、継続)。壁は必ず
   「そのデッキで実際に勝っている人のデータ」で学習した方策に操縦させる。
6. **40–200戦のゲートで±2–3%は検出できない**(旧知見、継続)。狙うのは二桁ptの差だけ。

## ラダー状況(2026-08-02 05:30 JST、active = 最新2提出のみ)

| 提出 | active | 内容 | score |
|---|---|---|---|
| **v5.0g** (sub 55174905) | **yes** | bc_grim2 + Grim合意60枚 + **探索BCS 8s** | PENDING / 0戦 |
| **v5.1g** (sub 55172873) | **yes** | bc_grim2 + Grim合意60枚 + **純BC(探索なし)** | **815.0 / 31戦** |
| v4.3h (sub 54968749) | no | bc_v2 BCS + Hammer4 Alakazam | 740.5 / 217戦49.8%で押し出し |
| v4.3a (sub 54731784) | no | bc_v2 BCS + canonical Top Alakazam | 795.7 / 315戦49.8%で押し出し |

**v5.0g と v5.1g はデッキも`bc_grim2`も完全に同一で、探索の有無だけが違う本番A/B**。
ローカルの壁は実物より約19pt弱い(対Grim ローカル50%に対し本番31%)ので、
探索の是非はラダーの方が信頼できる判別になる。

⚠️ **早期scoreは読まないこと**。v4.3aは78戦で920.7 → 315戦で795.7へ収束した。
判定は両方が80–100戦に達する **08-04頃**。それまで別物に差し替えない。
参考として v5.1g の31戦時点815.0は、v4.3aが315戦かけて到達した795.7より上ではある
(過去の純BC提出は685〜770だった)。実力値としては扱わない。

⚠️ 日付順で最新2提出が決まる。v5.1g提出時に押し出されたのは v4.3h ではなく **v4.3a(795.7)**
   だった(v4.3hの方が新しいため)。提出前に必ず日付順を確認すること。

フーディン系は環境の硬化とともに沈み続けている: v4.3a 871.7(07-23) → 810.2(08-01) → **795.7**、
v4.3h 889.6(07-25) → 768.2(08-01) → **740.5**。Top8境界は1116.6(07-23) → **1133.7**(08-01)、
自チーム順位は454位 → **795位**。

## メタの時系列(公式Daily Top、チーム単位シェア)

| 日 | 勝者チーム | Grim | Alakazam | Kang | Lopunny |
|---|---|---|---|---|---|
| 07-22 | 119 | 33.6% | 34.5% | 9.2% | 4.2% |
| 07-26 | 141 | 53.2% | 26.2% | 6.4% | 2.1% |
| 07-28 | 154 | 55.8% | 20.1% | 13.0% | 0.6% |
| 07-30 | 149 | 58.4% | 16.8% | 16.1% | 2.7% |
| 07-31 | 142 | **62.7%** | 13.4% | **15.5%** | 3.5% |

**予測(締切08-16)**: Grimが主役のまま終わる可能性が高い。チームシェアが単調上昇、
合意60枚が07-23から**完全に不変**(111チーム中82チーム=74%が同一構築)、集中度HHIは0.24→0.53と
7月の最高値、統計的に支持される天敵が存在しない。残り期間は上位ほど実験をやめて固める時期。
**ただし7月に一度回転している**(Grim 38% → Alakazam 44% → Grim 70%)ので断定はしない。
**最有力の対抗馬はKangaskhan**(9日でチームシェア9.2%→15.5%と倍増、明確な2番手)。
`bc_kang`(70.3万判断)が既にあり、最新データで`bc_kang2`を作れば同じ手順で試せる。

## 次のアクション(2026-08-02、優先順)

1. **v5.1gの判定を08-04頃に行う**(80–100戦到達後)。`scripts/ladder_stats.py`と
   `scripts/ladder_matchups.py 55172873`で対面別も出す。**それまで別物に差し替えない**。
2. ~~第2枠の使い道~~ → **完了(08-02)**。`v5.0g`(探索あり)を提出、sub 55174905。
   これで探索有無の本番A/Bが成立。**08-04頃に両方を判定する**。
3. **`meta_decks.py`を現環境へ更新**(Task #6)。07-10版でオーロンゲが不在。
   `infer_opponent_deck`は不一致時に`my_deck`へフォールバックするため、
   **上位帯68%の対戦で相手をフーディンと誤って埋めていた**。
   ⚠️ ただし`v5.1g`は純BCで探索を使わないので**この修正はv5.1gには効かない**。
   探索を復活させる場合(項目4)の前提条件として先に直す。
4. **探索を救えるか(未決着の本丸)**。
   - ~~ロールアウトを確率的にする~~ → **実装済み(08-02、`b861779`)**。
     `agent_config.json`の`rollout_temperature`(0..2、既定0で完全no-op)。
     温度0では`_policy_act`/`_rollout`の**呼び出し引数の数まで従来と同一**にしたので
     既存テストは無変更で通る。テスト135件通過。
     A/B用agent: `v5.2g-t05-fixed2`(温度0.5) / `v5.2g-t10-fixed2`(温度1.0)。
     **基準は同一壁`wall-grim-top8-bc`に対し温度0の`v5.0g-fixed2` = 46.0%/200**。
     ⚠️ 未実行。CPUを占有するので他の重い評価と並走させないこと。
   - **価値網でロールアウトを打ち切る**。`value.py`に`VALUE_TRUNC=20`の機構が
     `ENABLED=False`で眠っている。棄却は07-14で当時のペアは`bc_v2`(62%)。
     **方策が74%になった今は条件が違う**ので再評価の価値がある。
   - `fixed4`でT4をやり直し仮説A/Bを判別する(約1.5時間)。
5. **エリート限定BC(`bc_grim_elite`)**。**BCは模倣した集団の平均を超えられない。**
   `bc_grim2`の学習データは判断シェアで1100+が33.2%/13チーム、1000-1100が46.3%/71チーム、
   900未満が14.8%で**重心はLB約1050**。つまり方策の天井が約1050で、Top8境界1133.7には
   構造的に届かない。`bc_filter_deck --min-team-score 1100 --lb results/lb_20260801.csv`で
   **607,600判断 / 13チーム / ユニークデッキ5**を抽出済み(`data/bc/pairs_grim_elite.jsonl.gz`)。
   `bc_kang`(70.3万でholdout 58.6%)と同程度の量なので学習は成立する見込み。
   08-02に学習開始。次は**`bc_grim_elite` vs `bc_grim2`の純BCミラー**で天井が上がったか直接測る。
6. **`bc_kang2`を作る**(対抗馬への保険)。最新データで`bc_filter_deck --key Kangaskhan`。
   Grimが崩れる兆候が出たときに即座に試せる状態にしておく。
7. **データを日次で更新する**。`bc_grim2`は07-31まで。放置すると今日と同じ
   「古い環境のモデル」に戻る。`bc_fetch_days.sh` + `scripts/meta_matrix.py`を日次で回し、
   **Kangaskhanの台頭(9日でチームシェア9.2%→15.5%)**を早期検知する。


## ⚠️ 進め方の最重要事項(2026-07-25 更新)

1. **非Alakazamデッキ相手のローカル勝率を根拠に使わない**。相手をbc_v2(Alakazam学習)に操縦させると
   分布外で弱くなり、ローカル88.95%が本番25.7%になる。壁は「デッキ」ではなく「そのデッキ用に
   学習した方策」で作らなければ意味がない。
2. **Alakazamミラーでの方策A/Bはもう情報を持たない**(本番ミラー49.6%=伸びしろなし)。
   方策改善6連続中立の理由はこれ。測る場所を対Grim/Dragapultへ移す。
3. **40–200戦のゲートで±2–3%は検出できない**(要n≈3000)。nativeエンジンはseed非公開で
   common random numbersが使えず分散低減も効かない。**±5%未満を狙う施策はローカルでは判定不能**と
   割り切り、大きい効果だけを狙う。
4. **提出枠を遊ばせない**。07-16以降9日間 0/5。v4.2t(699.9)スロットは最新2提出の下位なので、
   1回提出すればv4.2tだけが押し出され**v4.3aは残る=ノーリスク**。ラダーは1提出あたり約25戦/日の
   実分布データ源であり、ローカル40戦ゲートより情報量が多い。

## ラダー状況(2026-07-25 16:10 JST、active = 最新2提出のみ)

| 提出 | active | 内容 | ライブレート / 公開対戦 |
|---|---|---|---|
| **v4.3h** (sub 54968749) | **yes** | bc_v2 BCS + **Hammer4 Alakazam**(Top8 Majkel/Yushinと同一60枚) | **889.6 / 戦数僅少で判定不能**(07-25 15:30提出) |
| **v4.3a** (sub 54731784) | **yes** | bc_v2 BCS + canonical Top Alakazam | **832.8** / **315戦157勝158敗 (49.8%)** — 871.7から低下 |
| **v4.2t** (sub 54688865) | no | bc_v2 BCS + Great Tusk–Crustle mill | 699.9 / 255戦で押し出し・凍結 |

⚠️ v4.3hの初期scoreは読まないこと。v4.3aも78戦時点で920.7 → 315戦で839へ収束した。
**判定は最低80–100戦(約2日、07-27頃)以降**。それまでv4.3hを別物に差し替えない。
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

## 次のアクション(2026-07-25 全面改訂 / 優先順)

**A. 本番315戦で判明した対面別実勝率(最重要・`results/ladder_matchups_v4.3a_20260725.json`)**

| 相手 | n | 比率 | 勝率 |
|---|---:|---:|---:|
| Alakazam(ミラー) | 115 | 36.5% | 49.6% |
| Archaludon+Cinderace | 58 | 18.4% | **72.4%**(カモ) |
| **Grimmsnarl系** | 35 | 11.1% | **25.7%** |
| Lucario | 25 | 7.9% | 60.0% |
| **Kangaskhan** | 16 | 5.1% | **37.5%**(10敗中5敗が自deckout) |
| **Dragapult** | 13 | 4.1% | **23.1%** |

時系列で二分すると対Grim比率 7.6%→13.9%、対Archaludon 21.7%→15.2%。**カモが減り天敵が増えている**。
1100+帯はGrim 38–41%なので、対Grim 26%のままでは1100は構造的に到達不能。

**B. やること(優先順)**

1. ~~**Grim専用スパーリング相手**~~ → **壁は完成。ただし対Grim直接チューニングは一旦閉じる(07-25)**。
   `models/bc_grim/`(164万判断/100チーム、holdout top1 **70.25%**)。
   壁は **旧52.8% → bc_grim純BC 35.5% → bc_grim+探索 38.0%** で、
   **探索を足しても壁は強くならず頭打ち**(+2.5pt、CI重複。自陣側の+14.5ptと非対称)。
   本番側も全Alakazam系提出をプールして **対Grim 13/42 = 31.0% [19.1–46.0]**
   (v4.3a単独の25.7%/35は標本不足だったので置き換え)。
   → **ローカルで対Grimの数pt改善を判定するのは、壁の残差と本番CIの広さの両方から現状不可能**。
   本番標本が貯まる(v4.3a/v4.3hが対Grim戦を積む)まで再開しない。確実な成果は旧壁からの17pt是正のみ。
   壁は資産として残す: `build/wall-grim-top8-bc` / `wall-grim-top8-fixed2` / `wall-grim-canonical-bc`。
   同じ手順で`bc_dragapult`(20.8万判断)/`bc_kangaskhan`(70.3万判断)も作れるが、
   **同じ測定限界に当たるので先に作らない**。
2. ~~**提出枠を使う**~~ → **完了(07-25)**。v4.3h = Hammer4 production、sub 54968749 COMPLETE。
   activeは v4.3h + v4.3a。**07-27頃に80–100戦到達したら判定**し、次のラダー試験へ回す。
   締切8/16まで残22日 = 逐次ラダー試験は実質あと2回。
3. **対Kangのmill負け対策**: 16戦中10敗の半分が自deckout。山札枚数を状態評価に入れる/
   終盤のドロー系サポーターを自制する等、**明示ルール(Expert Floor)の対象として
   AZ003(Hammer)より遥かに件数が多く効果も大きい**。AZ00x系のリソースをここへ振り替える。
4. **AZ003/AZ006/AZ008系はクローズ**: 対象局面が13–29件しかなく、40–160戦のゲートでは
   永遠にINCONCLUSIVEにしかならない。3日かけて採用0だった。残22日で再開しない。
5. **【大きい賭け・要判断】自分がGrimを持つ**: Top8はGrim 3/8。ただしv4.1g(751)の失敗は
   「bc_v2にGrimを操縦させた」ことが原因。**Grim専用BC(項目1で作る`bc_grim`)+ Grimデッキ**なら
   全く別の試行になる。項目1の副産物としてほぼ無料で試せる。
6. **Dunsparce4案は優先度低**: 短期崩壊17件(全315戦の5.4%)が上限。初手Basic枚数別の
   勝率差は無い(1枚49.8% / 2枚50.0%)。やるなら片手間で。
7. **時間/クラッシュは無罪**: 600s中 median 358s / max 545s、枯渇0・timeout 0・全DONE。
   時間予算の増減は本命ではない(過去にG1で不発済み)。

**C. 旧ブランチ(以下は上記の後回し。記録として残す)**

1. **AZ003をHOLDし、07-22 branchを閉じる**: 回復scanは全validator通過。semantic top-5外で
   Exact-safe **10/13=76.92%**、Broad-only **12/16=75.00%**、差+1.92pt。
   事前SUPPORT（80%以上かつ+20pt）未達で`INCONCLUSIVE_GUARD`。AZ009、個別trace、fresh wall、
   ExIt/production/提出へ進めず、07-22から別条件を後付けしない。変更なしの再確認は次の未開封
   Daily Topを取得・閲覧する前に停止則ごと事前登録する。
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
- AZ003 Exact-safe回復scanは全technical 0、privacy/frozen/recovery validator全通過。
  v1→v2差は4引分の正常skipと機械的gate再計算だけで、戦略集計は完全一致。Exact-safe
  **10/13=76.92%**、Broad-only **12/16=75.00%**、差**+1.92pt**のため
  **INCONCLUSIVE_GUARD**。r2 SHA `f3ed4d45...`。AZ003をHOLDし、AZ009/trace/wall/提出へ進めない。
- 初回version 1は`episode_schema_errors=4`でINVALIDとしてSHA `ded767a1...`のまま保存。
  4件は全て勝者なし`[0,0]`かつvalid step構造、malformed/multiple winner 0。
  回復protocolは`802527b`で事前固定し、旧結果を上書きしていない。
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

- (空き) — 08-10 21:20時点で実行中の重いジョブなし。チームセッションの学習・評価は全て完走済み
  (bc_grim5 / bc_ogerpon / 壁6アーム+ミラーの7本、results/arena.jsonl 記録済み)。

- Claude Code (07-25、完了): **山札レース評価レーン**。`deck_race_weight` の事前登録A/B。
  基準 `build/v4.3a-fixed2`(weight=0) → 候補 `build/v4.7a-deckrace-fixed2`(weight=0.01)、
  どちらも `build/wall-kang-bc`(bc_kang純BC)へ各200戦、fixed-worlds、-j 8。
  **両アームを途中結果に関わらず実行する**。両ビルドは`bc_search.py`が完全同一で設定1項のみ差分。
  ⚠️ 完了までCPUを食う重い評価を並走させないこと。

**未了の測定(次に誰かが拾うもの)**: `build/v4.3a-bc`(純BC) vs
`build/wall-grim-top8-fixed2`(探索付きGrim壁)は取得済み(38.0%/200)。
残るは両者探索版(約2時間、優先度低)。
400戦(両者探索・約2時間)と200戦(自陣純BC・約40分)を2回とも外部から停止されたため未取得。
台帳・プロセスは汚れていない(partial書き込みなし)。再開時は**より小さいnか、空いている時間帯**で。


## 今日の提出枠

- 08-10: **2/5 使用** (`v5.4g` sub 55399895 COMPLETE / `v5.1g再` sub 55403337 復旧再提出)
- 07-25: **1/5 使用** (`v4.3h`, sub 54968749, COMPLETE)
- 07-24: **0/5 使用**（提出なし）
- 07-23: **0/5 使用**（提出なし）
- 07-22: **0/5 使用**（提出なし）
- 07-16: **1/5 使用** (`v4.3a`, sub 54731784, COMPLETE)
- 07-15: 0/5使用
- 07-14: 1/5使用 (`v4.2t`, sub 54688865, COMPLETE)
