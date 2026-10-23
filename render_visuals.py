"""Render exact verification views from the generated KiCad library.

The script reads the footprint, symbol, and pinout files in this directory and
emits editable SVG plus high-resolution PNG views under visuals/.
"""

from __future__ import annotations

import csv
import html
import math
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "visuals"
FOOTPRINT = ROOT / "PCA10059_nRF52840_Dongle.pretty" / "PCA10059_nRF52840_Dongle.kicad_mod"
SYMBOL = ROOT / "PCA10059_nRF52840_Dongle.kicad_sym"
PINOUT = ROOT / "pinout.csv"

BG = "#F4F7FB"
CARD = "#FFFFFF"
INK = "#172033"
MUTED = "#637083"
BOARD = "#DCE8F5"
BOARD_EDGE = "#183E6B"
PAD = "#E99B27"
PAD_EDGE = "#8A5412"
KEEP = "#E5484D"
GRID = "#B9C5D5"
POWER = "#C33A3A"
GPIO = "#2563A5"
INPUT = "#16835E"


def color_rgba(value: str, opacity: float = 1.0) -> tuple[int, int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4)) + (round(255 * opacity),)


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    choices = [
        Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf"),
    ]
    for choice in choices:
        if choice.exists():
            return ImageFont.truetype(str(choice), size)
    return ImageFont.load_default()


class Canvas:
    def __init__(self, width: int, height: int, title: str, desc: str):
        self.width = width
        self.height = height
        self.title = title
        self.desc = desc
        self.image = Image.new("RGBA", (width, height), color_rgba(BG))
        self.draw = ImageDraw.Draw(self.image, "RGBA")
        self.svg: list[str] = [f'<rect width="{width}" height="{height}" fill="{BG}"/>']

    def rect(self, x: float, y: float, w: float, h: float, *, fill: str = "none", stroke: str = "none", sw: float = 1, radius: float = 0, opacity: float = 1.0, dash: str | None = None):
        if fill != "none":
            self.draw.rounded_rectangle((x, y, x + w, y + h), radius=radius, fill=color_rgba(fill, opacity))
        if stroke != "none":
            self.draw.rounded_rectangle((x, y, x + w, y + h), radius=radius, outline=color_rgba(stroke, opacity), width=max(1, round(sw)))
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        self.svg.append(f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" rx="{radius:.2f}" fill="{fill}" fill-opacity="{opacity:.3f}" stroke="{stroke}" stroke-width="{sw:.2f}"{dash_attr}/>' )

    def line(self, x1: float, y1: float, x2: float, y2: float, *, stroke: str = INK, sw: float = 2, opacity: float = 1.0, dash: str | None = None):
        if dash:
            length = math.hypot(x2 - x1, y2 - y1)
            unit_x = (x2 - x1) / length if length else 0
            unit_y = (y2 - y1) / length if length else 0
            pattern = [float(p) for p in dash.split()]
            pos = 0.0
            draw_on = True
            i = 0
            while pos < length:
                step = min(pattern[i % len(pattern)], length - pos)
                if draw_on:
                    self.draw.line((x1 + unit_x * pos, y1 + unit_y * pos, x1 + unit_x * (pos + step), y1 + unit_y * (pos + step)), fill=color_rgba(stroke, opacity), width=max(1, round(sw)))
                pos += step
                draw_on = not draw_on
                i += 1
        else:
            self.draw.line((x1, y1, x2, y2), fill=color_rgba(stroke, opacity), width=max(1, round(sw)))
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        self.svg.append(f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" stroke="{stroke}" stroke-opacity="{opacity:.3f}" stroke-width="{sw:.2f}" stroke-linecap="round"{dash_attr}/>' )

    def polygon(self, points: list[tuple[float, float]], *, fill: str = "none", stroke: str = "none", sw: float = 1, opacity: float = 1.0):
        if fill != "none":
            self.draw.polygon(points, fill=color_rgba(fill, opacity))
        if stroke != "none":
            self.draw.line(points + [points[0]], fill=color_rgba(stroke, opacity), width=max(1, round(sw)), joint="curve")
        pts = " ".join(f"{x:.2f},{y:.2f}" for x, y in points)
        self.svg.append(f'<polygon points="{pts}" fill="{fill}" fill-opacity="{opacity:.3f}" stroke="{stroke}" stroke-width="{sw:.2f}" stroke-linejoin="round"/>')

    def circle(self, x: float, y: float, r: float, *, fill: str = "none", stroke: str = "none", sw: float = 1, opacity: float = 1.0):
        if fill != "none":
            self.draw.ellipse((x - r, y - r, x + r, y + r), fill=color_rgba(fill, opacity))
        if stroke != "none":
            self.draw.ellipse((x - r, y - r, x + r, y + r), outline=color_rgba(stroke, opacity), width=max(1, round(sw)))
        self.svg.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{r:.2f}" fill="{fill}" fill-opacity="{opacity:.3f}" stroke="{stroke}" stroke-width="{sw:.2f}"/>')

    def text(self, x: float, y: float, value: str, *, size: int = 22, fill: str = INK, anchor: str = "middle", bold: bool = False, opacity: float = 1.0):
        anchor_map = {"start": "lm", "middle": "mm", "end": "rm"}
        self.draw.text((x, y), value, font=load_font(size, bold), fill=color_rgba(fill, opacity), anchor=anchor_map[anchor])
        weight = "700" if bold else "400"
        self.svg.append(f'<text x="{x:.2f}" y="{y:.2f}" text-anchor="{anchor}" dominant-baseline="middle" font-family="Arial, Helvetica, sans-serif" font-size="{size}" font-weight="{weight}" fill="{fill}" fill-opacity="{opacity:.3f}">{html.escape(value)}</text>')

    def save(self, stem: str):
        OUT.mkdir(exist_ok=True)
        png_path = OUT / f"{stem}.png"
        svg_path = OUT / f"{stem}.svg"
        self.image.convert("RGB").save(png_path, quality=95)
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.width} {self.height}" width="{self.width}" height="{self.height}" role="img" aria-labelledby="title desc">'
            f'<title id="title">{html.escape(self.title)}</title>'
            f'<desc id="desc">{html.escape(self.desc)}</desc>'
            + "".join(self.svg)
            + "</svg>"
        )
        svg_path.write_text(svg, encoding="utf-8")
        return png_path, svg_path


