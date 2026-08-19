from __future__ import annotations

import argparse
import os
import random
import sys
from pathlib import Path


def _fix_tcl_tk_library_paths() -> None:
    """uv-managed CPython builds (python-build-standalone) sometimes ship
    tcl8.6/tk8.6 data dirs without wiring TCL_LIBRARY/TK_LIBRARY correctly,
    which makes `tkinter.Tk()` fail to find init.tcl at runtime."""
    base = Path(sys.base_prefix) / "lib"
    tcl_dir = base / "tcl8.6"
    tk_dir = base / "tk8.6"
    if tcl_dir.is_dir() and not os.environ.get("TCL_LIBRARY"):
        os.environ["TCL_LIBRARY"] = str(tcl_dir)
    if tk_dir.is_dir() and not os.environ.get("TK_LIBRARY"):
        os.environ["TK_LIBRARY"] = str(tk_dir)


_fix_tcl_tk_library_paths()

import tkinter as tk

from PIL import Image, ImageTk

from rvl_pick_seat.algorithm import Assignment, run_draft
from rvl_pick_seat.config import load_config
from rvl_pick_seat.layout import load_layout
from rvl_pick_seat.render import (
    BG_TOP,
    GOLD as GOLD_RGB,
    GOLD_BRIGHT as GOLD_BRIGHT_RGB,
    TOP_MARGIN,
    make_summon_particles,
    render_idle_chart,
    render_result_chart,
    render_summon_scene,
)

DEFAULT_LAYOUT = "configs/seats_layout.yaml"
DEFAULT_PHOTOS_DIR = "assets/members"
MAX_DISPLAY_WIDTH = 1400


def _hex(rgb: tuple[int, int, int]) -> str:
    return "#%02x%02x%02x" % rgb


# tkinter chrome colors derived from render.py's palette so the two stay in
# sync instead of duplicating the same colors as separately hand-typed hex
BG_COLOR = _hex(BG_TOP)
GOLD = _hex(GOLD_RGB)
GOLD_BRIGHT = _hex(GOLD_BRIGHT_RGB)

# Timing tuned for a gacha-pull feel: idle -> full-screen summon cutscene
# (rotating magic circle building to a flash) -> cross-fade cut into the
# seat grid -> a per-seat "lock-in" reveal in random order.
SUMMON_FRAMES = 46
SUMMON_INTERVAL_MS = 40
FLASH_FRAMES = 6
FLASH_INTERVAL_MS = 30
CROSSFADE_FRAMES = 8
CROSSFADE_INTERVAL_MS = 35
LOCK_IN_STEPS = 9
LOCK_IN_INTERVAL_MS = 28
REVEAL_PAUSE_MS = 180
IDLE_PULSE_INTERVAL_MS = 60


