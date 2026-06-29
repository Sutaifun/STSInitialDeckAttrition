"""层 1：枚举抽牌路径（弃牌堆组成仅由抽牌决定，与出牌无关）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

from engine.deck import IRONCLAD_A10_DECK, combinations_draw, opening_hand_combinations, pile_add, pile_total
from engine.types import EMPTY_PILE, HAND_SIZE, MAX_TURNS, Pile


@dataclass(frozen=True)
class TurnPiles:
    """某回合初（已抽牌后）的牌堆状态。"""

    hand: Pile
    draw: Pile
    discard: Pile
    exhaust: Pile


def _draw_at_turn_start(draw: Pile, discard: Pile, exhaust: Pile) -> Iterator[TurnPiles]:
    """回合初从 draw/discard 抽满 5 张的所有组合分支。"""
    for hand, new_draw, new_discard in _draw_rec(draw, discard, EMPTY_PILE, HAND_SIZE):
        yield TurnPiles(hand=hand, draw=new_draw, discard=new_discard, exhaust=exhaust)


def _draw_rec(
    draw: Pile,
    discard: Pile,
    hand: Pile,
    need: int,
) -> Iterator[tuple[Pile, Pile, Pile]]:
    if need == 0:
        yield hand, draw, discard
        return

    draw_n = pile_total(draw)
    if draw_n > 0:
        if draw_n <= need:
            hand = pile_add(hand, draw)
            yield from _draw_rec(EMPTY_PILE, discard, hand, need - draw_n)
        else:
            for drawn, left in combinations_draw(draw, need):
                yield pile_add(hand, drawn), left, discard
        return

    discard_n = pile_total(discard)
    if discard_n == 0:
        yield hand, draw, discard
        return

    if discard_n <= need:
        hand = pile_add(hand, discard)
        yield hand, EMPTY_PILE, EMPTY_PILE
        return

    for drawn, left in combinations_draw(discard, need):
        yield pile_add(hand, drawn), left, EMPTY_PILE


def _end_turn_piles(piles: TurnPiles) -> tuple[Pile, Pile, Pile]:
    """回合末弃牌更新（与出牌无关，仅看本回合上手牌）。"""
    discard = pile_add(piles.discard, piles.hand)
    exhaust = piles.exhaust
    bane = piles.hand[3]
    if bane > 0:
        discard = (discard[0], discard[1], discard[2], discard[3] - bane)
        exhaust = (exhaust[0], exhaust[1], exhaust[2], exhaust[3] + bane)
    return piles.draw, discard, exhaust


def enumerate_draw_paths(max_turns: int = MAX_TURNS) -> Iterator[tuple[TurnPiles, ...]]:
    """
    枚举至 max_turns 回合的全部抽牌路径。
    每条路径为各回合初的 TurnPiles 序列（手牌已抽满）。
    """

    def rec(
        turn: int,
        draw: Pile,
        discard: Pile,
        exhaust: Pile,
        path: tuple[TurnPiles, ...],
    ) -> Iterator[tuple[TurnPiles, ...]]:
        if turn > max_turns:
            yield path
            return

        if turn == 1:
            turn_iters: Iterator[TurnPiles] = (
                TurnPiles(hand=h, draw=d, discard=EMPTY_PILE, exhaust=EMPTY_PILE)
                for h, d in opening_hand_combinations()
            )
        else:
            turn_iters = _draw_at_turn_start(draw, discard, exhaust)

        for tp in turn_iters:
            new_draw, new_discard, new_exhaust = _end_turn_piles(tp)
            yield from rec(turn + 1, new_draw, new_discard, new_exhaust, path + (tp,))

    yield from rec(1, IRONCLAD_A10_DECK, EMPTY_PILE, EMPTY_PILE, ())


def count_draw_paths(max_turns: int = MAX_TURNS) -> int:
    return sum(1 for _ in enumerate_draw_paths(max_turns))
