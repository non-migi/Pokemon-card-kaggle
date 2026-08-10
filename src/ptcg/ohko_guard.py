"""一撃死圏へ主力をアクティブへ出す悪手を防ぐ床(floor)。

2026-08-10のLopunny/Ogerpon敗戦調査(13敗中12試合34局面=敗戦の92%に関与)で
特定した悪手:

    相手の可視情報から計算できる一撃死ダメージ圏内へ、進化 / 自発的入れ替え /
    **KO後のベンチ→アクティブ昇格** でGrimmsnarl系統をアクティブに出す。
    ベンチに身代わりにできる低価値ポケモンがいるのに使わない。

これを「観測だけで確定計算できる打点」に限って禁止する。expert_rules.py と違い
探索(bcs)を前提にせず**純BC経路で使う**ための軽量フックで、
agent_config.jsonの`ohko_guard`が無ければ完全なno-op(既存agentは一切変わらない)。

ルールは2段構え:
- 1段目(GR001/GR002、**既定で有効**): 主力が一撃死圏で、
  より安い身代わりがあるなら主力を出さない。
- 2段目(GR003、**既定では無効。明示指定でのみ有効**): **どの候補も一撃死圏**なら、
  どうせ死ぬので「攻撃できる候補」を優先する。

⚠️ GR003を既定から外している理由(2026-08-10、過去リプレイ2,503判断での実測):
GR001/GR002が止めた手は12試合すべて敗戦だったのに対し、GR003が止めた手には
**勝ち試合も混ざり**、内容も「10ダメージのCorkscrew Punchが撃てるだけの
Impidimp(70)を、Morgrem(100)やMunkidori(110)より優先して昇格させる」という
筋の悪いものが含まれた(ep 90763519 T7 / ep 90042676 T7)。
「攻撃できる」を真偽値で扱うと打点1発10点でも勝ってしまうのが原因。
打点の大きさや進化ラインの温存を条件に入れるまで、既定では使わない。

保守側(発火しない側)に倒した点:
- 打点はOgerpon exとMega Lopunny exの2枚だけ。他のカードは脅威0として扱う。
- 相手の次ターンのエネ加速(Teal Dance)や、自分が後からPunk Upで乗せるエネは数えない。
- 抵抗力・スタジアム・道具・特性による打点補正は無視する。
- リトリート宣言(OptionType RETREAT)自体は対象にしない。誰が上がるかは
  直後のSWITCH選択で決まるので、そちらだけを見る。

発火の可観測性: モジュール変数 `METRICS` に全カウンタを積む
(「クラッシュせずに100% no-opだった」を後から誤帰属しないため)。
arenaは main.AGENT_METRICS 経由で同じ値を集計する。
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

# コスト計算でどの型にも使えると見なすenergy(過大評価=攻撃可能側に倒す。
# 「攻撃できない」と誤判定して候補を禁止する方が害が大きいため)。
COLORLESS = 0
WILDCARD_ENERGY = frozenset({10, 11})  # RAINBOW / TEAM_ROCKET

RULE_SWITCH = "GR001_OHKO_COMMIT_AVOID"
RULE_EVOLVE = "GR002_OHKO_EVOLVE_AVOID"
RULE_ATTACKER = "GR003_OHKO_ALL_DEAD_PREFER_ATTACKER"
KNOWN_RULE_IDS = (RULE_SWITCH, RULE_EVOLVE, RULE_ATTACKER)
# `true` や rules 省略で有効になるのはここだけ。GR003は上記の理由で明示指定制。
DEFAULT_RULE_IDS = (RULE_SWITCH, RULE_EVOLVE)

Action = tuple[int, ...]

# プロセス内カウンタ。ローカル評価/テストから素で参照できるようにしておく。
METRICS: dict[str, int] = {}


def reset_metrics() -> None:
    METRICS.clear()


def _inc(metrics: dict | None, key: str, amount: int = 1) -> None:
    METRICS[key] = int(METRICS.get(key, 0)) + amount
    if metrics is not None:
        metrics[key] = int(metrics.get(key, 0)) + amount


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
      true                      -> 既定ルール(DEFAULT_RULE_IDS)を有効
      {"enabled": bool,
       "rules": ["GR001_..."]}  -> 明示指定(rules省略で既定ルール)
    """
    raw = config.get("ohko_guard") if isinstance(config, Mapping) else None
    if raw is None or raw is False:
        return None
    if raw is True:
        return GuardConfig(DEFAULT_RULE_IDS)
    if not isinstance(raw, Mapping):
        raise ValueError("ohko_guardはbooleanまたはobject")
    if not bool(raw.get("enabled", True)):
        return None
    rules = raw.get("rules")
    if rules is None:
        return GuardConfig(DEFAULT_RULE_IDS)
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


