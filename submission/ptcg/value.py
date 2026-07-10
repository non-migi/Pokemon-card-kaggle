"""学習済み価値関数(勝率予測)の推論。純Python・依存なし。

value_params.py(train_value.pyが生成)が無い/特徴量バージョン不一致なら
無効(win_probはNoneを返す)となり、呼び手は従来のロジックにフォールバックする。
"""

import math

from .features import extract, FEATURE_VERSION, N_FEATURES

try:
    from . import value_params as _P

    ENABLED = (_P.FEATURE_VERSION == FEATURE_VERSION and len(_P.W) == N_FEATURES)
except Exception:
    _P = None
    ENABLED = False


def win_prob(cur, my_index: int) -> float | None:
    """盤面から自分の勝率を予測。モデル無効ならNone。"""
    if not ENABLED:
        return None
    try:
        f = extract(cur, my_index)
        z = _P.B
        for w, x, m, s in zip(_P.W, f, _P.MU, _P.SD):
            z += w * (x - m) / s
        return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))
    except Exception:
        return None
