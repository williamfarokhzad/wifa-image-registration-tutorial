"""Render the two article diagrams from the checked-in fixture data (Pillow)."""
import json
from pathlib import Path
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from register import audit, read_pgm

BG, INK, MUTED, TEAL, GOLD = "#f0f6f5", "#102c3d", "#364f5b", "#006d68", "#ae431a"
FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")


def font(size, bold=False):
    path = FONT_DIR / ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf")
    if path.exists():
        return ImageFont.truetype(str(path), size)
    return ImageFont.load_default(size=size)


def label(draw, xy, text, size=24, color=INK, bold=False):
    draw.text(xy, text, fill=color, font=font(size, bold))


def frame(draw, image, points, x0, y0, fit):
    size = 8
    for y, row in enumerate(image):
        for x, v in enumerate(row):
            draw.rectangle((x0+x*size, y0+y*size, x0+(x+1)*size-1, y0+(y+1)*size-1), fill=(v,v,v))
    x1 = x0 + len(image[0])*size
    y1 = y0 + fit*size
    draw.line((x0, y1, x1, y1), fill="#30e4d4", width=3)
    for index, (x, y) in enumerate(points, 1):
        px, py = x0+x*size+4, y0+y*size+4
        draw.ellipse((px-9,py-9,px+9,py+9), outline="#ffb174", width=3)
        label(draw, (px+14,py-12), str(index), 20, "#ffb174", True)


def read_case(name):
    folder = HERE.parent / "examples"
    case = json.loads((folder / (name + ".json")).read_text())
    a = read_pgm(folder / case["reference"])
    b = read_pgm(folder / case["moving"])
    return case, a, b


def draw():
    case, a, b = read_case("shifted")
    im = Image.new("RGB", (820, 465), BG)
    d = ImageDraw.Draw(im)
    label(d, (32, 22), "Fit above the line. Check below it.", 36, bold=True)
    label(d, (85, 91), "Reference", 26, bold=True)
    label(d, (479, 91), "Moving image", 26, bold=True)
    for x, img, key in [(85, a, "reference"), (479, b, "moving")]:
        frame(d, img, [p[key] for p in case["checkpoints"]], x, 126, case["fit_height_px"])
    label(d, (33, 394), "Cyan: fit boundary   Orange: checkpoint pixels", 24, MUTED)
    label(d, (33, 429), "Correction applied to moving coordinates: (−5, +3) px", 23, TEAL, True)
    im.save(HERE / "image-registration-fit-and-check.webp", quality=84, method=6)

    im = Image.new("RGB", (820, 432), BG)
    d = ImageDraw.Draw(im)
    label(d, (31, 24), "A sharp peak can still fail the check", 33, bold=True)
    for x, name, heading in [(31, "shifted", "Whole image shift"),
                             (422, "local-motion", "One mark also moves")]:
        c, a, b = read_case(name)
        result = audit(a, b, c["checkpoints"], c["fit_height_px"],
                       c["max_shift_px"], c["max_checkpoint_error_px"])
        color = TEAL if result["status"] == "accepted" else GOLD
        d.rounded_rectangle((x,88,x+367,358), radius=18, fill="#ffffff", outline="#b6cecc", width=2)
        label(d,(x+18,108), heading, 25, bold=True)
        label(d,(x+18,159),"Peak gap",22,MUTED)
        label(d,(x+212,154),f"{result['peak_gap']:.2f}",27,bold=True)
        label(d,(x+18,209),"Check 1 error",22,MUTED)
        label(d,(x+212,204),f"{result['checkpoint_errors_px'][0]:.0f} px",27,color,True)
        label(d,(x+18,254),"Check 2 error",22,MUTED)
        label(d,(x+212,249),f"{result['checkpoint_errors_px'][1]:.0f} px",27,bold=True)
        label(d,(x+18,305),"Accepted" if name == "shifted" else "Rejected",25,color,True)
    label(d,(31,379),"Example tolerance: each checkpoint must be within 1 px.",23,MUTED)
    im.save(HERE / "image-registration-peak-and-residual.webp", quality=84, method=6)


if __name__ == "__main__":
    draw()