def build_card_info(
    cards: Mapping[int, object], attacks: Mapping[int, object] | None = None,
) -> dict[int, dict]:
    """cg card metadataから打点計算に要る安定値だけを抽出する。

    attacks(attackId -> Attack)を渡すと、GR003が使う
    「ダメージの出るワザのコスト一覧」も併せて抽出する。
    """
    attacks = attacks or {}
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
        costs = []
        for attack_id in getattr(card, "attacks", ()) or ():
            attack = attacks.get(attack_id)
            if attack is None:
                continue
            try:
                damage = int(getattr(attack, "damage", 0) or 0)
                cost = tuple(int(e) for e in getattr(attack, "energies", ()) or ())
            except (TypeError, ValueError):
                continue
            if damage > 0:
                costs.append(cost)
        info[card_id] = {
            "max_hp": max_hp,
            "weakness": weakness,
            "energy_type": energy_type,
            "prize": prize,
            "attack_costs": tuple(costs),
        }
    return info


def _can_pay(attached: Iterable[int], cost: Iterable[int]) -> bool:
    """付いているenergyでワザのコストを払えるか。"""
    need: dict[int, int] = {}
    colorless = 0
    for energy in cost:
        if energy == COLORLESS:
            colorless += 1
        else:
            need[energy] = need.get(energy, 0) + 1
    typed: dict[int, int] = {}
    wild = 0
    for energy in attached:
        if energy in WILDCARD_ENERGY:
            wild += 1
        else:
            typed[energy] = typed.get(energy, 0) + 1
    for energy, count in need.items():
        have = typed.get(energy, 0)
        used = min(have, count)
        typed[energy] = have - used
        shortfall = count - used
        if shortfall:
            if wild < shortfall:
                return False
            wild -= shortfall
    return sum(typed.values()) + wild >= colorless


def can_attack(pokemon: Mapping, info: Mapping) -> bool:
    """今付いているenergyだけで、ダメージの出るワザを撃てるか。

    attack_costsが無い(古い形式のcard_info)ときは、判定不能として
    「撃てる」を返す — GR003が誤って候補を禁止する方を避ける。
    """
    costs = info.get("attack_costs")
    if not costs:
        return True
    attached = pokemon.get("energies")
    attached = list(attached) if isinstance(attached, (list, tuple)) else []
    return any(_can_pay(attached, cost) for cost in costs)


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
    cfg: GuardConfig, sel: Mapping, mine: Mapping, opponent: Mapping,
    your_index: int, card_info: Mapping[int, dict],
) -> dict[Action, str]:
    """昇格(KO後を含む)/入れ替えの候補選択を2段構えで絞る。

    1段目 GR001: 死ぬ主力を、より安い身代わりがあるのに出す手を禁止する。
    2段目 GR003: 全候補が死ぬなら、同じサイド枚数の中で
                 攻撃できない候補(攻撃できる候補があるとき)を禁止する。
    """
    options = sel.get("option") or []
    bench = mine.get("bench") or []
    entries = []
    for i, option in enumerate(options):
        if not isinstance(option, Mapping):
            return {}
        if (option.get("type") != OT_CARD or option.get("area") != AR_BENCH
                or _int(option.get("playerIndex"), -1) != your_index):
            return {}  # 相手ベンチ指定(Boss's Orders等)や未知形式は非発火
        try:
            pokemon = bench[_int(option["index"], -1)]
        except (KeyError, IndexError):
            return {}
        if not isinstance(pokemon, Mapping):
            return {}
        info = card_info.get(_int(pokemon.get("id"), -1))
        if info is None:
            return {}  # 語彙外カードは評価しない
        energies = _energy_count(pokemon)
        damage = max_incoming_damage(
            opponent, info["weakness"], energies, card_info,
        )
        hp = _int(pokemon.get("hp"), 0)
        entries.append((
            i, int(info["prize"]), hp > 0 and damage >= hp,
            can_attack(pokemon, info),
        ))
    if not entries:
        return {}
    all_dead = all(dies for _, _, dies, _ in entries)
    forbidden: dict[Action, str] = {}
    for i, prize, dies, attacks_now in entries:
        if not dies:
            continue
        # 1段目: 「より安い身代わり」= 取られるサイドが少ない、または
        # 同値以下で生き残る候補。これがあるときだけ禁止する(最小介入)。
        if cfg.enabled(RULE_SWITCH) and any(
            j != i and (other_prize < prize
                        or (not other_dies and other_prize <= prize))
            for j, other_prize, other_dies, _ in entries
        ):
            forbidden[(i,)] = RULE_SWITCH
            continue
        # 2段目: どうせ全員死ぬなら、同じサイド枚数で攻撃できる方を出す。
        if (cfg.enabled(RULE_ATTACKER) and all_dead and not attacks_now
                and any(
                    j != i and other_prize == prize and other_attacks
                    for j, other_prize, _, other_attacks in entries
                )):
            forbidden[(i,)] = RULE_ATTACKER
    return forbidden


