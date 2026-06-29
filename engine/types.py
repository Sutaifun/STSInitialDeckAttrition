"""局面与求解结果类型（多重集表示）。"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Tuple

# (打击, 防御, 痛击, 诅咒)
Pile = Tuple[int, int, int, int]

EMPTY_PILE: Pile = (0, 0, 0, 0)
MAX_TURNS = 8
MAX_DAMAGE = 200
ENERGY_PER_TURN = 3
HAND_SIZE = 5


@dataclass(frozen=True)
class State:
    """玩家回合初（已抽牌后）的完整局面。"""

    enemy_hp: int
    enemy_block: int
    enemy_strength: int
    enemy_vulnerable: int
    intent_index: int

    player_block: int
    player_vulnerable: int
    player_weak: int
    player_frail: int
    player_strength: int
    player_dexterity: int

    damage_taken: int
    turn_count: int
    energy: int

    hand: Pile
    draw: Pile
    discard: Pile
    exhaust: Pile

    # 本回合开始时上手牌（用于回合末弃牌，与出牌无关）
    hand_at_turn_start: Pile


@dataclass(frozen=True)
class SolveResult:
    """solve_state 的输出。"""

    min_damage: int
    play_path: Tuple[str, ...]
    end_state: State | None
    combat_over: bool


@dataclass(frozen=True)
class TurnTrace:
    """单回合最优出牌明细（用于路线导出）。"""

    turn: int
    hand: Pile  # 本回合抽到的上手牌（多重集）
    plays: Tuple[str, ...]  # 按序打出的牌（S/D/B；诅咒不可打出故不出现）
    damage_after: int  # 本回合结束后的累计战损（含本回合敌人攻击；若本回合击杀则不含）
    enemy_hp_after_plays: int  # 本回合出牌后的敌人 HP（敌人行动不改其 HP）


@dataclass(frozen=True)
class PathResult:
    """单条抽牌路线 ω 的完整结果（用于 JSONL 导出）。"""

    weight: Fraction  # w(ω)，组合权重（精确分数）
    min_damage: int  # D(ω)，最优总战损
    opening_hand: Pile  # 第 1 回合上手
    turns: Tuple[TurnTrace, ...]