def blocks(text: str, token: str) -> list[str]:
    result: list[str] = []
    cursor = 0
    needle = f"({token}"
    while True:
        start = text.find(needle, cursor)
        if start < 0:
            break
        depth = 0
        quoted = False
        escaped = False
        for i in range(start, len(text)):
            ch = text[i]
            if quoted:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    quoted = False
            elif ch == '"':
                quoted = True
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    result.append(text[start : i + 1])
                    cursor = i + 1
                    break
        else:
            raise ValueError(f"Unclosed {token} block")
    return result


def parse_library():
    mod = FOOTPRINT.read_text(encoding="utf-8")
    sym = SYMBOL.read_text(encoding="utf-8")
    with PINOUT.open(encoding="utf-8", newline="") as handle:
        pinout = {int(row["Pin"]): row for row in csv.DictReader(handle)}

    pads = []
    for block in blocks(mod, "pad"):
        m = re.search(r'^\(pad\s+"(\d+)"\s+smd\s+roundrect', block)
        at = re.search(r'\(at\s+([-\d.]+)\s+([-\d.]+)', block)
        size = re.search(r'\(size\s+([-\d.]+)\s+([-\d.]+)', block)
        if m and at and size:
            pads.append({"number": int(m.group(1)), "x": float(at.group(1)), "y": float(at.group(2)), "w": float(size.group(1)), "h": float(size.group(2))})

    fab_lines = []
    for block in blocks(mod, "fp_line"):
        if '(layer "F.Fab")' not in block:
            continue
        start = re.search(r'\(start\s+([-\d.]+)\s+([-\d.]+)', block)
        end = re.search(r'\(end\s+([-\d.]+)\s+([-\d.]+)', block)
        if start and end:
            fab_lines.append(((float(start.group(1)), float(start.group(2))), (float(end.group(1)), float(end.group(2)))))

    symbol_pins = []
    for block in blocks(sym, "pin"):
        head = re.search(r'^\(pin\s+(\S+)\s+(\S+)', block)
        at = re.search(r'\(at\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)', block)
        name = re.search(r'\(name\s+"([^"]*)"', block)
        number = re.search(r'\(number\s+"(\d+)"', block)
        if head and at and name and number:
            symbol_pins.append({"type": head.group(1), "x": float(at.group(1)), "y": float(at.group(2)), "angle": float(at.group(3)), "name": name.group(1), "number": int(number.group(1))})

    pads.sort(key=lambda item: item["number"])
    symbol_pins.sort(key=lambda item: item["number"])
    assert [p["number"] for p in pads] == list(range(1, 23))
    assert [p["number"] for p in symbol_pins] == list(range(1, 23))
    assert all(pinout[p["number"]]["Signal"] == p["name"] for p in symbol_pins)
    assert len(fab_lines) == 8
    return pads, fab_lines, symbol_pins, pinout


