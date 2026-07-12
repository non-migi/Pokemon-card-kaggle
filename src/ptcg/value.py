"""学習済み価値網(勝率予測)の推論。numpy MLP(route B)。

value_params.py(train_value_mlp.pyが生成)が無い/特徴量バージョン不一致なら
ENABLED=False(win_probはNone)。呼び手は従来ロジック(ロールアウト)へフォールバック。
numpyは提出物でpolicy.pyが既に使用しており依存増にならない。
"""

import numpy as np

from .features import extract, FEATURE_VERSION, N_FEATURES

ENABLED = False
_W1 = _b1 = _W2 = _b2 = _W3 = _b3 = _MU = _SD = None

try:
    from . import value_params as _P

    if getattr(_P, "FEATURE_VERSION", -1) == FEATURE_VERSION and len(_P.MU) == N_FEATURES:
        _W1 = np.asarray(_P.W1, np.float32); _b1 = np.asarray(_P.b1, np.float32)
        _W2 = np.asarray(_P.W2, np.float32); _b2 = np.asarray(_P.b2, np.float32)
        _W3 = np.asarray(_P.W3, np.float32); _b3 = np.float32(_P.b3)
        _MU = np.asarray(_P.MU, np.float32); _SD = np.asarray(_P.SD, np.float32)
        ENABLED = True
except Exception:
    ENABLED = False


def _forward(x: np.ndarray) -> float:
    xn = (x - _MU) / _SD
    a1 = np.maximum(xn @ _W1 + _b1, 0.0)
    a2 = np.maximum(a1 @ _W2 + _b2, 0.0)
    z = float(a2 @ _W3 + _b3)
    return 1.0 / (1.0 + np.exp(-max(-30.0, min(30.0, z))))


def win_prob(cur, my_index: int) -> float | None:
    """盤面(State)から自分の勝率を予測。モデル無効ならNone。"""
    if not ENABLED:
        return None
    try:
        return _forward(np.asarray(extract(cur, my_index), np.float32))
    except Exception:
        return None
