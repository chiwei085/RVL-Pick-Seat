from __future__ import annotations

import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from rvl_pick_seat.algorithm import Assignment
from rvl_pick_seat.config import Member
from rvl_pick_seat.layout import Box, SeatLayout

# -- palette: dark indigo/gold "gacha summon" theme -------------------------

BG_TOP = (26, 21, 46)
BG_BOTTOM = (9, 8, 19)

TEXT_COLOR = (240, 236, 250)
MUTED_TEXT = (170, 163, 200)

GOLD = (214, 178, 118)
GOLD_BRIGHT = (255, 224, 165)
GOLD_DIM = (140, 116, 78)
PURPLE_GLOW = (150, 112, 245)

CARD_BG = (40, 34, 66, 232)
CARD_BORDER = GOLD

IDLE_CARD_BG = (30, 27, 50, 205)
IDLE_CARD_BORDER = (98, 90, 134)

EMPTY_CARD_BG = (20, 18, 34, 150)
EMPTY_CARD_BORDER = (56, 52, 80)

BADGE_BG = GOLD
BADGE_TEXT = (26, 20, 44)

# top space reserved above the seat grid for the title/rule/subtitle; also
# used by the caller (gui.py) to keep the summon-scene size in sync with the
# grid image size so the two can be cross-faded together
TOP_MARGIN = 172

_PACKAGE_FONT_DIR = Path(__file__).resolve().parent / "assets" / "fonts"
_SOURCE_FONT_DIR = Path(__file__).resolve().parents[2] / "assets" / "fonts"


def _resolve_font(filename: str) -> Path:
    for directory in (_PACKAGE_FONT_DIR, _SOURCE_FONT_DIR):
        path = directory / filename
        if path.is_file():
            return path
    raise FileNotFoundError(f"Bundled font not found: {filename}")


_FONT_REGULAR = _resolve_font("NotoSansTC-Regular.otf")
_FONT_BOLD = _resolve_font("NotoSansTC-Bold.otf")

_font_cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    key = ("bold" if bold else "regular", size)
    if key in _font_cache:
        return _font_cache[key]
    font = ImageFont.truetype(_FONT_BOLD if bold else _FONT_REGULAR, size)
    _font_cache[key] = font
    return font


# -- letter-tracked text: PIL has no native tracking, so glyphs are placed --
# -- by hand for the wider, more deliberate spacing of a game title/HUD ----


def _char_advances(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> list[float]:
    return [draw.textlength(ch, font=font) for ch in text]


def _tracked_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, spacing: float) -> float:
    if not text:
        return 0.0
    return sum(_char_advances(draw, text, font)) + spacing * (len(text) - 1)


def _draw_tracked(
    draw: ImageDraw.ImageDraw,
    x: float,
    y: float,
    text: str,
    font: ImageFont.FreeTypeFont,
    fill,
    spacing: float = 0,
) -> None:
    cx = x
    for ch, advance in zip(text, _char_advances(draw, text, font)):
        draw.text((cx, y), ch, font=font, fill=fill)
        cx += advance + spacing


def _draw_tracked_centered(
    draw: ImageDraw.ImageDraw,
    center_x: float,
    y: float,
    text: str,
    font: ImageFont.FreeTypeFont,
    fill,
    spacing: float = 0,
) -> None:
    # measure once and reuse the same per-glyph advances for drawing, rather
    # than re-running draw.textlength() for every character a second time
    advances = _char_advances(draw, text, font)
    w = sum(advances) + spacing * (len(text) - 1) if text else 0.0
    cx = center_x - w / 2
    for ch, advance in zip(text, advances):
        draw.text((cx, y), ch, font=font, fill=fill)
        cx += advance + spacing


def _diamond(draw: ImageDraw.ImageDraw, cx: float, cy: float, r: float, color) -> None:
    draw.polygon([(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)], fill=color)


# -- backgrounds: gradient + faint starfield + a closing vignette ----------