def heading(c: Canvas, title: str, subtitle: str):
    c.text(70, 62, title, size=34, bold=True, anchor="start")
    c.text(70, 102, subtitle, size=19, fill=MUTED, anchor="start")
    c.line(70, 130, c.width - 70, 130, stroke=GRID, sw=2)


def hatch(c: Canvas, x: float, y: float, w: float, h: float):
    c.rect(x, y, w, h, fill=KEEP, stroke=KEEP, sw=2, opacity=0.12, dash="8 6")
    step = 18
    for off in range(-round(h), round(w) + round(h), step):
        x1 = max(x, x + off)
        y1 = y + max(0, -off)
        x2 = min(x + w, x + off + h)
        y2 = y + min(h, h + off)
        if x2 >= x1:
            c.line(x1, y1, x2, y2, stroke=KEEP, sw=1, opacity=0.25)


def arrow_h(c: Canvas, x1: float, x2: float, y: float, label: str, color: str = BOARD_EDGE):
    c.line(x1, y, x2, y, stroke=color, sw=2)
    c.polygon([(x1, y), (x1 + 12, y - 7), (x1 + 12, y + 7)], fill=color)
    c.polygon([(x2, y), (x2 - 12, y - 7), (x2 - 12, y + 7)], fill=color)
    c.rect((x1 + x2) / 2 - 78, y - 17, 156, 34, fill=BG)
    c.text((x1 + x2) / 2, y, label, size=19, fill=color, bold=True)


def arrow_v(c: Canvas, x: float, y1: float, y2: float, label: str, color: str = BOARD_EDGE):
    c.line(x, y1, x, y2, stroke=color, sw=2)
    c.polygon([(x, y1), (x - 7, y1 + 12), (x + 7, y1 + 12)], fill=color)
    c.polygon([(x, y2), (x - 7, y2 - 12), (x + 7, y2 - 12)], fill=color)
    c.rect(x - 62, (y1 + y2) / 2 - 17, 124, 34, fill=BG)
    c.text(x, (y1 + y2) / 2, label, size=19, fill=color, bold=True)


