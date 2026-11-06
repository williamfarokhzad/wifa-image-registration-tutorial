"""Rebuild the original synthetic 32 by 32 P2 fixtures."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
N = 32


def save(name, grid):
    raster = "\n".join(" ".join(map(str, row)) for row in grid)
    (HERE / (name + ".pgm")).write_text(f"P2\n{N} {N}\n255\n{raster}\n", encoding="ascii")


def manifest(name, ref, moving, points, limit=8):
    case = {"reference": ref + ".pgm", "moving": moving + ".pgm",
            "fit_height_px": 22, "max_shift_px": limit, "max_checkpoint_error_px": 1,
            "checkpoints": [{"reference": a, "moving": b} for a, b in points]}
    (HERE / (name + ".json")).write_text(json.dumps(case, indent=2) + "\n", encoding="utf-8")


def generate():
    reference = [[25] * N for _ in range(N)]
    # An asymmetric fixture, plus two small marks that can be located independently.
    for x0, y0, w, h, value in [(8, 9, 11, 3, 215), (8, 9, 3, 11, 215),
                                 (14, 14, 6, 5, 148), (20, 10, 3, 3, 99),
                                 (15, 27, 1, 1, 251), (22, 28, 1, 1, 181)]:
        for y in range(y0, y0+h):
            for x in range(x0, x0+w):
                reference[y][x] = value
    # Physical pixel displacement (+5,-3); no wrap; new background exposed at borders.
    moving = [[(reference[y+3][x-5] if y+3 < N and x >= 5 else 25)
               for x in range(N)] for y in range(N)]
    save("reference", reference)
    save("moving", moving)
    save("moving-offset", [[p + 3 for p in row] for row in moving])
    moved = [row[:] for row in moving]
    moved[24][20], moved[24][23] = 25, 251  # first mark moves 3 more pixels right
    save("moving-local", moved)
    points = [([15, 27], [20, 24]), ([22, 28], [27, 25])]
    manifest("shifted", "reference", "moving", points)
    manifest("lighting-offset", "reference", "moving-offset", points)
    manifest("local-motion", "reference", "moving-local", [([15, 27], [23, 24]), points[1]])
    manifest("out-of-range", "reference", "moving", points, limit=4)
    stripe = [[220 if x % 8 < 3 else 40 for x in range(N)] for _ in range(N)]
    shifted = [[row[(x-3) % N] for x in range(N)] for row in stripe]
    save("stripes", stripe)
    save("stripes-shifted", shifted)
    manifest("repeated", "stripes", "stripes-shifted", [([8, 23], [11, 23]), ([16, 24], [19, 24])])


if __name__ == "__main__":
    generate()