_GRADIENT_CACHE: dict[tuple, Image.Image] = {}


def _vertical_gradient(size: tuple[int, int], top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    key = (size, top, bottom)
    cached = _GRADIENT_CACHE.get(key)
    if cached is not None:
        return cached
    w, h = size
    base = Image.new("RGB", (1, h))
    for y in range(h):
        t = y / max(h - 1, 1)
        r = round(top[0] + (bottom[0] - top[0]) * t)
        g = round(top[1] + (bottom[1] - top[1]) * t)
        b = round(top[2] + (bottom[2] - top[2]) * t)
        base.putpixel((0, y), (r, g, b))
    base = base.resize((w, h))
    _GRADIENT_CACHE[key] = base
    return base


_STARFIELD_CACHE: dict[tuple[int, int], Image.Image] = {}


def _starfield(size: tuple[int, int]) -> Image.Image:
    cached = _STARFIELD_CACHE.get(size)
    if cached is not None:
        return cached
    w, h = size
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    rng = random.Random(7)
    count = max(40, (w * h) // 9000)
    for _ in range(count):
        x, y = rng.uniform(0, w), rng.uniform(0, h)
        r = rng.uniform(0.5, 1.7)
        alpha = rng.randint(22, 85)
        color = (255, 224, 180, alpha) if rng.random() < 0.25 else (222, 220, 255, alpha)
        draw.ellipse((x - r, y - r, x + r, y + r), fill=color)
    _STARFIELD_CACHE[size] = layer
    return layer


_VIGNETTE_CACHE: dict[tuple[int, int], Image.Image] = {}


def _vignette_layer(size: tuple[int, int]) -> Image.Image:
    cached = _VIGNETTE_CACHE.get(size)
    if cached is not None:
        return cached
    w, h = size
    cx, cy = w / 2, h / 2
    max_r = math.hypot(cx, cy)
    alpha_layer = Image.new("L", size, 0)
    draw = ImageDraw.Draw(alpha_layer)
    steps = 48
    for i in range(steps, 0, -1):
        t = i / steps
        r = max_r * t * 1.05
        alpha = int(80 * t * t * t)
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=alpha)
    black = Image.new("RGBA", size, (4, 3, 10, 255))
    black.putalpha(alpha_layer)
    _VIGNETTE_CACHE[size] = black
    return black


def _apply_vignette(canvas: Image.Image) -> None:
    canvas.alpha_composite(_vignette_layer(canvas.size), (0, 0))


def _new_canvas(layout: SeatLayout, top_margin: int) -> Image.Image:
    size = (layout.canvas_width, layout.canvas_height + top_margin)
    base = _vertical_gradient(size, BG_TOP, BG_BOTTOM).convert("RGBA")
    base.alpha_composite(_starfield(size), (0, 0))
    return base


# -- avatars ------------------------------------------------------------


def _draw_centered_text(draw: ImageDraw.ImageDraw, cx: float, cy: float, text: str, font: ImageFont.FreeTypeFont, fill) -> None:
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text((cx - tw / 2 - bbox[0], cy - th / 2 - bbox[1]), text, font=font, fill=fill)


def _circular_avatar(photo_path: Path, diameter: int) -> Image.Image:
    img = Image.open(photo_path).convert("RGB")
    img = ImageOps.exif_transpose(img)
    img = ImageOps.fit(img, (diameter, diameter), method=Image.LANCZOS)

    mask = Image.new("L", (diameter, diameter), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, diameter, diameter), fill=255)

    out = Image.new("RGBA", (diameter, diameter))
    out.paste(img, (0, 0), mask)
    return out