def render_footprint(pads, fab_lines, pinout):
    c = Canvas(1800, 950, "PCA10059 top footprint verification", "Top view of the generated carrier-board footprint with exact outline, numbered pads, signals, and antenna keepout.")
    heading(c, "PCA10059 carrier footprint — top view", "USB plug points right • pin 1 is upper-left • dimensions in millimetres")
    scale, cx, cy = 27.5, 900, 455
    tx = lambda x: cx + x * scale
    ty = lambda y: cy - y * scale
    outline_mm = [fab_lines[0][0]] + [line[1] for line in fab_lines]
    outline_px = [(tx(x), ty(y)) for x, y in outline_mm[:-1]]
    c.polygon(outline_px, fill=BOARD, stroke=BOARD_EDGE, sw=4)
    hatch(c, tx(-23.02002), ty(7.62), 8.0 * scale, 15.24 * scale)
    c.text(tx(-19.02), cy - 12, "ANTENNA", size=20, fill=KEEP, bold=True)
    c.text(tx(-19.02), cy + 18, "NO COPPER BELOW", size=14, fill=KEEP)
    c.rect(tx(8.61822), ty(6.00964), (23.02002 - 8.61822) * scale, 12.01928 * scale, fill="#BCD0E6", opacity=0.35)
    c.text(tx(17.0), cy, "USB PLUG\nENVELOPE".replace("\n", " / "), size=18, fill=BOARD_EDGE, bold=True)

    for pad in pads:
        x, y = tx(pad["x"]), ty(pad["y"])
        w, h = pad["w"] * scale, pad["h"] * scale
        c.rect(x - w / 2, y - h / 2, w, h, fill=PAD, stroke=PAD_EDGE, sw=2, radius=8)
        c.circle(x, y, 3, fill=PAD_EDGE)
        c.text(x, y, str(pad["number"]), size=15, fill="#FFFFFF", bold=True)

    top = [p for p in pads if abs(p["y"] - 7.62) < 0.01]
    bottom = [p for p in pads if abs(p["y"] + 7.62) < 0.01]
    for pad in top:
        x = tx(pad["x"])
        c.line(x, ty(8.85), x, 182, stroke=GRID, sw=1)
        c.text(x, 158, f'{pad["number"]}', size=16, fill=PAD_EDGE, bold=True)
        c.text(x, 180, pinout[pad["number"]]["Signal"], size=14, fill=INK)
    for pad in bottom:
        x = tx(pad["x"])
        c.line(x, ty(-8.85), x, 748, stroke=GRID, sw=1)
        c.text(x, 765, pinout[pad["number"]]["Signal"], size=14, fill=INK)
        c.text(x, 787, f'{pad["number"]}', size=16, fill=PAD_EDGE, bold=True)

    for number, label_y in ((11, 192), (12, 714)):
        pad = pads[number - 1]
        x, y = tx(pad["x"]), ty(pad["y"])
        callout_x = x + 150
        c.line(x + 36, y, callout_x - 12, label_y, stroke=GRID, sw=2)
        c.text(callout_x, label_y - 11, f'{number}  {pinout[number]["Signal"]}', size=17, fill=INK, bold=True, anchor="start")
        c.text(callout_x, label_y + 13, "USB-neck castellation", size=13, fill=MUTED, anchor="start")

    c.circle(cx, cy, 8, fill="#FFFFFF", stroke=KEEP, sw=2)
    c.line(cx - 16, cy, cx + 16, cy, stroke=KEEP, sw=2)
    c.line(cx, cy - 16, cx, cy + 16, stroke=KEEP, sw=2)
    c.text(cx + 22, cy - 18, "footprint origin", size=13, fill=KEEP, anchor="start")
    arrow_h(c, tx(-23.02002), tx(23.02002), 868, "46.04 overall")
    c.rect(78, 830, 18, 18, fill=PAD, stroke=PAD_EDGE, sw=1, radius=4)
    c.text(106, 839, "host-board solder pads", size=15, fill=MUTED, anchor="start")
    c.rect(78, 862, 18, 18, fill=KEEP, opacity=0.16, stroke=KEEP, sw=1)
    c.text(106, 871, "antenna keepout guide", size=15, fill=MUTED, anchor="start")
    return c.save("footprint_top")


