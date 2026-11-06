"""Audit integer translation between two small grayscale images."""
import argparse
import cmath
from functools import lru_cache
import json
import math
from pathlib import Path
import sys


def read_pgm(path):
    """Read one bounded, plain P2 image with maxval 255."""
    if path.stat().st_size > 65536:
        raise ValueError("PGM exceeds this lab's 64 KiB limit")
    words = [w for line in path.read_text(encoding="ascii").splitlines()
             for w in line.partition("#")[0].split()]
    if len(words) < 4 or words[0] != "P2":
        raise ValueError("expected a plain P2 PGM image")
    w, h, maximum = map(int, words[1:4])
    pixels = list(map(int, words[4:]))
    if not (4 <= w <= 64 and 4 <= h <= 64 and maximum == 255):
        raise ValueError("expected dimensions 4 to 64 and maxval 255")
    if len(pixels) != w * h or any(not 0 <= p <= 255 for p in pixels):
        raise ValueError("PGM raster has wrong length or invalid samples")
    return [pixels[i:i+w] for i in range(0, len(pixels), w)]


@lru_cache(maxsize=16)
def weights(n, inverse):
    sign = 1 if inverse else -1
    return tuple(tuple(cmath.exp(sign * 2j * math.pi * k * i / n)
                       for i in range(n)) for k in range(n))


def transform_rows(matrix, inverse):
    n = len(matrix[0])
    scale = n if inverse else 1
    table = weights(n, inverse)
    return [[sum(sample * basis for sample, basis in zip(row, vector)) / scale
             for vector in table] for row in matrix]


def dft2(matrix, inverse=False):
    horizontal = transform_rows(matrix, inverse)
    return list(zip(*transform_rows(list(zip(*horizontal)), inverse)))


def centered(image):
    n = len(image) * len(image[0])
    mean = sum(map(sum, image)) / n
    return [[p - mean for p in row] for row in image]


def signed(bin_index, length):
    return (bin_index + length // 2) % length - length // 2


def estimate(reference, moving):
    """Return correction (x, y), peak height and gap to second peak."""
    a, b = dft2(centered(reference)), dft2(centered(moving))
    products = [[u * v.conjugate() for u, v in zip(ar, br)]
                for ar, br in zip(a, b)]
    top = max(abs(p) for row in products for p in row)
    if top == 0:
        return None
    normalized = [[p / abs(p) if abs(p) > top * 1e-12 else 0j
                   for p in row] for row in products]
    surface = dft2(normalized, inverse=True)
    ranked = sorted(((v.real, y, x) for y, row in enumerate(surface)
                     for x, v in enumerate(row)), reverse=True)
    peak, y, x = ranked[0]
    return signed(x, len(reference[0])), signed(y, len(reference)), peak, peak - ranked[1][0]


def valid_point(value, width, height):
    if not (isinstance(value, list) and len(value) == 2
            and all(type(v) is int for v in value)
            and 0 <= value[0] < width and 0 <= value[1] < height):
        raise ValueError("each checkpoint must be an in-frame [x, y] integer pair")
    return value


def audit(reference, moving, checkpoints, fit_height, max_shift, max_error):
    w, h = len(reference[0]), len(reference)
    if len(moving) != h or len(moving[0]) != w:
        raise ValueError("reference and moving images must have equal dimensions")
    if type(fit_height) is not int or not 4 <= fit_height < h:
        raise ValueError("fit_height_px must leave lower rows for checkpoints")
    if type(max_shift) is not int or not 1 <= max_shift < min(w, fit_height) / 2:
        raise ValueError("max_shift_px must be positive and below half the shorter fit side")
    if type(max_error) not in (int, float) or not 0 <= max_error <= min(w, h):
        raise ValueError("invalid max_checkpoint_error_px")
    if not isinstance(checkpoints, list) or len(checkpoints) < 2:
        raise ValueError("supply at least two separate checkpoint pairs")
    if any(not isinstance(pair, dict) for pair in checkpoints):
        raise ValueError("each checkpoint must contain reference and moving coordinates")
    pairs = [(valid_point(pair.get("reference"), w, h), valid_point(pair.get("moving"), w, h))
             for pair in checkpoints]
    if len({tuple(a) for a, _ in pairs}) != len(pairs) or len({tuple(b) for _, b in pairs}) != len(pairs):
        raise ValueError("checkpoint locations must be distinct in each image")
    if any(a[1] < fit_height or b[1] < fit_height for a, b in pairs):
        raise ValueError("checkpoints must lie below the fitting rows in both images")
    result = estimate(reference[:fit_height], moving[:fit_height])
    if result is None:
        return {"status": "no_shared_texture", "correction_xy_px": None}
    x, y, peak, gap = result
    if gap < 0.05:
        return {"status": "ambiguous_peak", "correction_xy_px": None,
                "peak": round(peak, 6), "peak_gap": round(gap, 6)}
    errors = [math.hypot(b[0] + x - a[0], b[1] + y - a[1]) for a, b in pairs]
    overlap = (w - abs(x)) * (h - abs(y)) / (w * h)
    if max(abs(x), abs(y)) > max_shift:
        status = "outside_shift_bound"
    elif max(errors) > max_error:
        status = "checkpoint_mismatch"
    else:
        status = "accepted"
    return {"status": status, "correction_xy_px": [x, y],
            "overlap_fraction": round(overlap, 6), "peak": round(peak, 6),
            "peak_gap": round(gap, 6), "checkpoint_errors_px": [round(e, 6) for e in errors]}


def aligned_image(moving, correction):
    """Render to the original frame size, with black outside source bounds."""
    dx, dy = correction
    width, height = len(moving[0]), len(moving)
    return [[moving[y-dy][x-dx] if 0 <= x-dx < width and 0 <= y-dy < height else 0
             for x in range(width)] for y in range(height)]


def write_pgm(path, image):
    with path.open("x", encoding="ascii") as stream:
        stream.write(f"P2\n{len(image[0])} {len(image)}\n255\n")
        for row in image:
            stream.write(" ".join(map(str, row)) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", type=Path)
    parser.add_argument("--aligned-out", type=Path, help="write an accepted alignment to a new P2 PGM")
    args = parser.parse_args()
    try:
        case = json.loads(args.case.read_text(encoding="utf-8"))
        if not isinstance(case, dict):
            raise ValueError("case must be a JSON object")
        paths = [args.case.parent / case[name] for name in ("reference", "moving")]
        reference, moving = map(read_pgm, paths)
        result = audit(reference, moving, case["checkpoints"], case["fit_height_px"],
                       case["max_shift_px"], case["max_checkpoint_error_px"])
        if args.aligned_out is not None and result["status"] == "accepted":
            write_pgm(args.aligned_out, aligned_image(moving, result["correction_xy_px"]))
    except (OSError, UnicodeError, ValueError, TypeError, KeyError) as exc:
        print(f"Input error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "accepted" else 1


if __name__ == "__main__":
    raise SystemExit(main())