# Every avatar variant is pure given its inputs (a member's photo never
# changes mid-run, and the mystery/placeholder art has no random element),
# but render_result_chart redraws the full seat grid on every animation
# frame, so without caching the same photo gets re-decoded and re-masked
# dozens of times per reveal.
_CIRCULAR_AVATAR_CACHE: dict[tuple[Path, int], Image.Image] = {}
_PLACEHOLDER_AVATAR_CACHE: dict[tuple[int, str], Image.Image] = {}
_MYSTERY_AVATAR_CACHE: dict[int, Image.Image] = {}


def _cached_circular_avatar(photo_path: Path, diameter: int) -> Image.Image:
    key = (photo_path, diameter)
    cached = _CIRCULAR_AVATAR_CACHE.get(key)
    if cached is None:
        cached = _circular_avatar(photo_path, diameter)
        _CIRCULAR_AVATAR_CACHE[key] = cached
    return cached


def _placeholder_avatar(
    diameter: int, initial: str, fill=(58, 50, 92, 255), text=GOLD_BRIGHT
) -> Image.Image:
    key = (diameter, initial)
    cached = _PLACEHOLDER_AVATAR_CACHE.get(key)
    if cached is not None:
        return cached
    out = Image.new("RGBA", (diameter, diameter), (0, 0, 0, 0))
    draw = ImageDraw.Draw(out)
    draw.ellipse((0, 0, diameter, diameter), fill=fill)
    if initial:
        font = _load_font(int(diameter * 0.4), bold=True)
        _draw_centered_text(draw, diameter / 2, diameter / 2, initial, font, (*text, 255))
    _PLACEHOLDER_AVATAR_CACHE[key] = out
    return out


def _mystery_avatar(diameter: int) -> Image.Image:
    cached = _MYSTERY_AVATAR_CACHE.get(diameter)
    if cached is not None:
        return cached
    out = Image.new("RGBA", (diameter, diameter), (0, 0, 0, 0))
    draw = ImageDraw.Draw(out)
    draw.ellipse((0, 0, diameter, diameter), fill=(42, 37, 68, 255))
    draw.ellipse((2, 2, diameter - 3, diameter - 3), outline=(*GOLD_DIM, 220), width=2)
    font = _load_font(int(diameter * 0.48), bold=True)
    _draw_centered_text(draw, diameter / 2, diameter / 2, "?", font, (*GOLD, 255))
    _MYSTERY_AVATAR_CACHE[diameter] = out
    return out


def _avatar_for_member(member: Member, photos_dir: Path, diameter: int) -> Image.Image:
    photo_path = photos_dir / member.photo if member.photo else None
    if photo_path and photo_path.exists():
        return _cached_circular_avatar(photo_path, diameter)
    return _placeholder_avatar(diameter, member.name[:1])


# -- glow / shadow / glass-panel primitives ---------------------------------


# GaussianBlur is the costliest step in these two primitives, and both are
# redrawn every animation frame for boxes whose size never changes within a
# render pass; cache the blurred layer (at full opacity for the glow, so a
# per-frame alpha pulse only needs a cheap channel rescale, not a re-blur).
_GLOW_LAYER_CACHE: dict[tuple, Image.Image] = {}
_SHADOW_LAYER_CACHE: dict[tuple, Image.Image] = {}


def _glow(canvas: Image.Image, box_xyxy: tuple[int, int, int, int], radius: int, color, alpha: int, blur: int, pad: int) -> None:
    x0, y0, x1, y1 = box_xyxy
    w, h = x1 - x0, y1 - y0
    if w + 2 * pad <= 0 or h + 2 * pad <= 0 or alpha <= 0:
        return
    key = (w, h, radius, color, blur, pad)
    base = _GLOW_LAYER_CACHE.get(key)
    if base is None:
        layer = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
        ImageDraw.Draw(layer).rounded_rectangle((pad, pad, pad + w, pad + h), radius=radius, fill=(*color, 255))
        base = layer.filter(ImageFilter.GaussianBlur(blur))
        _GLOW_LAYER_CACHE[key] = base
    layer = base if alpha >= 255 else _scale_alpha_channel(base, alpha)
    canvas.alpha_composite(layer, (x0 - pad, y0 - pad))


