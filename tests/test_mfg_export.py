"""
test_mfg_export.py - Tests for manufacturing features per BUT guidelines (Manufacturing of antennas - instructions.pdf).
Verifies corner alignment marks calculation, 'PM.' identifier symbol, mirroring, and KiCad 10 board generation.
"""

import os
import sys
import tempfile
import unittest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(TESTS_DIR, ".."))
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "scripts")

for p in (PROJECT_ROOT, SRC_DIR, SCRIPTS_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

from antenna_geometry import (
    compute_mfg_corner_marks,
    compute_mfg_ident_polygons,
    get_model4_kicad_geometry,
)
from kicad_generator import generate_kicad_pcb


class TestManufacturingExport(unittest.TestCase):
    def setUp(self):
        self.params = {
            'patch_L': 29.81,
            'patch_W': 29.81,
            'sub_h': 1.52,
            'eps_r': 4.3,
            'design_freq_ghz': 2.3325,
            'port_impedance': 50.0,
            'feed_inset_b': 2.5,
            'feed_inset_l': 2.5,
            'feed_inset_gap_b': 0.5,
            'feed_inset_gap_l': 0.5,
            'trans_w': 0.42,
            'feed_bend_radius': 3.0,
            'feed_t_fillet_r': 0.8,
            'feed_50_len': 9.0,
            'feed_end_straight': 4.6,
            'sub_margin': 8.0,
            'tight_pcb': True,
        }

    def test_corner_marks_count_and_positions(self):
        """Verify that compute_mfg_corner_marks generates exactly 8 rectangles adjacent to the corners."""
        xmin, xmax = -25.0, 35.0
        ymin, ymax = -20.0, 30.0
        lm = 8.0
        wm = 2.0
        marks = compute_mfg_corner_marks(xmin, xmax, ymin, ymax, mark_len=lm, mark_w=wm)
        self.assertEqual(len(marks), 8, "Exactly 8 corner marks must be created (2 for each of the 4 corners).")

        for poly in marks:
            self.assertEqual(len(poly), 4, "Each mark must be a quadrilateral/rectangle.")
            xs = [p[0] for p in poly]
            ys = [p[1] for p in poly]
            w = max(xs) - min(xs)
            h = max(ys) - min(ys)
            # Each mark has dimensions lm x wm or wm x lm
            self.assertTrue(
                (abs(w - lm) < 1e-6 and abs(h - wm) < 1e-6) or (abs(w - wm) < 1e-6 and abs(h - lm) < 1e-6),
                f"Mark dimensions ({w} x {h}) must match mark_len ({lm}) and mark_w ({wm}).",
            )

    def test_ident_polygons_generation_and_mirror(self):
        """Verify generation of the 'PM.' identifier symbol in normal and mirrored modes."""
        polys_normal = compute_mfg_ident_polygons(text="PM.", center_x=0.0, base_y=35.0, height=5.0, mirror=False)
        self.assertGreater(len(polys_normal), 0, "Identifier symbol must contain polygons.")

        polys_mirrored = compute_mfg_ident_polygons(text="PM.", center_x=0.0, base_y=35.0, height=5.0, mirror=True)
        self.assertEqual(len(polys_normal), len(polys_mirrored), "Polygon count in normal and mirrored modes must match.")

        # In normal mode, P is on the left (more negative X) and the dot is on the right (more positive X)
        xs_norm = [p[0] for poly in polys_normal for p in poly]
        # In mirrored mode, X is flipped (x -> -x)
        xs_mir = [p[0] for poly in polys_mirrored for p in poly]
        self.assertAlmostEqual(min(xs_norm), -max(xs_mir), places=4)
        self.assertAlmostEqual(max(xs_norm), -min(xs_mir), places=4)

    def test_kicad_geometry_data_with_mfg_vut(self):
        """Verify integration of manufacturing features into KiCadGeometryData."""
        geom_default = get_model4_kicad_geometry(self.params, mfg_vut=False)
        self.assertEqual(len(geom_default.mfg_corner_marks), 0)
        self.assertEqual(len(geom_default.mfg_ident_polygons), 0)
        self.assertFalse(geom_default.is_mirrored)

        geom_mfg = get_model4_kicad_geometry(self.params, mfg_vut=True, ident_symbol="PM.")
        self.assertEqual(len(geom_mfg.mfg_corner_marks), 8)
        self.assertGreater(len(geom_mfg.mfg_ident_polygons), 0)
        self.assertFalse(geom_mfg.is_mirrored)

        geom_mfg_mir = get_model4_kicad_geometry(self.params, mfg_vut=True, ident_symbol="PM.", mirror_x=True)
        self.assertEqual(len(geom_mfg_mir.mfg_corner_marks), 8)
        self.assertGreater(len(geom_mfg_mir.mfg_ident_polygons), 0)
        self.assertTrue(geom_mfg_mir.is_mirrored)

    def test_generate_kicad_pcb_mfg(self):
        """Verify that the generated .kicad_pcb file contains manufacturing zones and masks."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out_pcb = os.path.join(tmpdir, "test_antenna_mfg.kicad_pcb")
            res = generate_kicad_pcb(
                self.params,
                out_pcb,
                mfg_vut=True,
                ident_symbol="PM.",
                mirror_x=False,
            )
            self.assertTrue(os.path.exists(out_pcb))
            self.assertGreater(res['file_size_bytes'], 10000)

            with open(out_pcb, "r", encoding="utf-8") as f:
                content = f.read()

            self.assertIn('(generator "antenna_kicad_generator")', content)
            self.assertIn('(net "RF_IN")', content)
            self.assertIn('(net "GND")', content)
            self.assertIn('"Edge.Cuts"', content)
            self.assertIn('"F.Mask"', content)
            # Corner marks have priority 50..
            self.assertIn("(priority 50)", content)
            # Identifier symbol has priority 70..
            self.assertIn("(priority 70)", content)

    def test_generate_kicad_pcb_mfg_mirrored(self):
        """Verify generation of a mirrored board (mirror_x=True) including SMA connector rotation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out_pcb = os.path.join(tmpdir, "test_antenna_mfg_mirrored.kicad_pcb")
            res = generate_kicad_pcb(
                self.params,
                out_pcb,
                mfg_vut=True,
                ident_symbol="PM.",
                mirror_x=True,
            )
            self.assertTrue(os.path.exists(out_pcb))

            with open(out_pcb, "r", encoding="utf-8") as f:
                content = f.read()

            # Mirrored SMA connector has 180-degree rotation
            self.assertIn('180)\n    (attr smd)', content)


if __name__ == "__main__":
    unittest.main()
