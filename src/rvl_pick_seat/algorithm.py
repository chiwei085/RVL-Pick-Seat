from __future__ import annotations

import random
from dataclasses import dataclass

from rvl_pick_seat.config import Config, Member


@dataclass(frozen=True)
class Assignment:
    member: Member
    seat: int
    got_preference: bool
    priority: float


def _priority(member: Member, seat_count: int) -> float:
    """Higher weight -> higher priority. Fewer preferences -> higher priority.

    scarcity_bonus(k) = N ** (-(k-1)/(N-1))

    A geometric interpolation between 1 (k=1, maximally specific) and 1/N
    (k=N, every seat listed = no real opinion), i.e. each extra preferred
    seat costs a constant *fraction* of the remaining bonus rather than a
    constant amount. That naturally makes "no opinion" land far below
    "picked almost everything", with no extra magic constants, and it
    self-scales to any seat count N.
    """
    k = len(member.preferences)
    if seat_count == 1:
        scarcity_bonus = 1.0
    else:
        scarcity_bonus = seat_count ** (-(k - 1) / (seat_count - 1))
    return member.weight * scarcity_bonus


def _draft_order(members: tuple[Member, ...], seat_count: int, rng: random.Random) -> list[Member]:
    """Weighted random permutation (Efraimidis-Spirakis).

    Each member draws key = U(0,1) ** (1/priority); sorting by key descending
    yields a random order where the probability of any given member landing
    in any given rank is exactly proportional to their priority weight among
    those still remaining. Ties/equal priority are broken by fair randomness.
    """
    keyed = [
        (rng.random() ** (1.0 / _priority(m, seat_count)), m)
        for m in members
    ]
    keyed.sort(key=lambda pair: pair[0], reverse=True)
    return [m for _, m in keyed]


def run_draft(config: Config, rng: random.Random | None = None) -> list[Assignment]:
    rng = rng or random.SystemRandom()
    seat_count = len(config.seats)
    order = _draft_order(config.members, seat_count, rng)

    available = set(config.seats)
    results: list[Assignment] = []

    for member in order:
        wanted_available = [s for s in member.preferences if s in available]
        if wanted_available:
            seat = rng.choice(wanted_available)
            got_preference = True
        else:
            seat = rng.choice(sorted(available))
            got_preference = False

        available.remove(seat)
        results.append(
            Assignment(
                member=member,
                seat=seat,
                got_preference=got_preference,
                priority=_priority(member, seat_count),
            )
        )

    return results