def _scale_alpha_channel(img: Image.Image, alpha: int) -> Image.Image:
    r, g, b, a = img.split()
    a = a.point(lambda p, a=alpha: p * a // 255)
    return Image.merge("RGBA", (r, g, b, a))


def _shadow(canvas: Image.Image, box_xyxy: tuple[int, int, int, int], radius: int, pad: int = 18, offset: int = 6, alpha: int = 70, blur: int = 10) -> None:
    x0, y0, x1, y1 = box_xyxy
    w, h = x1 - x0, y1 - y0
    key = (w, h, radius, pad, offset, alpha, blur)
    layer = _SHADOW_LAYER_CACHE.get(key)
    if layer is None:
        layer = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
        ImageDraw.Draw(layer).rounded_rectangle(
            (pad, pad + offset, pad + w, pad + offset + h), radius=radius, fill=(0, 0, 0, alpha)
        )
        layer = layer.filter(ImageFilter.GaussianBlur(blur))
        _SHADOW_LAYER_CACHE[key] = layer
    canvas.alpha_composite(layer, (x0 - pad, y0 - pad))


def _panel(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    box_xyxy: tuple[int, int, int, int],
    radius: int,
    fill_rgba: tuple[int, int, int, int],
    outline_rgb=None,
    outline_width: int = 0,
) -> None:
    """A translucent 'glass' card: fill is alpha-composited over whatever is
    already on the canvas (letting the starfield gradient show through),
    with an opaque outline drawn crisply on top."""
    x0, y0, x1, y1 = box_xyxy
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0:
        return
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle((0, 0, w - 1, h - 1), radius=radius, fill=fill_rgba)
    canvas.alpha_composite(layer, (x0, y0))
    if outline_rgb is not None and outline_width > 0:
        draw.rounded_rectangle(box_xyxy, radius=radius, outline=outline_rgb, width=outline_width)


def _corner_brackets(draw: ImageDraw.ImageDraw, box_xyxy: tuple[int, int, int, int], color, length: float = 13, width: int = 2, pad: int = 7) -> None:
    x0, y0, x1, y1 = box_xyxy
    x0, y0, x1, y1 = x0 - pad, y0 - pad, x1 + pad, y1 + pad
    for cx, cy, sx, sy in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)):
        draw.line((cx, cy, cx + sx * length, cy), fill=color, width=width)
        draw.line((cx, cy, cx, cy + sy * length), fill=color, width=width)


def _seat_badge(canvas: Image.Image, draw: ImageDraw.ImageDraw, x: int, y0: int, seat: int) -> None:
    r = 17
    cx, cy = x + 16, y0 + 16
    draw.polygon(_regular_polygon(cx, cy, r, 6, -90), fill=BADGE_BG, outline=GOLD_BRIGHT)
    font = _load_font(16, bold=True)
    _draw_centered_text(draw, cx, cy, str(seat), font, BADGE_TEXT)


def _draw_header(canvas: Image.Image, draw: ImageDraw.ImageDraw, title: str, subtitle: str) -> None:
    width = canvas.width
    cx = width / 2
    title_font = _load_font(48, bold=True)
    subtitle_font = _load_font(20)

    _shadow_text_glow(canvas, cx, 30, title, title_font, spacing=5)
    _draw_tracked_centered(draw, cx, 30, title, title_font, GOLD_BRIGHT, spacing=5)

    rule_y = 100
    rule_half = min(width * 0.3, 230)
    draw.line((cx - rule_half, rule_y, cx - 16, rule_y), fill=GOLD_DIM, width=2)
    draw.line((cx + 16, rule_y, cx + rule_half, rule_y), fill=GOLD_DIM, width=2)
    _diamond(draw, cx, rule_y, 5, GOLD)

    if subtitle:
        _draw_tracked_centered(draw, cx, 120, subtitle, subtitle_font, MUTED_TEXT, spacing=2)