def render_mechanical(pads, fab_lines, pinout):
    c = Canvas(1800, 1000, "PCA10059 mechanical verification", "Dimensioned outline and pad-center view derived from the footprint and Nordic manufacturing coordinates.")
    heading(c, "PCA10059 mechanical verification", "Exact F.Fab outline and pad centres • host land sizes shown in orange")
    scale, cx, cy = 27.5, 925, 425
    tx = lambda x: cx + x * scale
    ty = lambda y: cy - y * scale
    outline_mm = [fab_lines[0][0]] + [line[1] for line in fab_lines]
    outline_px = [(tx(x), ty(y)) for x, y in outline_mm[:-1]]
    c.polygon(outline_px, fill="#FFFFFF", stroke=BOARD_EDGE, sw=4)
    c.line(tx(-23.5), cy, tx(23.5), cy, stroke=GRID, sw=1, dash="10 8")
    c.line(cx, ty(8.6), cx, ty(-8.6), stroke=GRID, sw=1, dash="10 8")
    for pad in pads:
        x, y = tx(pad["x"]), ty(pad["y"])
        c.rect(x - pad["w"] * scale / 2, y - pad["h"] * scale / 2, pad["w"] * scale, pad["h"] * scale, fill=PAD, stroke=PAD_EDGE, sw=2, radius=7, opacity=0.78)
        c.circle(x, y, 4, fill="#FFFFFF", stroke=PAD_EDGE, sw=2)
        c.text(x, y, str(pad["number"]), size=14, fill=PAD_EDGE, bold=True)
    c.circle(cx, cy, 8, fill="#FFFFFF", stroke=KEEP, sw=2)
    c.line(cx - 18, cy, cx + 18, cy, stroke=KEEP, sw=2)
    c.line(cx, cy - 18, cx, cy + 18, stroke=KEEP, sw=2)

    y_overall = 830
    c.line(tx(-23.02002), ty(-7.62), tx(-23.02002), y_overall, stroke=GRID, sw=1)
    c.line(tx(23.02002), ty(-6.00964), tx(23.02002), y_overall, stroke=GRID, sw=1)
    arrow_h(c, tx(-23.02002), tx(23.02002), y_overall, "46.04")
    y_body = 755
    c.line(tx(7.00786), ty(-7.62), tx(7.00786), y_body, stroke=GRID, sw=1)
    arrow_h(c, tx(-23.02002), tx(7.00786), y_body, "30.03 body")
    y_usb = 700
    c.line(tx(8.61822), ty(-6.00964), tx(8.61822), y_usb, stroke=GRID, sw=1)
    arrow_h(c, tx(8.61822), tx(23.02002), y_usb, "14.40 USB tongue")
    x_width = 180
    c.line(x_width, ty(7.62), tx(-23.02002), ty(7.62), stroke=GRID, sw=1)
    c.line(x_width, ty(-7.62), tx(-23.02002), ty(-7.62), stroke=GRID, sw=1)
    arrow_v(c, x_width, ty(7.62), ty(-7.62), "15.24")
    x_usb_width = 1615
    c.line(tx(23.02002), ty(6.00964), x_usb_width, ty(6.00964), stroke=GRID, sw=1)
    c.line(tx(23.02002), ty(-6.00964), x_usb_width, ty(-6.00964), stroke=GRID, sw=1)
    arrow_v(c, x_usb_width, ty(6.00964), ty(-6.00964), "12.02")

    p1, p2 = pads[0], pads[1]
    y_pitch = 165
    c.line(tx(p1["x"]), y_pitch, tx(p1["x"]), ty(p1["y"]) - 38, stroke=GRID, sw=1)
    c.line(tx(p2["x"]), y_pitch, tx(p2["x"]), ty(p2["y"]) - 38, stroke=GRID, sw=1)
    arrow_h(c, tx(p1["x"]), tx(p2["x"]), y_pitch, "2.54 pitch")
    c.text(900, 910, "Main pad centres y = ±7.62 • SWD pad centres x = 10.63498 relative to origin • origin = overall-length centre", size=18, fill=MUTED)
    c.text(900, 945, "Main lands 1.50 × 2.40 • SWD lands 2.20 × 2.40", size=18, fill=MUTED, bold=True)
    return c.save("mechanical_dimensions")


