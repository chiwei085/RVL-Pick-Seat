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

from rvl_pick_seat.algorithm import run_draft
from rvl_pick_seat.config import load_config
from rvl_pick_seat.layout import load_layout
from rvl_pick_seat.render import render_seat_chart

DEFAULT_LAYOUT = "configs/seats_layout.yaml"
DEFAULT_PHOTOS_DIR = "assets/members"
MAX_DISPLAY_WIDTH = 1400


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

        root.title("抽座位結果")

        self.canvas_label = tk.Label(root)
        self.canvas_label.pack(padx=12, pady=12)

        button_bar = tk.Frame(root)
        button_bar.pack(pady=(0, 12))
        tk.Button(button_bar, text="重新抽一次", command=self.redraw).pack(side=tk.LEFT, padx=6)

        self.redraw()

    def redraw(self) -> None:
        config = load_config(self.config_path)
        rng = (
            random.Random(self.seed)
            if self.seed is not None
            else random.SystemRandom()
        )
        results = run_draft(config, rng)

        image = render_seat_chart(self.layout, results, self.photos_dir)
        if image.width > MAX_DISPLAY_WIDTH:
            scale = MAX_DISPLAY_WIDTH / image.width
            image = image.resize(
                (MAX_DISPLAY_WIDTH, int(image.height * scale)), Image.LANCZOS
            )

        self._tk_image = ImageTk.PhotoImage(image)
        self.canvas_label.configure(image=self._tk_image)

        # a fixed --seed would just redraw the same result every time
        self.seed = None


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