_TITLE_GLOW_CACHE: dict[tuple, Image.Image] = {}


def _shadow_text_glow(canvas: Image.Image, cx: float, y: float, text: str, font: ImageFont.FreeTypeFont, spacing: float = 0) -> None:
    """A soft gold halo behind the title, echoing a summon-emblem glow.

    The title is the same string in the same place on every frame of a
    given animation phase, so the (expensive, full-canvas) blurred glow
    layer is cached rather than rebuilt every tick."""
    key = (canvas.size, text, id(font), spacing, cx, y)
    layer = _TITLE_GLOW_CACHE.get(key)
    if layer is None:
        layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        _draw_tracked_centered(d, cx, y, text, font, (*GOLD, 200), spacing)
        layer = layer.filter(ImageFilter.GaussianBlur(6))
        _TITLE_GLOW_CACHE[key] = layer
    canvas.alpha_composite(layer)


def _empty_box(canvas: Image.Image, draw: ImageDraw.ImageDraw, box: Box, top_margin: int) -> None:
    x, y0, w, h = box.x, box.y + top_margin, box.w, box.h
    _panel(canvas, draw, (x, y0, x + w, y0 + h), radius=16, fill_rgba=EMPTY_CARD_BG, outline_rgb=EMPTY_CARD_BORDER, outline_width=2)


def _draw_mystery_seat(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    box_xyxy: tuple[int, int, int, int],
    seat: int,
    glow_alpha: int | None = None,
) -> None:
    """A seat not yet revealed: shadow, glass panel, '?' avatar, seat badge.
    Shared by the idle screen and the not-yet-reached seats mid-reveal;
    `glow_alpha` adds the idle screen's pulsing purple halo when given."""
    x, y0, x1, y1 = box_xyxy
    w, h = x1 - x, y1 - y0
    _shadow(canvas, box_xyxy, radius=18, alpha=45, blur=8)
    if glow_alpha is not None:
        _glow(canvas, box_xyxy, radius=18, color=PURPLE_GLOW, alpha=glow_alpha, blur=16, pad=10)
    _panel(canvas, draw, box_xyxy, radius=18, fill_rgba=IDLE_CARD_BG, outline_rgb=IDLE_CARD_BORDER, outline_width=2)
    avatar_d = int(min(w, h) * 0.5)
    avatar = _mystery_avatar(avatar_d)
    avatar_x = x + (w - avatar_d) // 2
    avatar_y = y0 + (h - avatar_d) // 2 - 6
    canvas.paste(avatar, (avatar_x, avatar_y), avatar)
    _seat_badge(canvas, draw, x, y0, seat)


def render_idle_chart(
    layout: SeatLayout,
    title: str = "抽座位結果",
    subtitle: str = "按下「開始抽籤」揭曉座位 ✦",
    pulse: float = 0.0,
) -> Image.Image:
    """Pre-draw screen: seats shown as empty mystery slots, waiting for Start."""
    top_margin = TOP_MARGIN
    canvas = _new_canvas(layout, top_margin)
    draw = ImageDraw.Draw(canvas)
    _draw_header(canvas, draw, title, subtitle)

    glow_alpha = int(55 + 45 * (0.5 + 0.5 * math.sin(pulse)))

    for box in layout.boxes:
        x, y0, w, h = box.x, box.y + top_margin, box.w, box.h
        if box.seat is None:
            _empty_box(canvas, draw, box, top_margin)
            continue

        box_xyxy = (x, y0, x + w, y0 + h)
        _draw_mystery_seat(canvas, draw, box_xyxy, box.seat, glow_alpha=glow_alpha)

    _apply_vignette(canvas)
    return canvas.convert("RGB")


# -- summon cutscene: a full-screen magic-circle gacha reveal ---------------

_SUMMON_BG_CACHE: dict[tuple[int, int], Image.Image] = {}