def render_symbol(symbol_pins):
    c = Canvas(1400, 1000, "PCA10059 schematic symbol verification", "Rendered schematic symbol with all 22 pin numbers, signal names, and electrical types.")
    heading(c, "PCA10059 schematic symbol", "22 pins • names and electrical types read from the generated .kicad_sym")
    scale, cx, cy = 20.0, 700, 520
    tx = lambda x: cx + x * scale
    ty = lambda y: cy - y * scale
    x1, x2 = tx(-15.24), tx(15.24)
    y1, y2 = ty(12.7), ty(-12.7)
    c.rect(x1, y1, x2 - x1, y2 - y1, fill="#EEF4FA", stroke=BOARD_EDGE, sw=4, radius=16)
    c.text(cx, cy - 18, "nRF52840 USB DONGLE", size=27, fill=BOARD_EDGE, bold=True)
    c.text(cx, cy + 22, "PCA10059", size=23, fill=MUTED)

    def pin_color(kind: str) -> str:
        if kind.startswith("power"):
            return POWER
        if kind == "input":
            return INPUT
        return GPIO

    for pin in symbol_pins:
        x, y = tx(pin["x"]), ty(pin["y"])
        angle = pin["angle"]
        length = 2.54 * scale
        color = pin_color(pin["type"])
        dx = math.cos(math.radians(angle)) * length
        dy = -math.sin(math.radians(angle)) * length
        end_x, end_y = x + dx, y + dy
        c.line(x, y, end_x, end_y, stroke=color, sw=4)
        c.circle(x, y, 5, fill="#FFFFFF", stroke=color, sw=3)
        if angle == 0:
            c.text(x - 14, y - 13, str(pin["number"]), size=15, fill=color, bold=True, anchor="end")
            c.text(end_x + 12, end_y, pin["name"], size=17, fill=INK, anchor="start")
        elif angle == 180:
            c.text(x + 14, y - 13, str(pin["number"]), size=15, fill=color, bold=True, anchor="start")
            c.text(end_x - 12, end_y, pin["name"], size=17, fill=INK, anchor="end")
        elif angle == 270:
            c.text(x + 14, y - 8, str(pin["number"]), size=15, fill=color, bold=True, anchor="start")
            c.text(end_x, end_y + 18, pin["name"], size=17, fill=INK)
        else:
            c.text(x + 14, y + 10, str(pin["number"]), size=15, fill=color, bold=True, anchor="start")
            c.text(end_x, end_y - 18, pin["name"], size=17, fill=INK)

    legend_y = 925
    for x, color, label in ((390, GPIO, "bidirectional GPIO / SWDIO"), (700, INPUT, "input"), (885, POWER, "power input/output")):
        c.line(x, legend_y, x + 36, legend_y, stroke=color, sw=5)
        c.text(x + 48, legend_y, label, size=16, fill=MUTED, anchor="start")
    return c.save("schematic_symbol")


def render_combined():
    top = Image.open(OUT / "footprint_top.png").convert("RGB")
    mech = Image.open(OUT / "mechanical_dimensions.png").convert("RGB")
    sym = Image.open(OUT / "schematic_symbol.png").convert("RGB")
    image = Image.new("RGB", (2400, 1900), color_rgba(BG)[:3])
    draw = ImageDraw.Draw(image)
    draw.text((90, 72), "PCA10059 KiCad part — visual verification sheet", font=load_font(40, True), fill=color_rgba(INK)[:3])
    draw.text((90, 126), "All views are generated from the delivered symbol, footprint, and pinout files.", font=load_font(22), fill=color_rgba(MUTED)[:3])
    top.thumbnail((2220, 1060))
    mech.thumbnail((1450, 820))
    sym.thumbnail((900, 820))
    image.paste(top, (90, 190))
    image.paste(mech, (90, 1130))
    image.paste(sym, (1490, 1130))
    image.save(OUT / "verification_sheet.png", quality=95)
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 2400 1900" width="2400" height="1900" role="img" aria-labelledby="title desc">
<title id="title">PCA10059 KiCad visual verification sheet</title>
<desc id="desc">Combined footprint, mechanical, and schematic symbol views generated from the delivered KiCad library.</desc>
<rect width="2400" height="1900" fill="{BG}"/>
<text x="90" y="88" font-family="Arial, Helvetica, sans-serif" font-size="40" font-weight="700" fill="{INK}">PCA10059 KiCad part — visual verification sheet</text>
<text x="90" y="138" font-family="Arial, Helvetica, sans-serif" font-size="22" fill="{MUTED}">All views are generated from the delivered symbol, footprint, and pinout files.</text>
<image href="footprint_top.svg" x="90" y="190" width="2220" height="1172" preserveAspectRatio="xMidYMid meet"/>
<image href="mechanical_dimensions.svg" x="90" y="1130" width="1380" height="767" preserveAspectRatio="xMidYMid meet"/>
<image href="schematic_symbol.svg" x="1490" y="1130" width="820" height="767" preserveAspectRatio="xMidYMid meet"/>
</svg>'''
    (OUT / "verification_sheet.svg").write_text(svg, encoding="utf-8")


def main():
    pads, fab_lines, symbol_pins, pinout = parse_library()
    render_footprint(pads, fab_lines, pinout)
    render_mechanical(pads, fab_lines, pinout)
    render_symbol(symbol_pins)
    render_combined()
    print("Rendered:")
    for path in sorted(OUT.glob("*")):
        print(f"  {path.name} ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
