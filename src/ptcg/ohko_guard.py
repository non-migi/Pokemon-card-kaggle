"""一撃死圏へ主力をアクティブへ出す悪手を防ぐ床(floor)。

2026-08-10のLopunny/Ogerpon敗戦調査(13敗中9試合19局面)で特定した悪手:

    相手の可視情報から計算できる一撃死ダメージ圏内へ、進化直後または入れ替えで
    Grimmsnarl系統をアクティブに出す。ベンチに身代わりにできる低価値ポケモンが
    いるのに使わない。

これを「観測だけで確定計算できる打点」に限って禁止する。expert_rules.py と違い
探索(bcs)を前提にせず**純BC経路で使う**ための軽量フックで、
agent_config.jsonの`ohko_guard`が無ければ完全なno-op(既存agentは一切変わらない)。

保守側(発火しない側)に倒した点:
- 打点はOgerpon exとMega Lopunny exの2枚だけ。他のカードは脅威0として扱う。
- 相手の次ターンのエネ加速(Teal Dance)や、自分が後からPunk Upで乗せるエネは数えない。
- 抵抗力・スタジアム・道具・特性による打点補正は無視する。
- リトリート宣言(OptionType RETREAT)自体は対象にしない。誰が上がるかは
  直後のSWITCH選択で決まるので、そちらだけを見る。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

# SelectType / OptionType / AreaType / SelectContext。
# コンペ中にenumが増えても未知intは非発火にする。
ST_MAIN, ST_CARD, ST_EVOLVE = 0, 1, 7
OT_CARD, OT_EVOLVE = 3, 9
AR_HAND, AR_ACTIVE, AR_BENCH = 2, 4, 5
CTX_SWITCH, CTX_TO_ACTIVE, CTX_EVOLVE = 3, 4, 37

# 打点が確定計算できる相手のカード。
OGERPON = 96              # Teal Mask Ogerpon ex
OGERPON_ATTACK_COST = 3   # Myriad Leaf Shower {G}{G}{G}
OGERPON_BASE = 30         # 基礎30 + 両者アクティブの合計エネ×30
OGERPON_PER_ENERGY = 30
LOPUNNY = 849             # Mega Lopunny ex
GALE_THRUST_MOVED = 230   # ベンチ→バトル場へ動いた番だけ 60+170
SPIKY_HOPPER = 160        # {C}{C}
GALE_THRUST_BASE = 60     # {C}

WEAKNESS_MULTIPLIER = 2

RULE_SWITCH = "GR001_OHKO_COMMIT_AVOID"
RULE_EVOLVE = "GR002_OHKO_EVOLVE_AVOID"
KNOWN_RULE_IDS = (RULE_SWITCH, RULE_EVOLVE)

Action = tuple[int, ...]


@dataclass(frozen=True)
class GuardConfig:
    """agent_config.jsonの`ohko_guard`を正規化したもの。"""

    rule_ids: tuple[str, ...]

    def enabled(self, rule_id: str) -> bool:
        return rule_id in self.rule_ids


def from_config(config: Mapping) -> GuardConfig | None:
    """設定を検証して返す。未指定/無効ならNone(=完全なno-op)。

    受け付ける形:
      未指定 / false            -> None
      true                      -> 全ルール有効
      {"enabled": bool,
       "rules": ["GR001_..."]}  -> 明示指定(rules省略で全ルール)
    """
    raw = config.get("ohko_guard") if isinstance(config, Mapping) else None
    if raw is None or raw is False:
        return None
    if raw is True:
        return GuardConfig(KNOWN_RULE_IDS)
    if not isinstance(raw, Mapping):
        raise ValueError("ohko_guardはbooleanまたはobject")
    if not bool(raw.get("enabled", True)):
        return None
    rules = raw.get("rules")
    if rules is None:
        return GuardConfig(KNOWN_RULE_IDS)
    if isinstance(rules, (str, bytes)) or not isinstance(rules, (list, tuple)):
        raise ValueError("ohko_guard.rulesは文字列の配列")
    ids = tuple(rules)
    if (not ids or any(not isinstance(x, str) or not x for x in ids)
            or len(set(ids)) != len(ids)):
        raise ValueError("ohko_guard.rulesは1件以上・重複なしの非空文字列配列")
    unknown = set(ids) - set(KNOWN_RULE_IDS)
    if unknown:
        raise ValueError(f"未知のohko_guard rule ID: {sorted(unknown)}")
    return GuardConfig(ids)


def build_card_info(cards: Mapping[int, object]) -> dict[int, dict]:
    """cg card metadataから打点計算に要る安定値だけを抽出する。"""
    info = {}
    for raw_id, card in cards.items():
        try:
            card_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        weakness = getattr(card, "weakness", None)
        try:
            weakness = int(weakness) if weakness is not None else None
        except (TypeError, ValueError):
            weakness = None
        try:
            energy_type = int(getattr(card, "energyType", -1))
        except (TypeError, ValueError):
            energy_type = -1
        try:
            max_hp = int(getattr(card, "hp", 0) or 0)
        except (TypeError, ValueError):
            max_hp = 0
        if getattr(card, "megaEx", False):
            prize = 3
        elif getattr(card, "ex", False):
            prize = 2
        else:
            prize = 1
        info[card_id] = {
            "max_hp": max_hp,
            "weakness": weakness,
            "energy_type": energy_type,
            "prize": prize,
        }
    return info


def _int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _energy_count(pokemon: Mapping) -> int:
    energies = pokemon.get("energies")
    return len(energies) if isinstance(energies, (list, tuple)) else 0


def _apply_weakness(damage: int, defender_weakness, attacker_type: int) -> int:
    if defender_weakness is not None and int(defender_weakness) == attacker_type:
        return damage * WEAKNESS_MULTIPLIER
    return damage


def max_incoming_damage(
    opponent: Mapping, defender_weakness, defender_energy_count: int,
    card_info: Mapping[int, dict],
) -> int:
    """相手が次のターンに与えられる、観測から確定計算できる最大打点。

    defender_energy_count は「アクティブに立ったときの自分のエネ数」。
    Myriad Leaf Showerは**両者のアクティブ**の合計エネを数えるので、
    どのポケモンを出すかで被ダメが変わる。
    """
    best = 0
    active = [p for p in (opponent.get("active") or []) if isinstance(p, Mapping)]
    bench = [p for p in (opponent.get("bench") or []) if isinstance(p, Mapping)]
    for pokemon, on_bench in [(p, False) for p in active] + [(p, True) for p in bench]:
        card_id = _int(pokemon.get("id"), -1)
        energies = _energy_count(pokemon)
        if card_id == OGERPON:
            if energies < OGERPON_ATTACK_COST:
                continue  # コスト未達。Teal Danceの加速は数えない(保守側)
            damage = OGERPON_BASE + OGERPON_PER_ENERGY * (
                energies + max(0, defender_energy_count)
            )
        elif card_id == LOPUNNY:
            if on_bench:
                # ベンチにいる限り、上げてきた番はGale Thrustが230になる。
                damage = GALE_THRUST_MOVED if energies >= 1 else 0
            elif energies >= 2:
                damage = SPIKY_HOPPER
            elif energies >= 1:
                damage = GALE_THRUST_BASE  # 既にアクティブなら移動ボーナスは乗らない
            else:
                damage = 0
            if damage <= 0:
                continue
        else:
            continue
        attacker_type = _int(card_info.get(card_id, {}).get("energy_type"), -1)
        best = max(best, _apply_weakness(damage, defender_weakness, attacker_type))
    return best


def _players(obs_dict: Mapping) -> tuple[dict, dict, int] | None:
    try:
        cur = obs_dict["current"]
        your_index = int(cur["yourIndex"])
        players = cur["players"]
        if your_index not in (0, 1) or len(players) < 2:
            return None
        mine, opponent = players[your_index], players[1 - your_index]
    except (KeyError, TypeError, ValueError, IndexError):
        return None
    if not isinstance(mine, Mapping) or not isinstance(opponent, Mapping):
        return None
    return mine, opponent, your_index


def _switch_forbidden(
    sel: Mapping, mine: Mapping, opponent: Mapping, your_index: int,
    card_info: Mapping[int, dict],
) -> set[Action]:
    """昇格/入れ替えで「死ぬ主力」を、より安い身代わりがあるのに出す手を禁止する。"""
    options = sel.get("option") or []
    bench = mine.get("bench") or []
    entries = []
    for i, option in enumerate(options):
        if not isinstance(option, Mapping):
            return set()
        if (option.get("type") != OT_CARD or option.get("area") != AR_BENCH
                or _int(option.get("playerIndex"), -1) != your_index):
            return set()  # 相手ベンチ指定(Boss's Orders等)や未知形式は非発火
        try:
            pokemon = bench[_int(option["index"], -1)]
        except (KeyError, IndexError):
            return set()
        if not isinstance(pokemon, Mapping):
            return set()
        info = card_info.get(_int(pokemon.get("id"), -1))
        if info is None:
            return set()  # 語彙外カードは評価しない
        energies = _energy_count(pokemon)
        damage = max_incoming_damage(
            opponent, info["weakness"], energies, card_info,
        )
        hp = _int(pokemon.get("hp"), 0)
        entries.append((i, int(info["prize"]), hp > 0 and damage >= hp))
    if not entries:
        return set()
    forbidden = set()
    for i, prize, dies in entries:
        if not dies:
            continue
        # 「より安い身代わり」= 取られるサイドが少ない、または
        # 同値以下で生き残る候補。これがあるときだけ禁止する(最小介入)。
        if any(
            j != i and (other_prize < prize
                        or (not other_dies and other_prize <= prize))
            for j, other_prize, other_dies in entries
        ):
            forbidden.add((i,))
    return forbidden


def _evolve_forbidden(
    sel: Mapping, mine: Mapping, opponent: Mapping,
    card_info: Mapping[int, dict],
) -> set[Action]:
    """アクティブを、一撃死圏内のより高いサイド値へ進化させる手を禁止する。"""
    active = [p for p in (mine.get("active") or []) if isinstance(p, Mapping)]
    if len(active) != 1:
        return set()
    current = active[0]
    current_info = card_info.get(_int(current.get("id"), -1))
    if current_info is None:
        return set()
    hand = mine.get("hand")
    if not isinstance(hand, (list, tuple)):
        return set()  # 自分の手札が見えない観測(相手席視点)では評価しない
    energies = _energy_count(current)
    damage_taken = max(0, _int(current.get("maxHp"), 0) - _int(current.get("hp"), 0))
    forbidden = set()
    for i, option in enumerate(sel.get("option") or []):
        if not isinstance(option, Mapping):
            continue
        if (option.get("type") != OT_EVOLVE
                or option.get("inPlayArea") != AR_ACTIVE
                or _int(option.get("inPlayIndex"), -1) != 0
                or option.get("area") != AR_HAND):
            continue
        try:
            card = hand[_int(option["index"], -1)]
        except (KeyError, IndexError):
            continue
        if not isinstance(card, Mapping):
            continue
        info = card_info.get(_int(card.get("id"), -1))
        if info is None:
            continue
        if int(info["prize"]) <= int(current_info["prize"]):
            continue  # サイド枚数が増えないなら進化を止める理由がない
        effective_hp = int(info["max_hp"]) - damage_taken
        damage = max_incoming_damage(
            opponent, info["weakness"], energies, card_info,
        )
        if effective_hp > 0 and damage >= effective_hp:
            forbidden.add((i,))
    return forbidden


def forbidden_actions(
    cfg: GuardConfig | None, obs_dict: Mapping,
    card_info: Mapping[int, dict], metrics: dict | None = None,
) -> frozenset[Action]:
    """現在の選択で禁止する行動集合。無効/対象外なら空集合。

    呼び手は例外を握ってBC選択へフォールバックすること(main.py参照)。
    """
    if cfg is None:
        return frozenset()
    sel = obs_dict.get("select")
    if not isinstance(sel, Mapping):
        return frozenset()
    options = sel.get("option") or []
    # 単数選択だけを対象にする(複数選択のマスクはBC側が扱えない)。
    if _int(sel.get("maxCount"), 0) != 1 or _int(sel.get("minCount"), 0) > 1:
        return frozenset()
    if len(options) < 2:
        return frozenset()
    players = _players(obs_dict)
    if players is None:
        return frozenset()
    mine, opponent, your_index = players

    select_type = sel.get("type")
    context = sel.get("context")
    forbidden: set[Action] = set()
    rule_id = None
    if (select_type == ST_CARD and context in (CTX_SWITCH, CTX_TO_ACTIVE)
            and cfg.enabled(RULE_SWITCH)):
        rule_id = RULE_SWITCH
        forbidden = _switch_forbidden(sel, mine, opponent, your_index, card_info)
    elif ((select_type == ST_MAIN and context == 0)
            or (select_type == ST_EVOLVE and context == CTX_EVOLVE)):
        if not cfg.enabled(RULE_EVOLVE):
            return frozenset()
        rule_id = RULE_EVOLVE
        forbidden = _evolve_forbidden(sel, mine, opponent, card_info)

    if not forbidden:
        return frozenset()
    if len(forbidden) >= len(options):
        # 全選択肢を潰すと試合が壊れる。安全網として丸ごと無効化する。
        if metrics is not None:
            metrics["ohko_guard_suppressed"] = int(
                metrics.get("ohko_guard_suppressed", 0)) + 1
        return frozenset()
    if metrics is not None and rule_id is not None:
        key = f"ohko_guard_hit.{rule_id}"
        metrics[key] = int(metrics.get(key, 0)) + 1
    return frozenset(forbidden)


def describe(forbidden: Iterable[Action]) -> str:
    """ログ用の短い説明(デバッグツールから使う)。"""
    return ",".join(str(list(a)) for a in sorted(forbidden))
