"""遭遇配置：模式检测、开局参数、试点默认项。"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Literal

from engine.deck import Pile
from engine.load_data import (
    A10,
    A20,
    build_deck_pile,
    build_hp_range,
    build_intents,
    build_opening_params,
    data_root_for,
    encounter_has_add_status_to_discard,
    load_character,
    load_encounter,
)

DrawMode = Literal["independent", "coupled"]


@dataclass(frozen=True)
class EncounterSpec:
    """一场遭遇的求解输入（角色 + 遭遇 + 数据根）。"""

    character_id: str
    encounter_id: str
    game: Literal["sts1", "sts2"]
    ascension: str
    data_root: Path
    starting_deck: Pile
    hand_size: int
    draw_mode: DrawMode
    intents: tuple[dict, ...]
    hp_min: int
    hp_max: int
    # coupled 专用：固定敌人回合表（见 data/sts1/README.md）
    fixed_enemy_turns: tuple[dict, ...] | None = None


def character_uses_coupled_draw(char: dict) -> bool:
    draw = char.get("first_fight_model", {}).get("draw", {})
    coupled = draw.get("discard_pile_coupled_to_plays")
    return coupled not in (None, False, "")


def resolve_draw_mode(encounter: dict, character: dict) -> DrawMode:
    if encounter_has_add_status_to_discard(encounter):
        return "coupled"
    if character_uses_coupled_draw(character):
        return "coupled"
    return "independent"


def build_encounter_spec(
    *,
    character_id: str = "ironclad",
    encounter_id: str = "seapunk",
    game: Literal["sts1", "sts2"] = "sts2",
    ascension: str | None = None,
    variant_id: str | None = None,
) -> EncounterSpec:
    root = data_root_for(game)
    asc = ascension or (A20 if game == "sts1" else A10)
    char = load_character(character_id, root)
    enc = load_encounter(encounter_id, root)
    deck = build_deck_pile(character_id, root)
    hand_size, _ = build_opening_params(character_id, root)
    draw_mode = resolve_draw_mode(enc, char)
    fixed = None
    if draw_mode == "coupled" and encounter_id == "small_slimes" and variant_id == "A":
        fixed = _small_slimes_a_fixed_turns(asc)
        intents: tuple[dict, ...] = ()
        hp_min = hp_max = _small_slimes_a_total_hp(enc, asc)
    else:
        intents = build_intents(encounter_id, ascension=asc, root=root)
        hp_min, hp_max = build_hp_range(encounter_id, ascension=asc, root=root)
    return EncounterSpec(
        character_id=character_id,
        encounter_id=encounter_id,
        game=game,
        ascension=asc,
        data_root=root,
        starting_deck=deck,
        hand_size=hand_size,
        draw_mode=draw_mode,
        intents=intents,
        hp_min=hp_min,
        hp_max=hp_max,
        fixed_enemy_turns=fixed,
    )


def default_pilot_spec() -> EncounterSpec:
    """塔2 铁甲 vs 海洋混混（独立快路径金标）。"""
    return build_encounter_spec(
        character_id="ironclad",
        encounter_id="seapunk",
        game="sts2",
        ascension=A10,
    )


def small_slimes_variant_a_spec(*, ascension: str = "low") -> EncounterSpec:
    """塔1 铁甲 vs 小史莱姆变体 A（耦合原型）。"""
    return build_encounter_spec(
        character_id="ironclad",
        encounter_id="small_slimes",
        game="sts1",
        ascension=ascension,
        variant_id="A",
    )


def _asc(value, ascension: str):
    if isinstance(value, dict) and ("low" in value or "high" in value):
        return value[ascension]
    return value


def _small_slimes_a_fixed_turns(ascension: str) -> tuple[dict, ...]:
    """
    变体 A 固定 AI（尖刺 M + 酸液 S），见 data/sts1/README.md。
    每回合一条：玩家回合结束后结算的总伤害、塞粘液、debuff。
    """
    flame = _asc({"low": 8, "high": 10}, ascension)
    acid_tackle = _asc({"low": 3, "high": 4}, ascension)
    return (
        {
            "damage": flame + acid_tackle,
            "hits": 1,
            "add_slimed": 1,
            "frail": 0,
            "weak": 0,
            "note": "T1 尖刺M Flame Tackle + 酸液S Tackle",
        },
        {
            "damage": acid_tackle,
            "hits": 1,
            "add_slimed": 0,
            "frail": 1,
            "weak": 0,
            "note": "T2+ 尖刺M Lick(虚弱未建模仅 frail) + 酸液S Tackle",
        },
    )


def fixed_enemy_turn_for(spec: EncounterSpec, turn_index: int) -> dict:
    """turn_index 从 1 起；超出固定表则循环末项。"""
    assert spec.fixed_enemy_turns is not None
    turns = spec.fixed_enemy_turns
    if turn_index <= len(turns):
        return turns[turn_index - 1]
    return turns[-1]


def _small_slimes_a_total_hp(enc: dict, ascension: str) -> int:
    """变体 A 两怪 HP 之和（各取 min，与 enumerate_each 一致）。"""
    kinds = enc["composition"]["variants"][0]["monsters"]
    total = 0
    for kind_id in kinds:
        band = enc["monster_kinds"][kind_id]["max_hp"][ascension]
        total += band["min"]
    return total


def small_slimes_a_total_hp(spec: EncounterSpec) -> int:
    enc = load_encounter("small_slimes", spec.data_root)
    return _small_slimes_a_total_hp(enc, spec.ascension)
