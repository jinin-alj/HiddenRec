"""HiddenRec desktop form: styled trip setup, progress, and completion."""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
import urllib.request
from datetime import date
from pathlib import Path
from tkinter import messagebox

from hiddenrec_pipeline import default_exports_dir, run_hiddenrec_pipeline
from itinerary_models import TripParameters

try:
    from PIL import Image, ImageDraw, ImageFont, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# Window geometry
WINDOW_WIDTH = 540
WINDOW_HEIGHT = 760
WINDOW_TITLE = "HiddenRec"

# Sky gradient endpoints (RGB tuples)
SKY_TOP_RGB = (130, 180, 235)
SKY_BOTTOM_RGB = (210, 240, 255)
GRADIENT_STRIP_PX = 4

# Colors
COLOR_BLACK = "#111111"
COLOR_WHITE = "#ffffff"
COLOR_MUTED = "#888888"
COLOR_INPUT_BG = "#f8f8f8"
COLOR_INPUT_BORDER = "#dddddd"
COLOR_SEPARATOR = "#eeeeee"
COLOR_TOGGLE_ON = "#111111"
COLOR_TOGGLE_OFF = "#e0e0e0"
COLOR_TOGGLE_THUMB = "#ffffff"

# Typography
FONT_LABEL = ("Helvetica Neue", 10, "bold")
FONT_INPUT = ("Helvetica Neue", 13)
FONT_SECTION = ("Helvetica Neue", 14, "bold")
FONT_CAPTION = ("Helvetica Neue", 11)
FONT_BUTTON = ("Helvetica Neue", 18, "bold")
FONT_LOADING_TITLE = ("Helvetica Neue", 20, "bold")

# Toggle switch dimensions
TOGGLE_WIDTH = 48
TOGGLE_HEIGHT = 26
TOGGLE_THUMB_RADIUS = 10

# Cloud animation
CLOUD_ANIMATION_MS = 40

# Logo font
LOGO_FONT_SIZE = 56
LOGO_IMAGE_WIDTH = 340
LOGO_IMAGE_HEIGHT = 72
LOGO_OUTLINE_PX = 3
FREDOKA_CACHE_PATH = os.path.join(os.path.expanduser("~"), ".hiddenrec_fredoka.ttf")
FREDOKA_FONT_URL = (
    "https://github.com/google/fonts/raw/main/ofl/fredokaone/FredokaOne-Regular.ttf"
)

# Form defaults
DEFAULT_START_DATE = date.today().isoformat()
DEFAULT_TRIP_DAYS = "3"
DEFAULT_BUDGET = "500"
DEFAULT_CURRENCY = "EUR"
DEFAULT_TIMEZONE = "Europe/Madrid"
LANGUAGE_OPTIONS = ["auto", "en", "es", "fr", "de", "it", "pt", "ja", "nl"]


def lerp_rgb(color_a: tuple, color_b: tuple, t: float) -> str:
    """Interpolate between two RGB tuples and return a hex color string."""
    r = int(color_a[0] + (color_b[0] - color_a[0]) * t)
    g = int(color_a[1] + (color_b[1] - color_a[1]) * t)
    b = int(color_a[2] + (color_b[2] - color_a[2]) * t)
    return f"#{r:02x}{g:02x}{b:02x}"


def draw_rounded_rect(
    canvas: tk.Canvas,
    x1: float, y1: float,
    x2: float, y2: float,
    radius: float,
    **kwargs,
) -> int:
    """Draw a smooth rounded rectangle on a canvas using a B-spline polygon."""
    return canvas.create_polygon(
        x1 + radius, y1,
        x2 - radius, y1,
        x2,           y1,
        x2,           y1 + radius,
        x2,           y2 - radius,
        x2,           y2,
        x2 - radius,  y2,
        x1 + radius,  y2,
        x1,           y2,
        x1,           y2 - radius,
        x1,           y1 + radius,
        x1,           y1,
        smooth=True,
        **kwargs,
    )