def _radial_gradient(
    size: tuple[int, int],
    center: tuple[float, float],
    inner: tuple[int, int, int],
    outer: tuple[int, int, int],
    max_radius: float,
    steps: int = 56,
) -> Image.Image:
    img = Image.new("RGB", size, outer)
    draw = ImageDraw.Draw(img)
    cx, cy = center
    for i in range(steps, 0, -1):
        t = i / steps
        r = max_radius * t
        color = tuple(round(outer[c] + (inner[c] - outer[c]) * (1 - t)) for c in range(3))
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color)
    return img


def _summon_background(width: int, height: int) -> Image.Image:
    key = (width, height)
    cached = _SUMMON_BG_CACHE.get(key)
    if cached is None:
        cx, cy = width / 2, height / 2
        max_radius = math.hypot(max(cx, width - cx), max(cy, height - cy))
        cached = _radial_gradient((width, height), (cx, cy), (58, 42, 92), (7, 6, 16), max_radius)
        base = cached.convert("RGBA")
        base.alpha_composite(_starfield((width, height)), (0, 0))
        cached = base
        _SUMMON_BG_CACHE[key] = cached
    return cached.copy()


def make_summon_particles(rng: random.Random, count: int, max_radius: float) -> list[tuple[float, float, float, int]]:
    """(angle, start_radius, timing_phase, size) for particles converging toward
    the summon circle's center."""
    particles = []
    for _ in range(count):
        angle = rng.uniform(0, 2 * math.pi)
        start_r = rng.uniform(max_radius * 0.55, max_radius)
        phase = rng.uniform(-0.15, 0.1)
        size = rng.randint(3, 7)
        particles.append((angle, start_r, phase, size))
    return particles


def _regular_polygon(cx: float, cy: float, r: float, sides: int, rotation_deg: float) -> list[tuple[float, float]]:
    return [
        (cx + r * math.cos(math.radians(rotation_deg + i * 360 / sides)), cy + r * math.sin(math.radians(rotation_deg + i * 360 / sides)))
        for i in range(sides)
    ]


def _particle_pos(cx: float, cy: float, angle: float, start_r: float, radius_t: float, spin_t: float) -> tuple[float, float]:
    """A summon particle's position: `radius_t` (0..1) drives how far it has
    converged toward the center, `spin_t` drives its orbital rotation."""
    r = start_r * (1 - radius_t * radius_t)
    spin_ang = angle + spin_t * 2.4
    return cx + r * math.cos(spin_ang), cy + r * math.sin(spin_ang)


