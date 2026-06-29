"""战斗状态转移：出牌、回合结束、敌人行动。"""

from __future__ import annotations

from dataclasses import replace
from typing import Optional

from engine.deck import BANE, BASH, CARD_INDEX, DEFEND, Pile, STRIKE, pile_add
from engine.types import ENERGY_PER_TURN, EMPTY_PILE, State

SEAPUNK_INTENTS = (
    {"kind": "attack", "damage": 13, "hits": 1},
    {"kind": "attack", "damage": 2, "hits": 4},
    {"kind": "buff", "block": 8, "strength": 2},
)

CARD_COST = {STRIKE: 1, DEFEND: 1, BASH: 2, BANE: None}
CARD_DAMAGE = {STRIKE: 6, BASH: 8}
CARD_BLOCK = {DEFEND: 5}
PLAYABLE = (STRIKE, DEFEND, BASH)
ATTACKS = (BASH, STRIKE)


def _calc_attack_damage(
    base: int,
    attacker_strength: int,
    attacker_weak: int,
    defender_vulnerable: int,
) -> int:
    single = base + attacker_strength
    if attacker_weak > 0:
        single *= 0.75
    if defender_vulnerable > 0:
        single *= 1.5
    return int(single)


def _calc_block(base: int, dexterity: int, frail: int) -> int:
    single = base + dexterity
    if frail > 0:
        single *= 0.75
    return int(single)


def _deal_damage_to_enemy(state: State, amount: int) -> State:
    block = min(state.enemy_block, amount)
    hp_loss = amount - block
    return replace(
        state,
        enemy_hp=state.enemy_hp - hp_loss,
        enemy_block=state.enemy_block - block,
    )


def _deal_damage_to_player(state: State, amount: int) -> State:
    block = min(state.player_block, amount)
    hp_loss = amount - block
    return replace(
        state,
        player_block=state.player_block - block,
        damage_taken=state.damage_taken + hp_loss,
    )


def make_turn_state(
    *,
    enemy_hp: int,
    hand: Pile,
    draw: Pile,
    discard: Pile = EMPTY_PILE,
    exhaust: Pile = EMPTY_PILE,
    turn_count: int = 1,
    intent_index: int = 0,
    damage_taken: int = 0,
    enemy_strength: int = 0,
    enemy_vulnerable: int = 0,
    enemy_block: int = 0,
) -> State:
    """构造玩家回合初局面（手牌已抽满）。"""
    return State(
        enemy_hp=enemy_hp,
        enemy_block=enemy_block,
        enemy_strength=enemy_strength,
        enemy_vulnerable=enemy_vulnerable,
        intent_index=intent_index,
        player_block=0,
        player_vulnerable=0,
        player_weak=0,
        player_frail=0,
        player_strength=0,
        player_dexterity=0,
        damage_taken=damage_taken,
        turn_count=turn_count,
        energy=ENERGY_PER_TURN,
        hand=hand,
        draw=draw,
        discard=discard,
        exhaust=exhaust,
        hand_at_turn_start=hand,
    )


def incoming_damage(state: State) -> int:
    """本回合敌人意图将造成的 HP 损失（按当前格挡模拟多段）。"""
    intent = SEAPUNK_INTENTS[state.intent_index]
    if intent["kind"] != "attack":
        return 0
    per_hit = _calc_attack_damage(
        intent["damage"], state.enemy_strength, 0, state.player_vulnerable
    )
    block = state.player_block
    total = 0
    for _ in range(intent["hits"]):
        absorbed = min(block, per_hit)
        block -= absorbed
        total += per_hit - absorbed
    return total


def block_is_sufficient(state: State) -> bool:
    return incoming_damage(state) == 0


def has_playable_attack(state: State) -> bool:
    for card in ATTACKS:
        cost = CARD_COST[card]
        idx = CARD_INDEX[card]
        if cost is not None and state.energy >= cost and state.hand[idx] > 0:
            return True
    return False


def _can_kill_impl(
    enemy_hp: int,
    enemy_block: int,
    enemy_vulnerable: int,
    player_strength: int,
    player_weak: int,
    energy: int,
    hand: tuple[int, int, int, int],
    memo: dict[tuple, bool],
) -> bool:
    key = (enemy_hp, enemy_block, enemy_vulnerable, player_strength, player_weak, energy, hand)
    cached = memo.get(key)
    if cached is not None:
        return cached

    if enemy_hp <= 0:
        memo[key] = True
        return True
    if energy <= 0:
        memo[key] = False
        return False

    for card in ATTACKS:
        cost = CARD_COST[card]
        idx = CARD_INDEX[card]
        if cost is None or energy < cost or hand[idx] <= 0:
            continue

        new_hand = list(hand)
        new_hand[idx] -= 1
        new_energy = energy - cost

        dmg = _calc_attack_damage(
            CARD_DAMAGE[card], player_strength, player_weak, enemy_vulnerable
        )
        absorbed = min(enemy_block, dmg)
        new_hp = enemy_hp - (dmg - absorbed)
        new_block = enemy_block - absorbed
        new_vuln = enemy_vulnerable + (2 if card == BASH else 0)

        if _can_kill_impl(
            new_hp,
            new_block,
            new_vuln,
            player_strength,
            player_weak,
            new_energy,
            tuple(new_hand),
            memo,
        ):
            memo[key] = True
            return True

    memo[key] = False
    return False


