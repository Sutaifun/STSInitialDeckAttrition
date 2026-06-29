"""局面与求解结果类型（多重集表示）。"""

from __future__ import annotations

from dataclasses import dataclass
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