def render_summon_scene(
    width: int,
    height: int,
    t: float,
    particles: list[tuple[float, float, float, int]],
    title: str = "抽座位結果",
    subtitle: str = "命運轉動中…",
    flash: float = 0.0,
) -> Image.Image:
    """Full-screen gacha-summon cutscene: a rotating magic circle with a
    hexagram core, particles sparkling inward, building to a warm-gold flash."""
    t = max(0.0, min(1.0, t))
    canvas = _summon_background(width, height)
    draw = ImageDraw.Draw(canvas)
    cx, cy = width / 2, height / 2 - 10

    rotation = t * 620
    outer_r, mid_r, inner_r = 260, 200, 150

    # clock-style tick marks around the outer ring
    tick_count = 24
    for i in range(tick_count):
        ang = math.radians(rotation * 0.5 + i * (360 / tick_count))
        length = 14 if i % 2 == 0 else 7
        x0, y0 = cx + outer_r * math.cos(ang), cy + outer_r * math.sin(ang)
        x1, y1 = cx + (outer_r + length) * math.cos(ang), cy + (outer_r + length) * math.sin(ang)
        draw.line((x0, y0, x1, y1), fill=(*GOLD_DIM, 190), width=2)

    for i, rr in enumerate((outer_r, mid_r, inner_r)):
        bbox = (cx - rr, cy - rr, cx + rr, cy + rr)
        draw.ellipse(bbox, outline=(*GOLD, 190 - i * 25), width=2)

    spoke_count = 12
    for i in range(spoke_count):
        ang = math.radians(rotation + i * (360 / spoke_count))
        x0, y0 = cx + inner_r * math.cos(ang), cy + inner_r * math.sin(ang)
        x1, y1 = cx + outer_r * math.cos(ang), cy + outer_r * math.sin(ang)
        draw.line((x0, y0, x1, y1), fill=(*PURPLE_GLOW, 130), width=2)

    # a slowly counter-rotating hexagram inscribed in the inner ring
    hex_r = inner_r * 0.86
    tri_a = _regular_polygon(cx, cy, hex_r, 3, -rotation * 0.6)
    tri_b = _regular_polygon(cx, cy, hex_r, 3, -rotation * 0.6 + 180)
    draw.polygon(tri_a, outline=(*GOLD, 170))
    draw.polygon(tri_b, outline=(*GOLD, 170))

    for i, (angle, start_r, phase, size) in enumerate(particles):
        local_t = max(0.0, min(1.0, t + phase))
        px, py = _particle_pos(cx, cy, angle, start_r, local_t, t)

        trail_t = max(0.0, local_t - 0.05)
        tx, ty = _particle_pos(cx, cy, angle, start_r, trail_t, max(0.0, t - 0.05))

        warm = i % 3 != 0
        color = GOLD_BRIGHT if warm else (200, 175, 255)
        trail_alpha = int(120 * (0.35 + 0.65 * local_t))
        draw.line((tx, ty, px, py), fill=(*color, trail_alpha), width=max(1, size - 3))

        alpha = int(255 * (0.35 + 0.65 * local_t))
        draw.ellipse((px - size, py - size, px + size, py + size), fill=(*color, alpha))

    pop = _ease_out_back(min(t * 1.3, 1.0))
    emblem_r = max(4, int(92 * pop))
    halo_pulse = 0.5 + 0.5 * math.sin(t * math.pi * 3)
    draw.ellipse(
        (cx - emblem_r - 26, cy - emblem_r - 26, cx + emblem_r + 26, cy + emblem_r + 26),
        fill=(*GOLD, int(55 + 55 * halo_pulse)),
    )
    draw.ellipse(
        (cx - emblem_r, cy - emblem_r, cx + emblem_r, cy + emblem_r),
        fill=(255, 244, 220, 235),
        outline=(*GOLD_BRIGHT, 255),
        width=4,
    )

    title_font = _load_font(44, bold=True)
    subtitle_font = _load_font(24)
    _shadow_text_glow(canvas, cx, 54, title, title_font, spacing=6)
    _draw_tracked_centered(draw, cx, 54, title, title_font, (*GOLD_BRIGHT, 255), spacing=6)

    if subtitle:
        sub_alpha = int(190 + 60 * math.sin(t * 10))
        _draw_tracked_centered(
            draw, cx, height - 108, subtitle, subtitle_font, (*MUTED_TEXT, max(0, min(255, sub_alpha))), spacing=2
        )

    _apply_vignette(canvas)

    if flash > 0:
        overlay = Image.new("RGBA", canvas.size, (255, 246, 222, int(255 * min(flash, 1.0))))
        canvas = Image.alpha_composite(canvas, overlay)

    return canvas.convert("RGB")


def _ease_out_back(t: float) -> float:
    c1 = 1.35
    c3 = c1 + 1
    t = max(0.0, min(1.0, t))
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