def _evolve_forbidden(
    sel: Mapping, mine: Mapping, opponent: Mapping,
    card_info: Mapping[int, dict],
) -> dict[Action, str]:
    """アクティブを、一撃死圏内のより高いサイド値へ進化させる手を禁止する。"""
    active = [p for p in (mine.get("active") or []) if isinstance(p, Mapping)]
    if len(active) != 1:
        return {}
    current = active[0]
    current_info = card_info.get(_int(current.get("id"), -1))
    if current_info is None:
        return {}
    hand = mine.get("hand")
    if not isinstance(hand, (list, tuple)):
        return {}  # 自分の手札が見えない観測(相手席視点)では評価しない
    energies = _energy_count(current)
    damage_taken = max(0, _int(current.get("maxHp"), 0) - _int(current.get("hp"), 0))
    forbidden: dict[Action, str] = {}
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
            forbidden[(i,)] = RULE_EVOLVE
    return forbidden


def _forbidden_actions(
    cfg: GuardConfig, obs_dict: Mapping,
    card_info: Mapping[int, dict], metrics: dict | None,
) -> frozenset[Action]:
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
    forbidden: dict[Action, str] = {}
    if select_type == ST_CARD and context in (CTX_SWITCH, CTX_TO_ACTIVE):
        if not (cfg.enabled(RULE_SWITCH) or cfg.enabled(RULE_ATTACKER)):
            return frozenset()
        _inc(metrics, "ohko_guard_scanned.switch")
        forbidden = _switch_forbidden(
            cfg, sel, mine, opponent, your_index, card_info,
        )
    elif ((select_type == ST_MAIN and context == 0)
            or (select_type == ST_EVOLVE and context == CTX_EVOLVE)):
        if not cfg.enabled(RULE_EVOLVE):
            return frozenset()
        _inc(metrics, "ohko_guard_scanned.evolve")
        forbidden = _evolve_forbidden(sel, mine, opponent, card_info)

    if not forbidden:
        return frozenset()
    if len(forbidden) >= len(options):
        # 全選択肢を潰すと試合が壊れる。安全網として丸ごと無効化する。
        _inc(metrics, "ohko_guard_suppressed")
        return frozenset()
    for rule_id in sorted(set(forbidden.values())):
        _inc(metrics, f"ohko_guard_hit.{rule_id}")
    _inc(metrics, "ohko_guard_fired")
    _inc(metrics, "ohko_guard_options_forbidden", len(forbidden))
    return frozenset(forbidden)


def forbidden_actions(
    cfg: GuardConfig | None, obs_dict: Mapping,
    card_info: Mapping[int, dict], metrics: dict | None = None,
) -> frozenset[Action]:
    """現在の選択で禁止する行動集合。無効/対象外なら空集合。

    ルール内のいかなる例外でも試合を壊さないよう、ここで握って空集合を返す
    (呼び手側=main.pyにも二重の握りがある)。カウンタは METRICS と
    引数metricsの両方へ積む。
    """
    if cfg is None:
        return frozenset()
    _inc(metrics, "ohko_guard_calls")
    try:
        return _forbidden_actions(cfg, obs_dict, card_info, metrics)
    except Exception:
        _inc(metrics, "ohko_guard_errors")
        return frozenset()


def describe(forbidden: Iterable[Action]) -> str:
    """ログ用の短い説明(デバッグツールから使う)。"""
    return ",".join(str(list(a)) for a in sorted(forbidden))