def can_kill_this_turn(state: State, memo: dict[tuple, bool] | None = None) -> bool:
    local: dict[tuple, bool] = {} if memo is None else memo
    return _can_kill_impl(
        state.enemy_hp,
        state.enemy_block,
        state.enemy_vulnerable,
        state.player_strength,
        state.player_weak,
        state.energy,
        state.hand,
        local,
    )


def play_card(state: State, card: str) -> Optional[State]:
    if state.energy <= 0:
        return None
    cost = CARD_COST[card]
    if cost is None or state.energy < cost:
        return None

    idx = CARD_INDEX[card]
    if state.hand[idx] <= 0:
        return None

    hand = list(state.hand)
    hand[idx] -= 1
    discard = list(state.discard)
    discard[idx] += 1
    nxt = replace(
        state,
        energy=state.energy - cost,
        hand=tuple(hand),
        discard=tuple(discard),
    )

    if card == STRIKE:
        dmg = _calc_attack_damage(
            CARD_DAMAGE[STRIKE], nxt.player_strength, nxt.player_weak, nxt.enemy_vulnerable
        )
        nxt = _deal_damage_to_enemy(nxt, dmg)
    elif card == BASH:
        dmg = _calc_attack_damage(
            CARD_DAMAGE[BASH], nxt.player_strength, nxt.player_weak, nxt.enemy_vulnerable
        )
        nxt = _deal_damage_to_enemy(nxt, dmg)
        nxt = replace(nxt, enemy_vulnerable=nxt.enemy_vulnerable + 2)
    elif card == DEFEND:
        block = _calc_block(CARD_BLOCK[DEFEND], nxt.player_dexterity, nxt.player_frail)
        nxt = replace(nxt, player_block=nxt.player_block + block)

    return nxt


def _finalize_discard(state: State) -> State:
    """回合末：本回合上手牌全部进弃牌堆，诅咒在手则消耗。"""
    discard = pile_add(state.discard, state.hand_at_turn_start)
    exhaust = state.exhaust
    bane_in_hand = state.hand[3]
    if bane_in_hand > 0:
        discard = (discard[0], discard[1], discard[2], discard[3] - bane_in_hand)
        exhaust = (exhaust[0], exhaust[1], exhaust[2], exhaust[3] + bane_in_hand)
    return replace(
        state,
        hand=EMPTY_PILE,
        discard=discard,
        exhaust=exhaust,
        energy=0,
    )


def enemy_turn(state: State) -> State:
    state = replace(
        state,
        enemy_block=0,
        enemy_vulnerable=max(0, state.enemy_vulnerable - 1),
    )

    intent = SEAPUNK_INTENTS[state.intent_index]
    if intent["kind"] == "attack":
        per_hit = _calc_attack_damage(
            intent["damage"], state.enemy_strength, 0, state.player_vulnerable
        )
        for _ in range(intent["hits"]):
            state = _deal_damage_to_player(state, per_hit)
    elif intent["kind"] == "buff":
        state = replace(
            state,
            enemy_block=state.enemy_block + intent["block"],
            enemy_strength=state.enemy_strength + intent["strength"],
        )

    return replace(
        state,
        intent_index=(state.intent_index + 1) % len(SEAPUNK_INTENTS),
    )


def prepare_next_turn(state: State) -> State:
    return replace(
        state,
        player_block=0,
        player_vulnerable=max(0, state.player_vulnerable - 1),
        player_weak=max(0, state.player_weak - 1),
        player_frail=max(0, state.player_frail - 1),
        turn_count=state.turn_count + 1,
        energy=ENERGY_PER_TURN,
        hand=EMPTY_PILE,
        hand_at_turn_start=EMPTY_PILE,
    )


def end_player_turn(state: State) -> State:
    """结束玩家回合 → 敌人行动 → 准备下一回合（尚未抽牌）。"""
    state = _finalize_discard(state)
    if state.enemy_hp <= 0:
        return state
    state = enemy_turn(state)
    if state.enemy_hp <= 0:
        return state
    return prepare_next_turn(state)