class SeatChartApp:
    def __init__(
        self, root: tk.Tk, config_path: str, layout_path: str, photos_dir: str, seed: int | None
    ) -> None:
        self.root = root
        self.config_path = config_path
        self.layout = load_layout(layout_path)
        self.photos_dir = photos_dir
        self.seed = seed
        self._tk_image: ImageTk.PhotoImage | None = None
        self._timer: str | None = None
        self._idle_pulse = 0.0
        self.state = "idle"

        root.title("抽座位結果")
        root.configure(bg=BG_COLOR)

        button_kwargs = dict(
            font=("TkDefaultFont", 13, "bold"),
            padx=20,
            pady=8,
            bg=GOLD,
            fg="#241c10",
            activebackground=GOLD_BRIGHT,
            activeforeground="#241c10",
            relief=tk.FLAT,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )

        # The button bar is packed at the bottom *first* so it always keeps
        # its space even if the seat chart image is taller than the screen;
        # the image itself is then scaled to fit whatever remains (see
        # _display), so neither the buttons nor the chart get clipped off
        # the visible screen area.
        button_bar = tk.Frame(root, bg=BG_COLOR)
        button_bar.pack(side=tk.BOTTOM, pady=(0, 18))
        self.start_button = tk.Button(
            button_bar,
            text="🎴 開始抽籤",
            command=self.start_draw,
            **button_kwargs,
        )
        self.start_button.pack(side=tk.LEFT, padx=6)
        self.redraw_button = tk.Button(
            button_bar, text="重新抽一次", command=self.reset_to_idle, **button_kwargs
        )

        self.canvas_label = tk.Label(root, bg=BG_COLOR, bd=0, highlightthickness=0)
        self.canvas_label.pack(side=tk.TOP, padx=12, pady=12)

        root.update_idletasks()
        screen_w = root.winfo_screenwidth()
        screen_h = root.winfo_screenheight()
        # leave headroom for the button bar, window chrome, and taskbar
        self.max_width = max(600, min(MAX_DISPLAY_WIDTH, int(screen_w * 0.92)))
        self.max_height = max(400, int(screen_h * 0.72))

        self._show_idle()

    # -- helpers ----------------------------------------------------------

    def _cancel_timer(self) -> None:
        if self._timer is not None:
            self.root.after_cancel(self._timer)
            self._timer = None

    def _display(self, image: Image.Image, fast: bool = False) -> None:
        # in-motion animation frames use a cheaper resample filter to keep
        # per-frame cost down; the final settled result gets LANCZOS since
        # it's rendered once and then stays on screen
        scale = min(self.max_width / image.width, self.max_height / image.height, 1.0)
        if scale < 1.0:
            resample = Image.BILINEAR if fast else Image.LANCZOS
            image = image.resize(
                (max(1, int(image.width * scale)), max(1, int(image.height * scale))),
                resample,
            )
        self._tk_image = ImageTk.PhotoImage(image)
        self.canvas_label.configure(image=self._tk_image)

    # -- idle state: waiting for the user to press Start -------------------

    def _show_idle(self) -> None:
        self.state = "idle"
        self.redraw_button.pack_forget()
        self.start_button.configure(state=tk.NORMAL, text="🎴 開始抽籤")
        self._run_idle_pulse()

    def _run_idle_pulse(self) -> None:
        if self.state != "idle":
            return
        image = render_idle_chart(
            self.layout,
            subtitle="按下「開始抽籤」揭曉座位",
            pulse=self._idle_pulse,
        )
        self._display(image, fast=True)
        self._idle_pulse += 0.35
        self._timer = self.root.after(IDLE_PULSE_INTERVAL_MS, self._run_idle_pulse)

    def reset_to_idle(self) -> None:
        self._cancel_timer()
        self._show_idle()

    # -- summon cutscene: a full-screen scene distinct from the seat grid ---

    def start_draw(self) -> None:
        self._cancel_timer()
        self.state = "summon"
        self.start_button.configure(state=tk.DISABLED)
        self.redraw_button.pack_forget()

        # the outcome is decided up front (like a server-side gacha roll);
        # only the reveal is animated
        config = load_config(self.config_path)
        rng = (
            random.Random(self.seed) if self.seed is not None else random.SystemRandom()
        )
        results = run_draft(config, rng)
        # a fixed --seed would just redraw the same result every time
        self.seed = None

        order_rng = random.Random()
        self._reveal_order: list[Assignment] = list(results)
        order_rng.shuffle(self._reveal_order)
        self._all_results = results
        self._revealed: set[int] = set()

        scene_w, scene_h = self.layout.canvas_width, self.layout.canvas_height + TOP_MARGIN
        self._scene_size = (scene_w, scene_h)
        self._particles = make_summon_particles(
            order_rng, count=40, max_radius=min(scene_w, scene_h) * 0.42
        )
        self._run_summon(frame=0)

    def _run_summon(self, frame: int) -> None:
        if frame >= SUMMON_FRAMES:
            self._run_flash(frame=0)
            return

        t = frame / max(SUMMON_FRAMES - 1, 1)
        image = render_summon_scene(
            *self._scene_size, t, self._particles, subtitle="命運轉動中…"
        )
        self._display(image, fast=True)
        self._timer = self.root.after(SUMMON_INTERVAL_MS, self._run_summon, frame + 1)

    def _run_flash(self, frame: int) -> None:
        if frame >= FLASH_FRAMES:
            self._begin_crossfade()
            return

        flash_t = (frame + 1) / FLASH_FRAMES
        image = render_summon_scene(
            *self._scene_size, 1.0, self._particles, subtitle="", flash=flash_t
        )
        self._display(image, fast=True)
        if frame == FLASH_FRAMES - 1:
            self._flash_image = image
        self._timer = self.root.after(FLASH_INTERVAL_MS, self._run_flash, frame + 1)

    # -- cross-fade cut from the cutscene into the seat grid ----------------

    def _begin_crossfade(self) -> None:
        self.state = "cutting_in"
        self._grid_mystery_image = render_result_chart(
            self.layout,
            self._all_results,
            self.photos_dir,
            revealed=set(),
            subtitle="揭曉中…",
        )
        self._crossfade(frame=0)

    def _crossfade(self, frame: int) -> None:
        if frame > CROSSFADE_FRAMES:
            self.state = "revealing"
            self._reveal_index = 0
            self._reveal_next()
            return

        alpha = frame / CROSSFADE_FRAMES
        blended = Image.blend(self._flash_image, self._grid_mystery_image, alpha)
        self._display(blended, fast=True)
        self._timer = self.root.after(CROSSFADE_INTERVAL_MS, self._crossfade, frame + 1)

    # -- reveal phase: results are decided, then unveiled one at a time -----

    def _reveal_next(self) -> None:
        if self._reveal_index >= len(self._reveal_order):
            self._finish_reveal()
            return

        assignment = self._reveal_order[self._reveal_index]
        self._lock_in(assignment, step=0)

    def _lock_in(self, assignment: Assignment, step: int) -> None:
        t = step / LOCK_IN_STEPS
        progress = {assignment.seat: min(t, 1.0)}
        remaining = len(self._reveal_order) - self._reveal_index
        image = render_result_chart(
            self.layout,
            self._all_results,
            self.photos_dir,
            revealed=self._revealed,
            reveal_progress=progress,
            subtitle=f"揭曉中…（還剩 {remaining} 位）",
        )
        self._display(image, fast=True)

        if step >= LOCK_IN_STEPS:
            self._revealed.add(assignment.seat)
            self._reveal_index += 1
            self._timer = self.root.after(REVEAL_PAUSE_MS, self._reveal_next)
        else:
            self._timer = self.root.after(LOCK_IN_INTERVAL_MS, self._lock_in, assignment, step + 1)

    def _finish_reveal(self) -> None:
        self.state = "done"
        image = render_result_chart(
            self.layout,
            self._all_results,
            self.photos_dir,
            subtitle="抽籤結果",
        )
        self._display(image)
        self.start_button.configure(state=tk.NORMAL, text="🎴 開始抽籤")
        self.redraw_button.pack(side=tk.LEFT, padx=6)


def main() -> None:
    parser = argparse.ArgumentParser(description="抽座位結果視覺化 GUI")
    parser.add_argument(
        "-c", "--config", default="configs/members.yaml", help="members config 路徑"
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="固定亂數種子（測試用，重現同一次結果）；不給則使用系統亂數",
    )
    parser.add_argument(
        "--layout", default=DEFAULT_LAYOUT, help="座位版面 config 路徑"
    )
    parser.add_argument(
        "--photos-dir", default=DEFAULT_PHOTOS_DIR, help="成員頭貼所在資料夾"
    )
    args = parser.parse_args()

    root = tk.Tk()
    SeatChartApp(root, args.config, args.layout, args.photos_dir, args.seed)
    root.mainloop()


if __name__ == "__main__":
    main()
