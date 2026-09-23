"""从 data/{sts1,sts2} 的 JSON 构建引擎所需的牌组/卡牌/遭遇数值，替代硬编码。

设计：本模块只读 JSON，不反向 import 引擎其它模块（避免循环依赖）。
- 数据层用英文 snake_case id（strike/defend/bash/ascenders_bane/seapunk…）。
- 引擎层用 5 槽多重集 Pile，槽位代码 (S,D,B,X,M)；二者用 CARD_ID_TO_CODE 适配。
- 进阶档：标量两档相同直接取；{low, high} 取对应档（塔2 A10 用 "high"，塔1 A20 用 "high"）。

详见 docs/游戏数据格式.md。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

DATA_STS2 = Path(__file__).resolve().parents[1] / "data" / "sts2"
DATA_STS1 = Path(__file__).resolve().parents[1] / "data" / "sts1"
DATA_ROOT = DATA_STS2  # 试点默认根（向后兼容）

# 数据卡 id → 引擎 Pile 槽位代码（表示层适配，非数值数据）。
CARD_ID_TO_CODE: dict[str, str] = {
    "strike": "S",
    "defend": "D",
    "bash": "B",
    "ascenders_bane": "X",
    "slimed": "M",
}
# 与 engine.deck.CARD_ORDER 对齐的槽位顺序。
CODE_ORDER: tuple[str, ...] = ("S", "D", "B", "X", "M")
_CODE_INDEX = {c: i for i, c in enumerate(CODE_ORDER)}

A10 = "high"  # 塔2 高进阶档对应 A10
A20 = "high"  # 塔1 高进阶档对应 A20
GameId = Literal["sts1", "sts2"]


def data_root_for(game: GameId) -> Path:
    return DATA_STS1 if game == "sts1" else DATA_STS2


def _asc(value, ascension: str):
    """取进阶档数值：{low, high} 取对应档；标量原样返回。"""
    if isinstance(value, dict) and ("low" in value or "high" in value):
        return value[ascension]
    return value


def _read_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_card(card_id: str, root: Path = DATA_ROOT) -> dict:
    return _read_json(root / "cards" / f"{card_id}.json")


def load_character(character_id: str = "ironclad", root: Path = DATA_ROOT) -> dict:
    return _read_json(root / "characters" / f"{character_id}.json")


def load_encounter(encounter_id: str = "seapunk", root: Path = DATA_ROOT) -> dict:
    return _read_json(root / "encounters" / f"{encounter_id}.json")


def build_deck_pile(
    character_id: str = "ironclad", root: Path = DATA_ROOT
) -> tuple[int, int, int, int, int]:
    """角色初始牌组 → Pile (打击, 防御, 痛击, 诅咒, 粘液)。"""
    char = load_character(character_id, root)
    pile = [0, 0, 0, 0, 0]
    for entry in char["starting_deck"]:
        code = CARD_ID_TO_CODE[entry["card"]]
        pile[_CODE_INDEX[code]] += entry["count"]
    return tuple(pile)  # type: ignore[return-value]


def build_opening_params(
    character_id: str = "ironclad", root: Path = DATA_ROOT
) -> tuple[int, int]:
    """(regular_hand_size, opening_hand_size) 来自 first_fight_model.draw。"""
    char = load_character(character_id, root)
    draw = char.get("first_fight_model", {}).get("draw", {})
    regular = int(draw.get("regular_hand_size", 5))
    opening = int(draw.get("opening_hand_size", regular))
    return regular, opening


def encounter_has_add_status_to_discard(encounter: dict) -> bool:
    """遭遇任一技能含 add_status_to_discard 则 True。"""
    kinds = encounter.get("monster_kinds", {})
    for kind in kinds.values():
        for move in kind.get("moves", []):
            for eff in move.get("effects", []):
                if eff.get("type") == "add_status_to_discard":
                    return True
    monsters = encounter.get("monsters", [])
    for m in monsters:
        for move in m.get("moves", []):
            for eff in move.get("effects", []):
                if eff.get("type") == "add_status_to_discard":
                    return True
    return False


def build_card_stats(
    root: Path = DATA_ROOT,
) -> tuple[
    dict[str, int | None],
    dict[str, int],
    dict[str, int],
    dict[str, int],
]:
    """
    读取 cards/*.json，按槽位代码返回：
      cost[code]  费用（不可打出/无费用为 None）
      damage[code] 攻击单段基础伤害（无则缺省）
      block[code]  技能基础格挡（无则缺省）
      vulnerable[code] 施加易伤层数（无则缺省）
    """
    cost: dict[str, int | None] = {}
    damage: dict[str, int] = {}
    block: dict[str, int] = {}
    vulnerable: dict[str, int] = {}
    cards_dir = root / "cards"
    for card_path in sorted(cards_dir.glob("*.json")):
        card_id = card_path.stem
        code = CARD_ID_TO_CODE.get(card_id)
        if code is None:
            continue
        c = _read_json(card_path)
        cost[code] = c.get("cost")
        if "damage" in c:
            damage[code] = c["damage"]
        if "block" in c:
            block[code] = c["block"]
        for eff in c.get("effects", []):
            if eff.get("type") == "apply_vulnerable":
                vulnerable[code] = eff["amount"]
    return cost, damage, block, vulnerable


def _find_monster(encounter: dict, monster_id: str | None) -> dict:
    monsters = encounter["monsters"]
    if monster_id is None:
        return monsters[0]
    for m in monsters:
        if m["id"] == monster_id:
            return m
    raise KeyError(f"怪物 {monster_id} 不在遭遇 {encounter.get('id')} 中")


def build_intents(
    encounter_id: str = "seapunk",
    monster_id: str | None = None,
    ascension: str = A10,
    root: Path = DATA_ROOT,
) -> tuple[dict, ...]:
    """
    构建敌人意图循环（与 combat.SEAPUNK_INTENTS 同形）：
      attack      → {"kind": "attack", "damage": d, "hits": h}
      defend_buff → {"kind": "buff", "block": b, "strength": s}

    引擎以 intent_index 从 0 起按 cycle 取模循环；故要求 opening == cycle[0]
    （本试点满足）。意图序列即 cycle 各招式。
    """
    monster = _find_monster(load_encounter(encounter_id, root), monster_id)
    moves = {m["id"]: m for m in monster["moves"]}
    pattern = monster["pattern"]
    if pattern.get("opening") != pattern["cycle"][0]:
        raise ValueError(
            "当前引擎仅支持 opening == cycle[0] 的意图循环；"
            f"该怪 opening={pattern.get('opening')} cycle={pattern['cycle']}"
        )

    intents: list[dict] = []
    for move_id in pattern["cycle"]:
        m = moves[move_id]
        kind = m["intent"]
        if kind == "attack":
            intents.append(
                {
                    "kind": "attack",
                    "damage": _asc(m["damage"], ascension),
                    "hits": m["hits"],
                }
            )
        elif kind == "defend_buff":
            intents.append(
                {
                    "kind": "buff",
                    "block": _asc(m["block"], ascension),
                    "strength": _asc(m["strength"], ascension),
                }
            )
        else:
            raise ValueError(f"未知意图类型 {kind}")
    return tuple(intents)


def build_hp_range(
    encounter_id: str = "seapunk",
    monster_id: str | None = None,
    ascension: str = A10,
    root: Path = DATA_ROOT,
) -> tuple[int, int]:
    """怪物在指定进阶档的 HP 枚举区间 (min, max)（含端点）。"""
    monster = _find_monster(load_encounter(encounter_id, root), monster_id)
    band = monster["max_hp"][ascension]
    return band["min"], band["max"]
