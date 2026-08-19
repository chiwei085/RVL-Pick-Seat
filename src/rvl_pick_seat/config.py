from __future__ import annotations

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
    seat_count: int

    @property
    def seats(self) -> tuple[int, ...]:
        return tuple(range(1, self.seat_count + 1))


def load_config(path: str | Path) -> Config:
    path = Path(path)
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    raw_members = raw.get("members")
    if not raw_members:
        raise ValueError(f"{path}: 'members' 為空或缺少")

    members: list[Member] = []
    seen_names: set[str] = set()
    for i, m in enumerate(raw_members):
        name = m.get("name")
        if not name:
            raise ValueError(f"{path}: 第 {i} 位成員缺少 name")
        if name in seen_names:
            raise ValueError(f"{path}: 姓名重複 '{name}'")
        seen_names.add(name)

        weight = m.get("weight")
        if weight is None or weight <= 0:
            raise ValueError(f"{path}: '{name}' 的 weight 必須為正數")

        preferences = tuple(m.get("preferences") or [])
        if not preferences:
            raise ValueError(
                f"{path}: '{name}' 的 preferences 不可為空；沒有特別偏好請列出全部座位編號"
            )
        photo = m.get("photo")
        members.append(
            Member(name=name, weight=float(weight), preferences=preferences, photo=photo)
        )

    seat_count = len(members)
    seat_ids = set(range(1, seat_count + 1))
    for m in members:
        invalid = set(m.preferences) - seat_ids
        if invalid:
            raise ValueError(
                f"{path}: '{m.name}' 的 preferences 含有不存在的座位編號 {sorted(invalid)}"
                f"（合法範圍為 1..{seat_count}）"
            )
        if len(set(m.preferences)) != len(m.preferences):
            raise ValueError(f"{path}: '{m.name}' 的 preferences 有重複座位編號")

    return Config(members=tuple(members), seat_count=seat_count)
