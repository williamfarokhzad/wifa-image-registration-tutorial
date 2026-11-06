import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from register import audit, estimate, read_pgm

ROOT = Path(__file__).resolve().parents[1]


class AlgorithmTests(unittest.TestCase):
    def test_asymmetric_rectangular_impulse_correction(self):
        # A hand constructed 9 x 7 pair; moving spot was shifted left 3, down 2.
        a, b = [[0] * 9 for _ in range(7)], [[0] * 9 for _ in range(7)]
        a[1][4], b[3][1] = 180, 180
        x, y, peak, gap = estimate(a, b)
        self.assertEqual((x, y), (3, -2))
        self.assertAlmostEqual(peak, 62 / 63)
        self.assertAlmostEqual(gap, 1)

    def test_no_texture_when_one_frame_is_flat(self):
        flat = [[12] * 8 for _ in range(8)]
        texture = [[x*x+y for x in range(8)] for y in range(8)]
        self.assertIsNone(estimate(flat, texture))

    def test_independent_marks_cannot_influence_the_fit(self):
        root = ROOT / "examples"
        a, b, c = [read_pgm(root / name) for name in
                   ("reference.pgm", "moving.pgm", "moving-local.pgm")]
        common = {"fit_height": 22, "max_shift": 8, "max_error": 1}
        points = [{"reference": [15, 27], "moving": [20, 24]},
                  {"reference": [22, 28], "moving": [27, 25]}]
        original = audit(a, b, points, **common)
        altered = audit(a, c, [dict(points[0], moving=[23, 24]), points[1]], **common)
        for key in ("correction_xy_px", "overlap_fraction", "peak", "peak_gap"):
            self.assertEqual(original[key], altered[key])
        self.assertEqual(original["overlap_fraction"], round(27 * 29 / 1024, 6))
        self.assertEqual(altered["checkpoint_errors_px"], [3.0, 0.0])
        self.assertEqual(altered["status"], "checkpoint_mismatch")

    def test_checkpoint_inside_fit_is_invalid(self):
        grid = [[0] * 8 for _ in range(8)]
        points = [{"reference": [1, 1], "moving": [1, 1]},
                  {"reference": [2, 7], "moving": [2, 7]}]
        with self.assertRaisesRegex(ValueError, "below the fitting rows"):
            audit(grid, grid, points, 5, 1, 1)

    def test_periodic_stripes_have_no_unique_solution(self):
        a = [[100 if x % 4 == 0 else 0 for x in range(12)] for _ in range(8)]
        b = [[r[(x-1) % 12] for x in range(12)] for r in a]
        points = [{"reference": [4, 6], "moving": [5, 6]},
                  {"reference": [8, 7], "moving": [9, 7]}]
        result = audit(a, b, points, 6, 2, 1)
        self.assertEqual(result["status"], "ambiguous_peak")
        self.assertIsNone(result["correction_xy_px"])
        self.assertEqual(result["peak_gap"], 0)


class FileAndCommandTests(unittest.TestCase):
    def test_rejects_short_raster_and_accepts_header_comment(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "frame.pgm"
            path.write_text("P2\n# test\n4 4\n255\n" + "0 " * 15, encoding="ascii")
            with self.assertRaisesRegex(ValueError, "wrong length"):
                read_pgm(path)
            path.write_text(path.read_text() + "255", encoding="ascii")
            self.assertEqual(read_pgm(path)[3][3], 255)

    def test_cli_status_and_exit_for_all_fixtures(self):
        cases = {"shifted": (0, "accepted"), "lighting-offset": (0, "accepted"),
                 "local-motion": (1, "checkpoint_mismatch"),
                 "out-of-range": (1, "outside_shift_bound"),
                 "repeated": (1, "ambiguous_peak")}
        for name, (code, status) in cases.items():
            with self.subTest(name=name):
                run = subprocess.run([sys.executable, "register.py", f"examples/{name}.json"],
                                     cwd=ROOT, capture_output=True, text=True)
                self.assertEqual(run.returncode, code, run.stderr)
                self.assertEqual(json.loads(run.stdout)["status"], status)
                self.assertEqual(run.stderr, "")

    def test_export_uses_inverse_sampling_without_wrap_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "aligned.pgm"
            cmd = [sys.executable, "register.py", "examples/shifted.json", "--aligned-out", str(target)]
            first = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            image = read_pgm(target)
            self.assertEqual(image[27][15], 251)
            self.assertEqual(image[28][22], 181)
            self.assertEqual(image[0], [0] * 32)
            self.assertEqual(image[27][-5:], [0] * 5)
            before = target.read_bytes()
            second = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(second.returncode, 2)
            self.assertEqual(target.read_bytes(), before)
            rejected = Path(folder) / "rejected.pgm"
            cmd[2], cmd[-1] = "examples/local-motion.json", str(rejected)
            self.assertEqual(subprocess.run(cmd, cwd=ROOT, capture_output=True).returncode, 1)
            self.assertFalse(rejected.exists())

    def test_invalid_input_does_not_emit_an_estimate(self):
        run = subprocess.run([sys.executable, "register.py", "missing.json"],
                             cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(run.returncode, 2)
        self.assertIn("Input error:", run.stderr)
        self.assertEqual(run.stdout, "")


if __name__ == "__main__":
    unittest.main()
