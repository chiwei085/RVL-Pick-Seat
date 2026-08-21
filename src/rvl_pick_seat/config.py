from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class Member:
    name: str
    weight: float
    preferences: tuple[int, ...]
    photo: str | None = None


@dataclass(frozen=True)
class Config:
    members: tuple[Member, ...]
    seats: tuple[int, ...]


def load_config(path: str | Path, seats: Iterable[int] | None = None) -> Config:
    path = Path(path)
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    raw_members = raw.get("members")
    if not raw_members:
        raise ValueError(f"{path}: 'members' is missing or empty")

    members: list[Member] = []
    seen_names: set[str] = set()
    for i, m in enumerate(raw_members):
        name = m.get("name")
        if not name:
            raise ValueError(f"{path}: member at index {i} is missing 'name'")
        if name in seen_names:
            raise ValueError(f"{path}: duplicate member name: '{name}'")
        seen_names.add(name)

        weight = m.get("weight")
        if weight is None or weight <= 0:
            raise ValueError(f"{path}: '{name}': 'weight' must be positive")

        preferences = tuple(m.get("preferences") or [])
        if not preferences:
            raise ValueError(
                f"{path}: '{name}': 'preferences' must not be empty; "
                "list all seat numbers when there is no preference"
            )
        photo = m.get("photo")
        members.append(
            Member(name=name, weight=float(weight), preferences=preferences, photo=photo)
        )

    seat_count = len(members)
    configured_seats = (
        tuple(range(1, seat_count + 1)) if seats is None else tuple(seats)
    )
    if len(configured_seats) != seat_count:
        raise ValueError(
            f"{path}: number of lottery seats ({len(configured_seats)}) must match "
            f"number of members ({seat_count})"
        )
    seat_ids = set(configured_seats)
    if len(seat_ids) != len(configured_seats):
        raise ValueError(f"{path}: lottery seat numbers must be unique")

    for m in members:
        invalid = set(m.preferences) - seat_ids
        if invalid:
            raise ValueError(
                f"{path}: '{m.name}': 'preferences' contains unknown seat numbers "
                f"{sorted(invalid)} (lottery seats: {sorted(seat_ids)})"
            )
        if len(set(m.preferences)) != len(m.preferences):
            raise ValueError(
                f"{path}: '{m.name}': 'preferences' contains duplicate seat numbers"
            )

    return Config(members=tuple(members), seats=configured_seats)