def render_result_chart(
    layout: SeatLayout,
    assignments: list[Assignment],
    photos_dir: str | Path,
    revealed: set[int] | None = None,
    reveal_progress: dict[int, float] | None = None,
    title: str = "抽座位結果",
    subtitle: str = "",
) -> Image.Image:
    """Final / in-progress reveal screen.

    revealed: seats already fully settled.
    reveal_progress: seat -> animation t in [0, 1] for a seat currently mid
    reveal-in (scale/glow "lock-in" burst); absent seats are drawn idle-mystery.
    """
    photos_dir = Path(photos_dir)
    revealed = revealed if revealed is not None else {a.seat for a in assignments}
    reveal_progress = reveal_progress or {}
    by_seat = {a.seat: a for a in assignments}

    top_margin = TOP_MARGIN
    canvas = _new_canvas(layout, top_margin)
    draw = ImageDraw.Draw(canvas)
    _draw_header(canvas, draw, title, subtitle)

    name_font = _load_font(27, bold=True)

    for box in layout.boxes:
        x, y0, w, h = box.x, box.y + top_margin, box.w, box.h
        box_xyxy = (x, y0, x + w, y0 + h)
        assignment = by_seat.get(box.seat) if box.seat is not None else None

        if assignment is None:
            _empty_box(canvas, draw, box, top_margin)
            continue

        t = reveal_progress.get(box.seat)
        is_revealed = box.seat in revealed
        if not is_revealed and t is None:
            # not yet reached in the reveal order -- still a mystery slot
            _draw_mystery_seat(canvas, draw, box_xyxy, box.seat)
            continue

        anim_t = 1.0 if t is None else t
        pop = _ease_out_back(anim_t)
        burst = math.sin(min(anim_t, 1.0) * math.pi)  # 0 -> 1 -> 0 flash during lock-in

        _shadow(canvas, box_xyxy, radius=18, alpha=60, blur=9)
        if burst > 0:
            _glow(canvas, box_xyxy, radius=18, color=GOLD, alpha=int(110 * burst), blur=16, pad=12)
            # a brief expanding gold ring shockwave at the moment of lock-in
            ring_r = int(min(w, h) * (0.35 + 0.5 * burst))
            cx0, cy0 = x + w // 2, y0 + h // 2
            draw.ellipse(
                (cx0 - ring_r, cy0 - ring_r, cx0 + ring_r, cy0 + ring_r),
                outline=(*GOLD_BRIGHT, int(200 * burst)),
                width=2,
            )

        border_w = 3 + int(3 * burst)
        _panel(canvas, draw, box_xyxy, radius=18, fill_rgba=CARD_BG, outline_rgb=CARD_BORDER, outline_width=border_w)
        if anim_t >= 0.999:
            _corner_brackets(draw, box_xyxy, GOLD, length=13, width=2, pad=7)

        member = assignment.member
        base_avatar_d = int(min(w, h) * 0.5)
        avatar_d = max(4, int(base_avatar_d * min(pop, 1.15)))
        avatar = _avatar_for_member(member, photos_dir, avatar_d)
        avatar_cx = x + w // 2
        avatar_cy = y0 + 20 + base_avatar_d // 2
        avatar_x = avatar_cx - avatar_d // 2
        avatar_y = avatar_cy - avatar_d // 2
        canvas.paste(avatar, (avatar_x, avatar_y), avatar)
        draw.ellipse(
            (avatar_x, avatar_y, avatar_x + avatar_d, avatar_y + avatar_d),
            outline=GOLD,
            width=3,
        )

        if anim_t >= 0.999:
            _seat_badge(canvas, draw, x, y0, box.seat)

            name = member.name
            name_w = _tracked_width(draw, name, name_font, spacing=1)
            name_y = avatar_cy + base_avatar_d // 2 + 12
            _draw_tracked(draw, x + (w - name_w) / 2, name_y, name, name_font, TEXT_COLOR, spacing=1)
            name_bbox = draw.textbbox((0, 0), name, font=name_font)
            underline_y = name_y + (name_bbox[3] - name_bbox[1]) + 12
            draw.line(
                (x + w / 2 - name_w / 3, underline_y, x + w / 2 + name_w / 3, underline_y),
                fill=GOLD_DIM,
                width=2,
            )

    _apply_vignette(canvas)
    return canvas.convert("RGB")
