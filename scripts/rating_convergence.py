"""レート収束の調査: ガウス(TrueSkill/Glicko様)レーティングフィルタのMonte Carlo。

問い: 「80戦で収束」か、40戦でも足りるか。
方法: 真の実力を持つエージェントが同格マッチングで対戦する過程をベイズ更新でシミュレート。
      推定値の不確かさ σ_n(=表示レートの±幅)を試合数nの関数として測る。
      競技の経験則「80戦で±50同格」に合わせて系をキャリブレーション。

出力: 各nでの推定の広がり、及び「真に50点差の2体を正しく順位付けできる確率」を40戦 vs 80戦で比較。
"""

import numpy as np

RNG = np.random.default_rng(42)
MU0 = 600.0
# 尺度は競技の経験則「80戦で±50同格」に合わせてキャリブレーション(σ(80)≈50)。
# 相対的な形(40 vs 80比・逓減)は尺度に依らず不変。
BETA = 197.0      # 実力→勝率のロジスティック尺度
SIGMA0 = 350.0    # 初期不確かさ(提出直後のσ膨張に対応)
TAU = 9.0         # 1試合ごとの微小ドリフト(σのfloorを作る=非定常ラダー)


def win_prob(mu_a: float, mu_b: float) -> float:
    return 1.0 / (1.0 + 10.0 ** (-(mu_a - mu_b) / (2 * BETA)))


def update(mu: float, var: float, mu_opp: float, var_opp: float, score: float):
    """TrueSkill様のガウス近似1試合更新(自分のμ,σ²を返す)。"""
    c2 = var + var_opp + 2 * BETA * BETA
    p = 1.0 / (1.0 + 10.0 ** (-(mu - mu_opp) / np.sqrt(c2)))
    k = var / c2
    mu_new = mu + k * (score - p) * np.sqrt(c2)
    var_new = var * (1 - k * p * (1 - p))
    var_new += TAU * TAU  # 微小ドリフト(σが0に潰れない=floor)
    return mu_new, var_new


def simulate_one(true_skill: float, n_games: int):
    """同格マッチングで n_games 戦。推定μの軌跡を返す。"""
    mu, var = MU0, SIGMA0 ** 2
    traj = np.empty(n_games)
    for i in range(n_games):
        # 同格マッチング: 相手は現在の推定μ付近(±小ノイズ)、相手は既に収束済み(小σ)と仮定
        mu_opp = mu + RNG.normal(0, 40)
        opp_true = mu_opp  # 相手は自分の推定と同格 = 真値も近い
        score = 1.0 if RNG.random() < win_prob(true_skill, opp_true) else 0.0
        mu, var = update(mu, var, mu_opp, 50.0 ** 2, score)
        traj[i] = mu
    return traj


def main() -> None:
    N = 4000
    n_games = 120
    trials = np.array([simulate_one(MU0 + 60, n_games) for _ in range(N)])
    # 真の実力=660(平衡660)。各nで推定の広がり(=表示レートの信頼幅)
    print(f"真の実力=660, μ0=600, 同格マッチング, {N}試行\n")
    print(f"{'試合数':>6} {'推定平均':>8} {'推定std(±幅)':>12} {'|推定-真|の中央値':>16}")
    checkpoints = [10, 20, 30, 40, 60, 80, 100, 120]
    stds = {}
    for n in checkpoints:
        col = trials[:, n - 1]
        std = col.std()
        stds[n] = std
        med_err = np.median(np.abs(col - 660))
        print(f"{n:>6} {col.mean():>8.0f} {std:>12.1f} {med_err:>16.1f}")

    print(f"\n40戦 vs 80戦の不確かさ比: {stds[40] / stds[80]:.2f}倍 "
          f"(理論 sqrt(80/40)={np.sqrt(2):.2f})")

    # 真に50点差の2体を「各n戦して高い方を勝ち」と判定したとき正しく順位付けできる確率
    print("\n真に50点差(660 vs 610)の2体を、各自n戦の推定レートで比較 → 正しく順位付けできる確率:")
    for n in [20, 40, 60, 80, 120]:
        a = np.array([simulate_one(660, n)[-1] for _ in range(2000)])
        b = np.array([simulate_one(610, n)[-1] for _ in range(2000)])
        # ランダムにペアにして a>b の割合
        correct = (a > b).mean()
        print(f"  n={n:>3}: {correct*100:.1f}%  (推定std≈{stds.get(n, float('nan')):.0f})")


if __name__ == "__main__":
    main()