def try_load_fredoka_font() -> object | None:
    """Download and cache the Fredoka One TTF font, returning a PIL ImageFont or None."""
    if not HAS_PIL:
        return None
    if not os.path.exists(FREDOKA_CACHE_PATH):
        try:
            urllib.request.urlretrieve(FREDOKA_FONT_URL, FREDOKA_CACHE_PATH)
        except Exception:
            return None
    try:
        return ImageFont.truetype(FREDOKA_CACHE_PATH, LOGO_FONT_SIZE)
    except Exception:
        return None


def build_logo_photo_image(pil_font: object | None, text: str = "HiddenRec") -> object | None:
    """
    Render text with an outlined style using PIL.
    Returns a Tkinter-compatible PhotoImage, or None if PIL is unavailable.
    """
    if not HAS_PIL or pil_font is None:
        return None

    image = Image.new("RGBA", (LOGO_IMAGE_WIDTH, LOGO_IMAGE_HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    origin = (LOGO_OUTLINE_PX, LOGO_OUTLINE_PX)

    # Outline pass: draw text offset in every direction
    for dx in range(-LOGO_OUTLINE_PX, LOGO_OUTLINE_PX + 1):
        for dy in range(-LOGO_OUTLINE_PX, LOGO_OUTLINE_PX + 1):
            if dx != 0 or dy != 0:
                draw.text(
                    (origin[0] + dx, origin[1] + dy),
                    text, font=pil_font, fill=(17, 17, 17, 255),
                )

    # Fill pass: white text on top of outline
    draw.text(origin, text, font=pil_font, fill=(255, 255, 255, 255))
    return ImageTk.PhotoImage(image)


def make_label(parent: tk.Widget, text: str) -> tk.Label:
    """Return a small uppercase muted label for use above form fields."""
    return tk.Label(
        parent,
        text=text.upper(),
        font=FONT_LABEL,
        fg=COLOR_MUTED,
        bg=COLOR_WHITE,
        anchor="w",
    )


def make_entry(parent: tk.Widget, **kwargs) -> tk.Entry:
    """Return a styled flat entry widget."""
    return tk.Entry(
        parent,
        font=FONT_INPUT,
        bg=COLOR_INPUT_BG,
        fg=COLOR_BLACK,
        relief=tk.FLAT,
        bd=0,
        highlightthickness=2,
        highlightbackground=COLOR_INPUT_BORDER,
        highlightcolor=COLOR_BLACK,
        insertbackground=COLOR_BLACK,
        **kwargs,
    )


def make_separator(parent: tk.Widget) -> tk.Frame:
    """Return a one-pixel horizontal separator."""
    return tk.Frame(parent, height=1, bg=COLOR_SEPARATOR)


def _open_folder(path: str) -> None:
    folder = str(Path(path).resolve().parent)
    try:
        if sys.platform == "darwin":
            subprocess.run(["open", folder], check=False)
        elif sys.platform.startswith("win"):
            os.startfile(folder)  # type: ignore[attr-defined]
        else:
            subprocess.run(["xdg-open", folder], check=False)
    except OSError as exc:
        messagebox.showwarning("HiddenRec", f"Could not open folder.\n{exc}")


def _open_file(path: str) -> None:
    try:
        if sys.platform == "darwin":
            subprocess.run(["open", path], check=False)
        elif sys.platform.startswith("win"):
            os.startfile(path)  # type: ignore[attr-defined]
        else:
            subprocess.run(["xdg-open", path], check=False)
    except OSError as exc:
        messagebox.showwarning(
            "HiddenRec",
            f"Could not open the file.\n{path}\n{exc}",
        )


class ToggleSwitch(tk.Canvas):
    """A custom toggle switch widget drawn entirely with Canvas primitives."""

    def __init__(self, parent: tk.Widget, **kwargs):
        super().__init__(
            parent,
            width=TOGGLE_WIDTH,
            height=TOGGLE_HEIGHT,
            bg=COLOR_WHITE,
            highlightthickness=0,
            bd=0,
            **kwargs,
        )
        self._value = False
        self._draw()
        self.bind("<Button-1>", self._on_click)

    def _draw(self) -> None:
        self.delete("all")
        track_color = COLOR_TOGGLE_ON if self._value else COLOR_TOGGLE_OFF
        draw_rounded_rect(
            self, 1, 1, TOGGLE_WIDTH - 1, TOGGLE_HEIGHT - 1,
            TOGGLE_HEIGHT // 2,
            fill=track_color, outline="#bbbbbb", width=1,
        )
        thumb_cx = (
            TOGGLE_WIDTH - TOGGLE_HEIGHT // 2 - 2
            if self._value
            else TOGGLE_HEIGHT // 2 + 2
        )
        thumb_cy = TOGGLE_HEIGHT // 2
        r = TOGGLE_THUMB_RADIUS
        self.create_oval(
            thumb_cx - r, thumb_cy - r,
            thumb_cx + r, thumb_cy + r,
            fill=COLOR_TOGGLE_THUMB, outline="#bbbbbb", width=1,
        )

    def _on_click(self, _event: tk.Event) -> None:
        self._value = not self._value
        self._draw()

    def get(self) -> bool:
        return self._value


class HiddenRecApp(tk.Tk):
    """Main application window with sky background, form, and loading states."""

    CLOUD_SPECS = [
        # (start_x, y, scale, speed_px_per_frame)
        (-320, 60,  1.0,  0.60),
        (140,  140, 0.70, 0.35),
        (-90,  240, 0.85, 0.45),
        (310,  400, 1.20, 0.28),
        (40,   520, 0.65, 0.38),
    ]

    FADE_STEP = 0.08
    FADE_INTERVAL_MS = 20

    def __init__(self):
        super().__init__()
        self.title(WINDOW_TITLE)
        self.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.resizable(False, False)

        self._cloud_positions = [[x, y] for x, y, *_ in self.CLOUD_SPECS]
        self._cloud_scales = [s for _, _, s, _ in self.CLOUD_SPECS]
        self._cloud_speeds = [sp for _, _, _, sp in self.CLOUD_SPECS]
        self._cloud_oval_ids: list[tuple] = []
        self._logo_photo_ref = None
        self._title_photo_ref = None

        self._bg_canvas = tk.Canvas(
            self, width=WINDOW_WIDTH, height=WINDOW_HEIGHT,
            highlightthickness=0, bd=0,
        )
        self._bg_canvas.pack(fill=tk.BOTH, expand=True)

        self._draw_sky_gradient()
        self._draw_clouds_initial()
        self._draw_logo()

        self._build_form()
        self._build_loading_items()
        self._build_done_card()

        self._log_queue: queue.Queue[str] = queue.Queue()
        self._animate_clouds()
        self._poll_queue()

    def _draw_sky_gradient(self) -> None:
        strips = WINDOW_HEIGHT // GRADIENT_STRIP_PX
        for i in range(strips):
            color = lerp_rgb(SKY_TOP_RGB, SKY_BOTTOM_RGB, i / strips)
            y = i * GRADIENT_STRIP_PX
            self._bg_canvas.create_rectangle(
                0, y, WINDOW_WIDTH, y + GRADIENT_STRIP_PX,
                fill=color, outline="",
            )

    def _draw_single_cloud(self, x: float, y: float, scale: float) -> tuple:
        body_w = int(200 * scale)
        body_h = int(50 * scale)
        bump1_r = int(66 * scale)
        bump2_r = int(52 * scale)

        body_id = self._bg_canvas.create_oval(
            x, y, x + body_w, y + body_h,
            fill=COLOR_WHITE, outline="",
        )
        bump1_id = self._bg_canvas.create_oval(
            x + int(28 * scale), y - bump1_r + int(20 * scale),
            x + int(28 * scale) + bump1_r * 2, y + int(20 * scale) + bump1_r,
            fill=COLOR_WHITE, outline="",
        )
        bump2_id = self._bg_canvas.create_oval(
            x + int(100 * scale), y - bump2_r + int(24 * scale),
            x + int(100 * scale) + bump2_r * 2, y + int(24 * scale) + bump2_r,
            fill=COLOR_WHITE, outline="",
        )
        return body_id, bump1_id, bump2_id

    def _draw_clouds_initial(self) -> None:
        for i, (x, y) in enumerate(self._cloud_positions):
            ids = self._draw_single_cloud(x, y, self._cloud_scales[i])
            self._cloud_oval_ids.append(ids)

    def _animate_clouds(self) -> None:
        for i in range(len(self._cloud_positions)):
            speed = self._cloud_speeds[i]
            self._cloud_positions[i][0] += speed
            for oval_id in self._cloud_oval_ids[i]:
                self._bg_canvas.move(oval_id, speed, 0)

            cloud_extent = int((200 + 132) * self._cloud_scales[i])
            if self._cloud_positions[i][0] > WINDOW_WIDTH + 60:
                reset_x = -(cloud_extent + 50)
                warp_dx = reset_x - self._cloud_positions[i][0]
                self._cloud_positions[i][0] = reset_x
                for oval_id in self._cloud_oval_ids[i]:
                    self._bg_canvas.move(oval_id, warp_dx, 0)

        self.after(CLOUD_ANIMATION_MS, self._animate_clouds)

    def _draw_logo(self) -> None:
        center_x = WINDOW_WIDTH // 2
        center_y = 68

        pil_font = try_load_fredoka_font()
        photo = build_logo_photo_image(pil_font)

        if photo is not None:
            self._logo_photo_ref = photo
            self._bg_canvas.create_image(
                center_x - 48, center_y,
                image=self._logo_photo_ref, anchor=tk.CENTER,
            )
            # Also build the loading title photo if we have the font
            self._title_photo_ref = build_logo_photo_image(pil_font, "BUILDING YOUR ITINERARY...")
        else:
            self._bg_canvas.create_text(
                center_x - 48, center_y,
                text="HiddenRec",
                font=("Helvetica Neue", 42, "bold"),
                fill=COLOR_BLACK, anchor=tk.CENTER,
            )

        self._draw_ticket(center_x + 148, center_y)

        self._bg_canvas.create_text(
            center_x, center_y + 45,
            text="Trip ideas from real posts. Your plan lands in a calendar file.",
            font=("Helvetica Neue", 10),
            fill=COLOR_BLACK, anchor=tk.CENTER,
        )

    def _draw_ticket(self, cx: float, cy: float) -> None:
        width, height = 92, 58
        x1, y1 = cx - width // 2, cy - height // 2

        draw_rounded_rect(
            self._bg_canvas,
            x1 + 6, y1 + 4, x1 + width + 6, y1 + height + 4, 8,
            fill="#c8c0b0", outline="",
        )
        draw_rounded_rect(
            self._bg_canvas, x1 + 6, y1 + 4, x1 + width + 6, y1 + height + 4, 8,
            fill="#e8e0d0", outline=COLOR_BLACK, width=2,
        )
        draw_rounded_rect(
            self._bg_canvas, x1, y1, x1 + width, y1 + height, 8,
            fill="#f5f0e8", outline=COLOR_BLACK, width=2,
        )
        self._bg_canvas.create_line(
            x1 + 28, y1, x1 + 28, y1 + height,
            fill=COLOR_BLACK, width=2, dash=(4, 3),
        )
        plane_cx, plane_cy = x1 + 14, cy
        self._bg_canvas.create_line(
            plane_cx - 8, plane_cy, plane_cx + 8, plane_cy,
            fill="#444444", width=3, capstyle=tk.ROUND,
        )
        self._bg_canvas.create_line(
            plane_cx, plane_cy - 7, plane_cx, plane_cy + 7,
            fill="#444444", width=3, capstyle=tk.ROUND,
        )
        self._bg_canvas.create_line(
            plane_cx - 5, plane_cy + 4, plane_cx + 5, plane_cy + 4,
            fill="#444444", width=2, capstyle=tk.ROUND,
        )
        for offset_y, line_w in [(10, 42), (20, 32), (30, 38), (40, 26)]:
            self._bg_canvas.create_rectangle(
                x1 + 36, y1 + offset_y,
                x1 + 36 + line_w, y1 + offset_y + 5,
                fill="#cccccc", outline="",
            )

    def _build_form(self) -> None:
        card_w = WINDOW_WIDTH - 48
        card_h = WINDOW_HEIGHT - 160
        card_x = 24
        card_y = 130

        draw_rounded_rect(
            self._bg_canvas,
            card_x + 5, card_y + 5,
            card_x + card_w + 5, card_y + card_h + 5,
            12, fill=COLOR_BLACK, outline="", tags="form_ui",
        )
        draw_rounded_rect(
            self._bg_canvas,
            card_x, card_y,
            card_x + card_w, card_y + card_h,
            12, fill=COLOR_WHITE, outline=COLOR_BLACK, width=2, tags="form_ui",
        )

        self._form_frame = tk.Frame(self._bg_canvas, bg=COLOR_WHITE)
        self._bg_canvas.create_window(
            card_x + 2, card_y + 2,
            window=self._form_frame,
            width=card_w - 4, height=card_h - 4,
            anchor=tk.NW, tags="form_ui",
        )

        self._form_frame.columnconfigure(1, weight=1)
        row = 0

        def add_row(r: int, label: str, widget: tk.Widget) -> None:
            make_label(self._form_frame, label).grid(
                row=r, column=0, sticky=tk.NW, pady=8, padx=(24, 12)
            )
            widget.grid(row=r, column=1, sticky=tk.EW, pady=8, padx=(0, 24))

        make_label(self._form_frame, "Where are you headed?").grid(
            row=row, column=0, columnspan=2, sticky=tk.W, pady=(20, 4), padx=24
        )
        row += 1
        self._city_entry = make_entry(self._form_frame)
        self._city_entry.grid(row=row, column=0, columnspan=2, sticky=tk.EW, padx=24, ipady=6)
        row += 1

        self._country_entry = make_entry(self._form_frame)
        add_row(row, "Country", self._country_entry)
        row += 1

        self._date_entry = make_entry(self._form_frame)
        self._date_entry.insert(0, DEFAULT_START_DATE)
        add_row(row, "Start date (YYYY-MM-DD)", self._date_entry)
        row += 1

        self._days_var = tk.StringVar(value=DEFAULT_TRIP_DAYS)
        days_spinbox = tk.Spinbox(
            self._form_frame, from_=1, to=30, textvariable=self._days_var,
            font=FONT_INPUT, bg=COLOR_INPUT_BG, fg=COLOR_BLACK,
            relief=tk.FLAT, bd=0, highlightthickness=2,
            highlightbackground=COLOR_INPUT_BORDER, highlightcolor=COLOR_BLACK,
            buttonbackground=COLOR_INPUT_BG,
        )
        add_row(row, "Trip length (days)", days_spinbox)
        row += 1

        self._budget_entry = make_entry(self._form_frame)
        self._budget_entry.insert(0, DEFAULT_BUDGET)
        add_row(row, "Total budget", self._budget_entry)
        row += 1

        self._currency_entry = make_entry(self._form_frame)
        self._currency_entry.insert(0, DEFAULT_CURRENCY)
        add_row(row, "Currency", self._currency_entry)
        row += 1

        make_separator(self._form_frame).grid(
            row=row, column=0, columnspan=2, sticky="ew", padx=24, pady=12
        )
        row += 1

        food_row = tk.Frame(self._form_frame, bg=COLOR_WHITE)
        food_row.grid(row=row, column=0, columnspan=2, sticky="ew", padx=24, pady=4)
        food_row.columnconfigure(0, weight=1)

        food_info = tk.Frame(food_row, bg=COLOR_WHITE)
        food_info.grid(row=0, column=0, sticky="w")
        tk.Label(food_info, text="Food only", font=FONT_SECTION, fg=COLOR_BLACK, bg=COLOR_WHITE).pack(anchor="w")
        tk.Label(food_info, text="Restaurants and local eats exclusively", font=FONT_CAPTION, fg=COLOR_MUTED, bg=COLOR_WHITE).pack(anchor="w")

        self._food_toggle = ToggleSwitch(food_row)
        self._food_toggle.grid(row=0, column=1, sticky="e")
        row += 1

        make_separator(self._form_frame).grid(
            row=row, column=0, columnspan=2, sticky="ew", padx=24, pady=12
        )
        row += 1

        self._tz_entry = make_entry(self._form_frame)
        self._tz_entry.insert(0, DEFAULT_TIMEZONE)
        add_row(row, "Timezone (IANA)", self._tz_entry)
        row += 1

        self._lang_var = tk.StringVar(value="auto")
        lang_menu = tk.OptionMenu(self._form_frame, self._lang_var, *LANGUAGE_OPTIONS)
        lang_menu.configure(
            font=FONT_INPUT, bg=COLOR_INPUT_BG, fg=COLOR_BLACK,
            relief=tk.FLAT, bd=0, highlightthickness=2,
            highlightbackground=COLOR_INPUT_BORDER,
            activebackground=COLOR_INPUT_BG, activeforeground=COLOR_BLACK,
        )
        lang_menu["menu"].configure(font=FONT_INPUT, bg=COLOR_INPUT_BG)
        add_row(row, "Search language", lang_menu)
        row += 1

        tk.Label(
            self._form_frame, text="Sources: Reddit, TikTok, Pinterest.",
            font=FONT_CAPTION, fg=COLOR_MUTED, bg=COLOR_WHITE,
        ).grid(row=row, column=0, columnspan=2, sticky="w", padx=24, pady=(8, 0))
        row += 1

        self._submit_btn = tk.Button(
            self._form_frame, text="Let's go", font=FONT_BUTTON,
            bg=COLOR_WHITE, fg=COLOR_BLACK, relief=tk.FLAT, bd=0,
            activebackground="#333333", activeforeground=COLOR_BLACK,
            cursor="hand2", command=self._submit,
        )
        self._submit_btn.grid(
            row=row, column=0, columnspan=2, sticky="ew",
            padx=24, pady=(24, 24), ipady=12,
        )

    def _build_loading_items(self) -> None:
        cx = WINDOW_WIDTH // 2
        cy = WINDOW_HEIGHT // 2

        if self._title_photo_ref:
            self._bg_canvas.create_image(
                cx, cy - 60,
                image=self._title_photo_ref, anchor=tk.CENTER,
                tags="loading_ui", state=tk.HIDDEN,
            )
        else:
            self._bg_canvas.create_text(
                cx, cy - 60,
                text="BUILDING YOUR ITINERARY...",
                font=FONT_LOADING_TITLE, fill=COLOR_BLACK,
                anchor=tk.CENTER, tags="loading_ui", state=tk.HIDDEN,
            )

        bar_w = 420
        bar_h = 56
        x1, y1 = cx - bar_w // 2, cy - bar_h // 2
        x2, y2 = cx + bar_w // 2, cy + bar_h // 2
        r = bar_h // 2

        draw_rounded_rect(
            self._bg_canvas, x1, y1, x2, y2, r,
            fill=COLOR_BLACK, outline="", tags="loading_ui", state=tk.HIDDEN,
        )
        draw_rounded_rect(
            self._bg_canvas, x1 + 4, y1 + 4, x2 - 4, y2 - 4, r - 4,
            fill=COLOR_WHITE, outline="", tags="loading_ui", state=tk.HIDDEN,
        )

        self._progress_fill_id = draw_rounded_rect(
            self._bg_canvas, x1 + 8, y1 + 8, x1 + 10, y2 - 8, r - 8,
            fill=COLOR_BLACK, outline="", tags="loading_ui", state=tk.HIDDEN,
        )
        self._progress_coords = (x1 + 8, y1 + 8, x2 - 8, y2 - 8, r - 8)

        self._status_text_id = self._bg_canvas.create_text(
            cx, cy + 50,
            text="Preparing...",
            font=FONT_CAPTION, fill=COLOR_BLACK,
            anchor=tk.CENTER, tags="loading_ui", state=tk.HIDDEN,
        )

    def _update_progress(self, fraction: float) -> None:
        fraction = max(0.0, min(1.0, fraction))
        x1, y1, x2, y2, r = self._progress_coords
        w = x2 - x1
        fill_w = int(fraction * w)
        if fill_w < r * 2:
            fill_w = r * 2

        self._bg_canvas.delete(self._progress_fill_id)
        self._progress_fill_id = draw_rounded_rect(
            self._bg_canvas, x1, y1, x1 + fill_w, y2, r,
            fill=COLOR_BLACK, outline="", tags="loading_ui",
        )

    def _build_done_card(self) -> None:
        card_w = 420
        card_h = 240
        card_x = (WINDOW_WIDTH - card_w) // 2
        card_y = (WINDOW_HEIGHT - card_h) // 2

        draw_rounded_rect(
            self._bg_canvas,
            card_x + 5, card_y + 5,
            card_x + card_w + 5, card_y + card_h + 5,
            12, fill=COLOR_BLACK, outline="", tags="done_ui", state=tk.HIDDEN,
        )
        draw_rounded_rect(
            self._bg_canvas,
            card_x, card_y,
            card_x + card_w, card_y + card_h,
            12, fill=COLOR_WHITE, outline=COLOR_BLACK, width=2, tags="done_ui", state=tk.HIDDEN,
        )

        self._done_frame = tk.Frame(self._bg_canvas, bg=COLOR_WHITE)
        self._bg_canvas.create_window(
            card_x + 2, card_y + 2,
            window=self._done_frame,
            width=card_w - 4, height=card_h - 4,
            anchor=tk.NW, tags="done_ui", state=tk.HIDDEN,
        )

        tk.Label(
            self._done_frame, text="Your itinerary is ready!",
            font=FONT_SECTION, bg=COLOR_BLACK, fg=COLOR_BLACK,
        ).pack(pady=(24, 8))

        self._done_path_label = tk.Label(
            self._done_frame, text="",
            font=FONT_CAPTION, bg=COLOR_WHITE, fg=COLOR_MUTED,
            wraplength=380, justify=tk.CENTER,
        )
        self._done_path_label.pack(pady=(0, 24))

        btn_row = tk.Frame(self._done_frame, bg=COLOR_WHITE)
        btn_row.pack()

        self._path_var = ""

        tk.Button(
            btn_row, text="Open file", font=FONT_CAPTION,
            bg=COLOR_WHITE, fg=COLOR_BLACK, relief=tk.FLAT, bd=0,
            activebackground="#333333", activeforeground=COLOR_BLACK,
            cursor="hand2", command=lambda: _open_file(self._path_var),
        ).pack(side=tk.LEFT, padx=6, ipady=6, ipadx=12)

        tk.Button(
            btn_row, text="Open folder", font=FONT_CAPTION,
            bg=COLOR_INPUT_BG, fg=COLOR_BLACK, relief=tk.FLAT, bd=0,
            highlightthickness=1, highlightbackground=COLOR_INPUT_BORDER,
            activebackground=COLOR_INPUT_BORDER, activeforeground=COLOR_BLACK,
            cursor="hand2", command=lambda: _open_folder(self._path_var),
        ).pack(side=tk.LEFT, padx=6, ipady=6, ipadx=12)

        tk.Button(
            self._done_frame, text="Plan another trip", font=FONT_CAPTION,
            bg=COLOR_WHITE, fg=COLOR_BLACK, relief=tk.FLAT, bd=0,
            cursor="hand2", command=self._reset_to_form,
        ).pack(pady=(20, 0))

    def _fade(self, direction: str, alpha: float = None, on_complete: callable = None) -> None:
        if alpha is None:
            alpha = 1.0 if direction == "out" else 0.0

        self.attributes("-alpha", alpha)

        if direction == "out":
            next_alpha = alpha - self.FADE_STEP
            if next_alpha > 0.0:
                self.after(self.FADE_INTERVAL_MS, lambda: self._fade("out", next_alpha, on_complete))
            else:
                self.attributes("-alpha", 0.0)
                if on_complete:
                    on_complete()
        else:
            next_alpha = alpha + self.FADE_STEP
            if next_alpha < 1.0:
                self.after(self.FADE_INTERVAL_MS, lambda: self._fade("in", next_alpha))
            else:
                self.attributes("-alpha", 1.0)

    def _submit(self) -> None:
        city = self._city_entry.get().strip()
        if not city:
            self._city_entry.focus_set()
            return

        country = self._country_entry.get().strip()
        if not country:
            messagebox.showwarning("HiddenRec", "Please enter a country.")
            self._country_entry.focus_set()
            return

        try:
            num_days = int(self._days_var.get())
        except ValueError:
            num_days = 3

        try:
            self._current_trip = TripParameters(
                city=city,
                country_hint=country,
                start_date=date.fromisoformat(self._date_entry.get().strip()),
                num_days=num_days,
                budget_amount=float(self._budget_entry.get().strip().replace(",", ".")),
                currency=self._currency_entry.get().strip() or DEFAULT_CURRENCY,
                food_focused=self._food_toggle.get(),
                timezone=self._tz_entry.get().strip() or DEFAULT_TIMEZONE,
                locale_queries=self._lang_var.get(),
            )
        except Exception as exc:
            messagebox.showerror("HiddenRec", f"Invalid input:\n{exc}")
            return

        self._submit_btn.configure(state=tk.DISABLED)
        self._fade("out", on_complete=self._start_loading)

    def _start_loading(self) -> None:
        self._bg_canvas.itemconfigure("form_ui", state=tk.HIDDEN)
        self._bg_canvas.itemconfigure("loading_ui", state=tk.NORMAL)
        self._update_progress(0.0)
        self._bg_canvas.itemconfigure(self._status_text_id, text="Preparing...")
        self._fade("in")

        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self) -> None:
        try:
            def log_from_thread(text: str) -> None:
                self._log_queue.put(f"STATUS|{text}")

            def on_progress(phase: str, fraction: float) -> None:
                self._log_queue.put(f"PROGRESS|{fraction:.4f}")

            output_path = run_hiddenrec_pipeline(
                self._current_trip,
                log_from_thread,
                on_progress=on_progress,
            )
            self._log_queue.put(f"SUCCESS|{output_path!s}")
        except Exception as exc:
            self._log_queue.put(f"ERROR|{exc}")

    def _poll_queue(self) -> None:
        try:
            while True:
                msg = self._log_queue.get_nowait()
                if msg.startswith("PROGRESS|"):
                    try:
                        frac = float(msg.split("|")[1])
                        self._update_progress(frac)
                    except ValueError:
                        pass
                elif msg.startswith("STATUS|"):
                    text = msg.split("|", 1)[1]
                    self._bg_canvas.itemconfigure(self._status_text_id, text=text)
                elif msg.startswith("SUCCESS|"):
                    path = msg.split("|", 1)[1]
                    self._show_done(path)
                elif msg.startswith("ERROR|"):
                    err = msg.split("|", 1)[1]
                    self._show_error(err)
        except queue.Empty:
            pass
        self.after(150, self._poll_queue)

    def _show_done(self, path: str) -> None:
        self._path_var = path
        self._done_path_label.configure(
            text=f"Calendar file saved next to this project:\n{path}\n\n"
                 f"Folder: {default_exports_dir()}"
        )
        self._fade("out", on_complete=self._reveal_done_card)

    def _reveal_done_card(self) -> None:
        self._bg_canvas.itemconfigure("loading_ui", state=tk.HIDDEN)
        self._bg_canvas.itemconfigure("done_ui", state=tk.NORMAL)
        self._fade("in")

    def _show_error(self, err: str) -> None:
        self._fade("out", on_complete=lambda: self._reveal_error(err))

    def _reveal_error(self, err: str) -> None:
        self._bg_canvas.itemconfigure("loading_ui", state=tk.HIDDEN)
        self._bg_canvas.itemconfigure("form_ui", state=tk.NORMAL)
        self._submit_btn.configure(state=tk.NORMAL)
        self._fade("in")
        messagebox.showerror("HiddenRec", f"An error occurred:\n{err}")

    def _reset_to_form(self) -> None:
        self._fade("out", on_complete=self._reveal_form)

    def _reveal_form(self) -> None:
        self._bg_canvas.itemconfigure("done_ui", state=tk.HIDDEN)
        self._bg_canvas.itemconfigure("form_ui", state=tk.NORMAL)
        self._submit_btn.configure(state=tk.NORMAL)
        self._fade("in")


def run_hiddenrec_app() -> None:
    app = HiddenRecApp()
    app.mainloop()


if __name__ == "__main__":
    run_hiddenrec_app()
