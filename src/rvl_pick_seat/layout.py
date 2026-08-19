from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class Box:
    x: int
    y: int
    w: int
    h: int
    seat: int | None  # None = decorative/unused cell, not part of the draw


@dataclass(frozen=True)
class SeatLayout:
    canvas_width: int
    canvas_height: int
    boxes: tuple[Box, ...]

    def box_for_seat(self, seat: int) -> Box | None:
        for box in self.boxes:
            if box.seat == seat:
                return box
        return None


def load_layout(path: str | Path) -> SeatLayout:
    path = Path(path)
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    canvas = raw.get("canvas") or {}
    width = canvas.get("width")
    height = canvas.get("height")
    if not width or not height:
        raise ValueError(f"{path}: 'canvas.width' and 'canvas.height' are required")

    raw_boxes = raw.get("boxes") or []
    if not raw_boxes:
        raise ValueError(f"{path}: 'boxes' is missing or empty")

    boxes: list[Box] = []
    seen_seats: set[int] = set()
    for i, b in enumerate(raw_boxes):
        coords = b.get("box")
        if not coords or len(coords) != 4:
            raise ValueError(
                f"{path}: box at index {i} must contain a valid [x, y, w, h] value"
            )
        x, y, w, h = coords
        seat = b.get("seat")
        if seat is not None:
            if seat in seen_seats:
                raise ValueError(f"{path}: seat {seat} is assigned to multiple boxes")
            seen_seats.add(seat)
        boxes.append(Box(x=x, y=y, w=w, h=h, seat=seat))

    return SeatLayout(canvas_width=width, canvas_height=height, boxes=tuple(boxes))
