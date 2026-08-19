from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from rvl_pick_seat.algorithm import Assignment
from rvl_pick_seat.layout import SeatLayout

BG_COLOR = (245, 246, 248)
EMPTY_FILL = (225, 227, 231)
EMPTY_OUTLINE = (200, 202, 207)
SEAT_FILL = (255, 255, 255)
SEAT_OUTLINE_HIT = (52, 168, 83)  # got preferred seat
SEAT_OUTLINE_MISS = (66, 133, 244)  # random seat
TEXT_COLOR = (30, 32, 36)
MUTED_TEXT = (140, 143, 150)

_FONT_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
]


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    for path in _FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _circular_avatar(photo_path: Path, diameter: int) -> Image.Image:
    img = Image.open(photo_path).convert("RGB")
    img = ImageOps.exif_transpose(img)
    img = ImageOps.fit(img, (diameter, diameter), method=Image.LANCZOS)

    mask = Image.new("L", (diameter, diameter), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, diameter, diameter), fill=255)

    out = Image.new("RGBA", (diameter, diameter))
    out.paste(img, (0, 0), mask)
    return out


def _placeholder_avatar(diameter: int, initial: str) -> Image.Image:
    out = Image.new("RGBA", (diameter, diameter), (0, 0, 0, 0))
    draw = ImageDraw.Draw(out)
    draw.ellipse((0, 0, diameter, diameter), fill=(200, 202, 207, 255))
    font = _load_font(int(diameter * 0.4))
    bbox = draw.textbbox((0, 0), initial, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(
        ((diameter - tw) / 2 - bbox[0], (diameter - th) / 2 - bbox[1]),
        initial,
        font=font,
        fill=(90, 92, 98, 255),
    )
    return out


def render_seat_chart(
    layout: SeatLayout,
    assignments: list[Assignment],
    photos_dir: str | Path,
    title: str = "抽座位結果",
) -> Image.Image:
    photos_dir = Path(photos_dir)
    by_seat = {a.seat: a for a in assignments}

    top_margin = 140
    canvas = Image.new(
        "RGB", (layout.canvas_width, layout.canvas_height + top_margin), BG_COLOR
    )
    draw = ImageDraw.Draw(canvas)

    title_font = _load_font(56)
    name_font = _load_font(30)
    seat_font = _load_font(24)
    tag_font = _load_font(20)

    draw.text((30, 30), title, font=title_font, fill=TEXT_COLOR)

    legend_y = 100
    draw.ellipse((32, legend_y, 52, legend_y + 20), outline=SEAT_OUTLINE_HIT, width=4)
    draw.text((60, legend_y - 2), "心儀座位", font=tag_font, fill=MUTED_TEXT)
    draw.ellipse((190, legend_y, 210, legend_y + 20), outline=SEAT_OUTLINE_MISS, width=4)
    draw.text((218, legend_y - 2), "隨機座位", font=tag_font, fill=MUTED_TEXT)
    draw.rectangle((376, legend_y, 396, legend_y + 20), fill=EMPTY_FILL, outline=EMPTY_OUTLINE)
    draw.text((404, legend_y - 2), "非本次抽籤座位", font=tag_font, fill=MUTED_TEXT)

    for box in layout.boxes:
        x, y, w, h = box.x, box.y, box.w, box.h + top_margin
        y0 = box.y + top_margin
        assignment = by_seat.get(box.seat) if box.seat is not None else None

        if assignment is None:
            draw.rounded_rectangle(
                (x, y0, x + w, y0 + h - top_margin),
                radius=16,
                fill=EMPTY_FILL,
                outline=EMPTY_OUTLINE,
                width=3,
            )
            continue

        outline = SEAT_OUTLINE_HIT if assignment.got_preference else SEAT_OUTLINE_MISS
        draw.rounded_rectangle(
            (x, y0, x + w, y0 + h - top_margin),
            radius=16,
            fill=SEAT_FILL,
            outline=outline,
            width=5,
        )

        box_h = h - top_margin
        avatar_d = int(min(w, box_h) * 0.62)
        member = assignment.member
        photo_path = photos_dir / member.photo if member.photo else None
        if photo_path and photo_path.exists():
            avatar = _circular_avatar(photo_path, avatar_d)
        else:
            avatar = _placeholder_avatar(avatar_d, member.name[:1])

        avatar_x = x + (w - avatar_d) // 2
        avatar_y = y0 + 10
        canvas.paste(avatar, (avatar_x, avatar_y), avatar)
        draw.ellipse(
            (avatar_x, avatar_y, avatar_x + avatar_d, avatar_y + avatar_d),
            outline=outline,
            width=4,
        )

        seat_tag = f"#{box.seat}"
        draw.text((x + 12, y0 + 8), seat_tag, font=seat_font, fill=MUTED_TEXT)

        name = member.name
        name_bbox = draw.textbbox((0, 0), name, font=name_font)
        name_w = name_bbox[2] - name_bbox[0]
        draw.text(
            (x + (w - name_w) / 2, avatar_y + avatar_d + 8),
            name,
            font=name_font,
            fill=TEXT_COLOR,
        )

        tag = "心儀座位" if assignment.got_preference else "隨機座位"
        tag_bbox = draw.textbbox((0, 0), tag, font=tag_font)
        tag_w = tag_bbox[2] - tag_bbox[0]
        draw.text(
            (x + (w - tag_w) / 2, y0 + box_h - 30),
            tag,
            font=tag_font,
            fill=outline,
        )

    return canvas
