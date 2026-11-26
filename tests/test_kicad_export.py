"""
test_kicad_export.py - Comprehensive unit tests for Pure-Python KiCad generator for Model 4.
Tests:
  1. antenna_geometry.py:
     - Analytical curved path length calculation (calc_curved_path_length).
     - 2D polygon outline generation for curved traces (compute_curved_ribbon_outline).
     - Filleted T-junction construction (compute_t_junction_polygon).
     - Model 4 routing analysis and Delta L phase balance (compute_model4_routing).
     - CAD-to-KiCad coordinate transformation with strict LHCP polarization preservation.
     - 50 um overlaps to eliminate DRC micro-gaps.
     - SMA G-S-G launch interface (Cinch Johnson 142-0701-801, 6 vias).
  2. kicad_generator.py:
     - KiCad 10 (version 20260206) manufacturing PCB (.kicad_pcb) generation.
     - Verification of named nets ("GND", "RF_IN") and canonical KiCad 10 layers.
     - F.Cu zones, solid B.Cu ground plane, Edge.Cuts outline, F.Mask openings, 6 GND vias.
     - Library footprint (.kicad_mod) generation with anchor point (0, 0) at patch center.
     - Custom SMD pad 1 with full RF geometry and SMD pads 2, 3 for SMA GND.
  3. scripts/export_kicad.py:
     - CLI interface and options (--pcb, --footprint, --all, parameter overrides).
"""

import math
import os
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

# Add project root, src, and scripts directories to sys.path
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(TESTS_DIR, ".."))
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "scripts")

for p in (PROJECT_ROOT, SRC_DIR, SCRIPTS_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

from antenna_geometry import (
    OVERLAP_DELTA,
    SMA_GAP,
    SMA_PAD_LEN,
    SMA_PAD_W,
    calc_curved_path_length,
    calc_microstrip_eps_eff,
    calc_microstrip_z0,
    calc_quarter_wave_length,
    compute_curved_ribbon_outline,
    compute_model4_routing,
    compute_patch_with_insets_polygon,
    compute_t_junction_polygon,
    get_model4_kicad_geometry,
    synth_microstrip_w,
    transform_cad_to_kicad,
    transform_poly_to_kicad,
)
from export_kicad import load_model4_params_from_env
from kicad_generator import (
    generate_kicad_footprint,
    generate_kicad_pcb,
)


class TestAntennaGeometry(unittest.TestCase):
    """Tests for analytical calculations and geometry in antenna_geometry.py."""

    def test_rf_formulas_pure_python(self):
        """Verify analytical formulas for microstrip line and quarter-wave length."""
        h = 1.52
        eps_r = 4.3
        # 50 Ohm line synthesis
        w_50 = synth_microstrip_w(50.0, h, eps_r)
        self.assertAlmostEqual(w_50, 2.98, delta=0.05)

        # Reverse impedance calculation check
        z0_calc = calc_microstrip_z0(w_50, h, eps_r)
        self.assertAlmostEqual(z0_calc, 50.0, delta=0.01)

        # Effective permittivity and quarter-wave length
        eps_eff = calc_microstrip_eps_eff(w_50, h, eps_r)
        self.assertTrue(1.0 < eps_eff < eps_r)
        lambda_g_4 = calc_quarter_wave_length(2.3325, eps_eff)
        self.assertTrue(15.0 < lambda_g_4 < 25.0)

    def test_curved_path_length(self):
        """Verify length calculation of an orthogonal route with 90° circular bends."""
        # 90° corner: straight segment 1 (10 - R) + straight segment 2 (10 - R) + quarter-circle (pi * R / 2)
        r = 3.0
        pts = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)]
        expected = (10.0 - r) + (10.0 - r) + 0.5 * math.pi * r
        calc_len = calc_curved_path_length(pts, r)
        self.assertAlmostEqual(calc_len, expected, places=7)

        # Straight line without corners
        pts_straight = [(0.0, 0.0), (15.0, 0.0)]
        self.assertAlmostEqual(calc_curved_path_length(pts_straight, r), 15.0, places=7)

        # Segment too short relative to bend radius raises ValueError
        pts_short = [(0.0, 0.0), (2.0, 0.0), (2.0, 10.0)]
        with self.assertRaises(ValueError):
            calc_curved_path_length(pts_short, 3.0)

    def test_curved_ribbon_outline(self):
        """Verify 2D polygon generation for a trace with circular bends."""
        pts = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)]
        width = 0.694
        outline = compute_curved_ribbon_outline(pts, width, bend_radius=3.0, arc_samples=16)

        self.assertGreater(len(outline), 20)
        # First point lies perpendicular to start at distance width/2
        self.assertAlmostEqual(outline[0][0], 0.0, places=4)
        self.assertAlmostEqual(abs(outline[0][1]), width / 2.0, places=4)
        # Last point lies perpendicular to start on the opposite side
        self.assertAlmostEqual(outline[-1][0], 0.0, places=4)
        self.assertAlmostEqual(abs(outline[-1][1]), width / 2.0, places=4)

    def test_t_junction_polygon(self):
        """Verify T-junction geometry with sharp corners and with circular fillets."""
        # Without fillets
        poly_sharp = compute_t_junction_polygon(
            x_port=-45.0, x_T=-38.0, y_T=-28.0, w_50=2.98, w_feed=0.694, t_fillet_r=0.0
        )
        self.assertEqual(len(poly_sharp), 8)

        # With fillet r = 0.8 mm
        poly_fillet = compute_t_junction_polygon(
            x_port=-45.0, x_T=-38.0, y_T=-28.0, w_50=2.98, w_feed=0.694, t_fillet_r=0.8, arc_samples=8
        )
        self.assertGreater(len(poly_fillet), 12)
        # Check that polygon starts and ends at x_port
        self.assertAlmostEqual(poly_fillet[0][0], -45.0, places=4)
        self.assertAlmostEqual(poly_fillet[-1][0], -45.0, places=4)

    def test_patch_with_insets_polygon(self):
        """Verify closed outline of radiating patch with inset notches."""
        poly = compute_patch_with_insets_polygon(
            W=28.8, L=28.8, inset_b=2.5, inset_l=2.5, w_T_b=0.42, w_T_l=0.42, gap_b=0.5, gap_l=0.5
        )
        self.assertGreater(len(poly), 8)
        # Patch extends to W/2 = 14.4 and L/2 = 14.4
        xs = [p[0] for p in poly]
        ys = [p[1] for p in poly]
        self.assertAlmostEqual(max(xs), 14.4, places=4)
        self.assertAlmostEqual(min(xs), -14.4, places=4)
        self.assertAlmostEqual(max(ys), 14.4, places=4)
        self.assertAlmostEqual(min(ys), -14.4, places=4)

    def test_model4_routing_and_phase_balance(self):
        """Verify that path difference L_100_b - L_100_l exactly matches Delta L."""
        params = {
            'patch_L': 28.8,
            'patch_W': 28.8,
            'sub_h': 1.52,
            'eps_r': 4.3,
            'port_impedance': 50.0,
            'feed_bend_radius': 3.0,
            'feed_t_fillet_r': 0.8,
        }
        info = compute_model4_routing(params)

        diff = info['L_100_b'] - info['L_100_l']
        self.assertAlmostEqual(diff, info['feed_delta_l'], places=6)
        self.assertAlmostEqual(info['x_port'], -info['W_sub'] / 2.0, places=6)
        self.assertAlmostEqual(info['y_port'], info['y_T'], places=6)
        self.assertGreaterEqual(info['s_end_l'], 0.5 - 1e-6)
        self.assertGreaterEqual(info['s_end_b'], info['end_straight'] - 1e-6)
        self.assertGreaterEqual(info['s_T_up'], 0.5 - 1e-6)
        self.assertGreaterEqual(info['s_T_down'], 0.5 - 1e-6)

    def test_kicad_coordinate_transformation_and_lhcp_preservation(self):
        """
        Verify that the transformation x_kicad = x0 + x_cad, y_kicad = y0 - y_cad
        strictly preserves spatial orientation and LHCP polarization.
        """
        params = {'patch_L': 28.8, 'sub_h': 1.52, 'eps_r': 4.3}
        geom = get_model4_kicad_geometry(params, is_footprint=False)

        # 1. Board origin and positive coordinates
        x_min, y_min, x_max, y_max = geom.edge_cuts_rect
        self.assertGreater(x_min, 0.0)
        self.assertGreater(y_min, 0.0)
        self.assertAlmostEqual(x_max - x_min, geom.W_sub, places=4)
        self.assertAlmostEqual(y_max - y_min, geom.L_sub, places=4)

        # 2. In CAD, the bottom branch (Ey, -90 deg delay) lies at negative Y.
        # In KiCad (where +Y points downward), the bottom branch must lie at a LARGER y_kicad than board center!
        info = geom.routing_info
        cad_y_T = info['y_T']  # negative number (e.g. -28.4 mm)
        self.assertLess(cad_y_T, 0.0)

        # Y coordinate in KiCad:
        kicad_y_T = geom.origin_y - cad_y_T
        self.assertGreater(kicad_y_T, geom.origin_y)

        # Left branch (Ex, 0 deg) lies at negative X in CAD -> smaller x_kicad than center
        cad_x_T = info['x_T']
        self.assertLess(cad_x_T, 0.0)
        kicad_x_T = geom.origin_x + cad_x_T
        self.assertLess(kicad_x_T, geom.origin_x)

        # 3. SMA interface check: 6 vias
        self.assertEqual(len(geom.vias), 6)
        for v in geom.vias:
            self.assertEqual(v['drill'], 0.30)
            self.assertEqual(v['size'], 0.60)
            self.assertEqual(v['net'], 1)
            self.assertEqual(v['net_name'], "GND")

    def test_solder_mask_clearance_and_bottom_opening(self):
        """Verify solder mask clearance and B.Mask opening."""
        params = {
            'patch_L': 28.8,
            'patch_W': 28.8,
            'sub_h': 1.52,
            'eps_r': 4.3,
            'mask_clearance': 0.30,
        }
        geom = get_model4_kicad_geometry(params, is_footprint=False)

        # 1. Mask opening polygon counts
        # F.Mask has 8 polygons (SMA GND top, SMA GND bot, patch, trans_b, trans_l, arm_l, arm_b, t_junc)
        self.assertEqual(len(geom.mask_openings), 8)
        # B.Mask has 1 polygon (SMA launch)
        self.assertEqual(len(geom.mask_openings_bottom), 1)

        # 2. Verify radiator mask dimensions (expanded by mask_clearance on each side)
        patch_mask = geom.mask_openings[2]
        xs = [p[0] for p in patch_mask]
        ys = [p[1] for p in patch_mask]
        patch_w_mask = max(xs) - min(xs)
        patch_l_mask = max(ys) - min(ys)
        self.assertAlmostEqual(patch_w_mask, 28.8 + 2 * 0.30, places=4)
        self.assertAlmostEqual(patch_l_mask, 28.8 + 2 * 0.30, places=4)

        # 3. Verify bottom transformer in mask (expanded in width by 2 * mask_clearance)
        trans_b_mask = geom.mask_openings[3]
        tb_xs = [p[0] for p in trans_b_mask]
        w_tb_mask = max(tb_xs) - min(tb_xs)
        info = geom.routing_info
        self.assertAlmostEqual(w_tb_mask, info['w_T_b'] + 2 * 0.30, places=4)

        # 4. Verify left transformer in mask (expanded in width by 2 * mask_clearance along Y)
        trans_l_mask = geom.mask_openings[4]
        tl_ys = [p[1] for p in trans_l_mask]
        w_tl_mask = max(tl_ys) - min(tl_ys)
        self.assertAlmostEqual(w_tl_mask, info['w_T_l'] + 2 * 0.30, places=4)

        # 4b. Verify solder mask dam between RF_IN and SMA GND on F.Mask
        sma_top_mask_ys = [p[1] for p in geom.mask_openings[0]]
        sma_bot_mask_ys = [p[1] for p in geom.mask_openings[1]]
        y_T_kicad = geom.origin_y - info['y_T']
        rf_mask_half = info['w_50'] / 2.0 + 0.30
        dam_top = (y_T_kicad - rf_mask_half) - max(sma_top_mask_ys)
        dam_bot = min(sma_bot_mask_ys) - (y_T_kicad + rf_mask_half)
        self.assertGreaterEqual(dam_top, 0.15 - 1e-4)
        self.assertGreaterEqual(dam_bot, 0.15 - 1e-4)

        # 5. Verify B.Mask opening (SMA launch 4.0 mm x 8.0 mm at board edge)
        b_mask_poly = geom.mask_openings_bottom[0]
        bm_xs = [p[0] for p in b_mask_poly]
        bm_ys = [p[1] for p in b_mask_poly]
        self.assertAlmostEqual(max(bm_xs) - min(bm_xs), 4.0, places=4)
        self.assertAlmostEqual(max(bm_ys) - min(bm_ys), 8.0, places=4)
        # Starts exactly at the left board edge (x_min of Edge.Cuts)
        x_min, _, _, _ = geom.edge_cuts_rect
        self.assertAlmostEqual(min(bm_xs), x_min, places=4)

    def test_tight_pcb_bounds_and_cropping(self):
        """Verify compact board cropping (tight_pcb=True) and full symmetric mode (tight_pcb=False)."""
        params_sdars = {
            'patch_L': 29.95,
            'patch_W': 29.95,
            'sub_h': 1.52,
            'eps_r': 4.3,
            'design_freq_ghz': 2.3325,
            'port_impedance': 50.0,
        }

        # 1. Compact crop (tight_pcb=True, default)
        geom_tight = get_model4_kicad_geometry(params_sdars, tight_pcb=True)
        info = geom_tight.routing_info

        self.assertTrue(geom_tight.tight_pcb)
        # Effective dimensions are significantly smaller than full symmetric substrate (~40% area savings)
        self.assertLess(geom_tight.W_sub, info['W_sub'])
        self.assertLess(geom_tight.L_sub, info['L_sub'])

        # Check compact dimensions for ~30 mm patch: W_sub ~ 73.4 mm
        self.assertAlmostEqual(geom_tight.W_sub, 73.40, delta=0.5)
        self.assertTrue(67.0 <= geom_tight.L_sub <= 77.0)

        # Check exact relations per analytical formulas
        expected_w = info['cad_x_max'] - info['cad_x_min']
        expected_l = info['cad_y_max'] - info['cad_y_min']
        self.assertAlmostEqual(geom_tight.W_sub, expected_w, places=4)
        self.assertAlmostEqual(geom_tight.L_sub, expected_l, places=4)

        self.assertAlmostEqual(info['cad_x_min'], info['x_port'], places=4)
        self.assertAlmostEqual(info['cad_x_max'], 29.95 / 2.0 + 10.0, places=4)
        self.assertAlmostEqual(info['cad_y_min'], info['y_bot'] - 5.0, places=4)
        self.assertAlmostEqual(info['cad_y_max'], 29.95 / 2.0 + 10.0, places=4)

        # Edge.Cuts rectangle in KiCad coordinates
        x_min, y_min, x_max, y_max = geom_tight.edge_cuts_rect
        self.assertAlmostEqual(x_max - x_min, geom_tight.W_sub, places=4)
        self.assertAlmostEqual(y_max - y_min, geom_tight.L_sub, places=4)
        self.assertAlmostEqual(x_min, 25.0, places=4)
        self.assertAlmostEqual(y_min, 25.0, places=4)

        # Check bottom GND polygon on B.Cu: covers Edge.Cuts exactly
        b_cu_poly = geom_tight.gnd_polygon_bottom
        b_xs = [p[0] for p in b_cu_poly]
        b_ys = [p[1] for p in b_cu_poly]
        self.assertAlmostEqual(min(b_xs), x_min, places=4)
        self.assertAlmostEqual(max(b_xs), x_max, places=4)
        self.assertAlmostEqual(min(b_ys), y_min, places=4)
        self.assertAlmostEqual(max(b_ys), y_max, places=4)

        # 2. Full symmetric mode (tight_pcb=False) for backwards compatibility
        geom_full = get_model4_kicad_geometry(params_sdars, tight_pcb=False)
        self.assertFalse(geom_full.tight_pcb)
        self.assertAlmostEqual(geom_full.W_sub, info['W_sub'], places=4)
        self.assertAlmostEqual(geom_full.L_sub, info['L_sub'], places=4)
        self.assertGreaterEqual(geom_full.W_sub, 95.0)
        self.assertGreaterEqual(geom_full.L_sub, 93.0)

        fx_min, fy_min, fx_max, fy_max = geom_full.edge_cuts_rect
        self.assertAlmostEqual(fx_max - fx_min, info['W_sub'], places=4)
        self.assertAlmostEqual(fy_max - fy_min, info['L_sub'], places=4)

        # 3. Optional margin configuration (margin_right, margin_top, margin_bottom)
        custom_params = dict(params_sdars)
        custom_params.update({
            'tight_pcb': True,
            'margin_right': 15.0,
            'margin_top': 12.0,
            'margin_bottom': 4.0,
        })
        geom_custom = get_model4_kicad_geometry(custom_params)
        c_info = geom_custom.routing_info
        self.assertAlmostEqual(c_info['cad_x_max'], 29.95 / 2.0 + 15.0, places=4)
        self.assertAlmostEqual(c_info['cad_y_max'], 29.95 / 2.0 + 12.0, places=4)
        self.assertAlmostEqual(c_info['cad_y_min'], c_info['y_bot'] - 4.0, places=4)

    def test_sma_gsg_backwards_compatibility_default_substrate(self):
        """Verify SMA G-S-G backwards compatibility for default substrate h=1.52 mm, eps_r=4.3."""
        params = {'patch_L': 28.8, 'patch_W': 28.8, 'sub_h': 1.52, 'eps_r': 4.3}
        geom = get_model4_kicad_geometry(params, is_footprint=False)
        info = geom.routing_info

        self.assertAlmostEqual(info['sma_gap'], SMA_GAP, places=6)
        self.assertAlmostEqual(info['sma_pad_len'], SMA_PAD_LEN, places=6)
        self.assertAlmostEqual(info['sma_pad_w'], SMA_PAD_W, places=6)
        self.assertAlmostEqual(info['sma_gnd_inner'], 2.19, delta=0.01)
        self.assertAlmostEqual(info['sma_gnd_outer'], 3.69, delta=0.01)
        self.assertAlmostEqual(info['sma_gnd_center_y'], 2.94, delta=0.01)
        self.assertAlmostEqual(info['sma_mask_len'], 4.0, places=6)
        self.assertAlmostEqual(info['sma_mask_half_h'], 4.0, places=6)
        self.assertEqual(geom.sma_pad_size, (3.50, 1.50))
        self.assertEqual(geom.sma_mask_size, (4.0, 8.0))

        # Vias at X offsets [1.0, 2.0, 3.0] from x_min and Y centered at y_T +- sma_gnd_center_y
        x_min, _, _, _ = geom.edge_cuts_rect
        y_T_kicad = geom.origin_y - info['y_T']
        via_x_offsets = sorted({round(v['x'] - x_min, 4) for v in geom.vias})
        self.assertEqual(via_x_offsets, [1.0, 2.0, 3.0])

        for v in geom.vias:
            self.assertAlmostEqual(abs(v['y'] - y_T_kicad), info['sma_gnd_center_y'], places=3)

    def test_sma_gsg_wide_50ohm_line_no_short_and_mask_coverage(self):
        """Verify SMA G-S-G for thicker board / lower eps_r (h=2.0, eps_r=3.5 -> w_50 > 4.4 mm)."""
        params = {
            'patch_L': 28.8,
            'patch_W': 28.8,
            'sub_h': 2.0,
            'eps_r': 3.5,
            'mask_clearance': 0.30,
        }
        geom = get_model4_kicad_geometry(params, is_footprint=False)
        info = geom.routing_info

        # Verify w_50 > 4.4 mm (previously would short at fixed +-2.19 mm boundary)
        self.assertGreater(info['w_50'], 4.4)
        self.assertGreater(info['w_50'] / 2.0, 2.19)

        y_T_kicad = geom.origin_y - info['y_T']
        x_min, _, _, _ = geom.edge_cuts_rect

        # 50 Ohm feed at port (rf_polygons[5] = t_junc_kicad)
        t_junc_poly = geom.rf_polygons[5]
        port_pts = [p for p in t_junc_poly if abs(p[0] - x_min) < 1e-4]
        self.assertEqual(len(port_pts), 2)
        rf_y_min = min(p[1] for p in port_pts)
        rf_y_max = max(p[1] for p in port_pts)
        self.assertAlmostEqual(rf_y_max - rf_y_min, info['w_50'], places=4)

        # Top and bottom GND pads on F.Cu (in KiCad: smaller Y = CAD +Y, larger Y = CAD -Y)
        gnd_top_poly, gnd_bot_poly = geom.gnd_polygons_top
        gnd_top_ys = [p[1] for p in gnd_top_poly]
        gnd_bot_ys = [p[1] for p in gnd_bot_poly]

        # No overlap between RF and GND and exact sma_gap = 0.70 mm on both sides
        gap_upper = rf_y_min - max(gnd_top_ys)
        gap_lower = min(gnd_bot_ys) - rf_y_max
        self.assertGreater(gap_upper, 0.0)
        self.assertGreater(gap_lower, 0.0)
        self.assertAlmostEqual(gap_upper, SMA_GAP, places=4)
        self.assertAlmostEqual(gap_lower, SMA_GAP, places=4)

        # All vias lie exactly centered (in Y) and inside (in X) their respective GND pads
        top_center_y = 0.5 * (min(gnd_top_ys) + max(gnd_top_ys))
        bot_center_y = 0.5 * (min(gnd_bot_ys) + max(gnd_bot_ys))
        self.assertEqual(len(geom.vias), 6)
        for v in geom.vias:
            self.assertGreaterEqual(v['x'], x_min + 0.5 - 1e-4)
            self.assertLessEqual(v['x'], x_min + info['sma_pad_len'] - 0.5 + 1e-4)
            dist_to_nearest_center = min(abs(v['y'] - top_center_y), abs(v['y'] - bot_center_y))
            self.assertAlmostEqual(dist_to_nearest_center, 0.0, places=4)

        # F.Mask (separate top/bot SMA GND with dam from RF_IN) and solid B.Mask both expanded (> 8.0 mm)
        self.assertGreater(info['sma_mask_half_h'], 4.0)
        expected_half_h = info['sma_gnd_outer'] + 0.31
        self.assertAlmostEqual(info['sma_mask_half_h'], expected_half_h, places=4)

        # B.Mask: single rectangle across entire SMA width
        bm_xs = [p[0] for p in geom.mask_openings_bottom[0]]
        bm_ys = [p[1] for p in geom.mask_openings_bottom[0]]
        self.assertAlmostEqual(min(bm_xs), x_min, places=4)
        self.assertAlmostEqual(max(bm_xs) - min(bm_xs), info['sma_mask_len'], places=4)
        self.assertAlmostEqual(max(bm_ys) - min(bm_ys), 2.0 * info['sma_mask_half_h'], places=4)
        self.assertLessEqual(min(bm_ys), min(gnd_top_ys) - 0.30 + 1e-4)
        self.assertGreaterEqual(max(bm_ys), max(gnd_bot_ys) + 0.30 + 1e-4)
        self.assertAlmostEqual(0.5 * (min(bm_ys) + max(bm_ys)), y_T_kicad, places=4)

        # F.Mask: 2 separate SMA GND openings with solder mask dam from RF_IN
        fm_top_xs = [p[0] for p in geom.mask_openings[0]]
        fm_top_ys = [p[1] for p in geom.mask_openings[0]]
        fm_bot_xs = [p[0] for p in geom.mask_openings[1]]
        fm_bot_ys = [p[1] for p in geom.mask_openings[1]]
        self.assertAlmostEqual(min(fm_top_xs), x_min, places=4)
        self.assertAlmostEqual(max(fm_top_xs) - min(fm_top_xs), info['sma_mask_len'], places=4)
        self.assertAlmostEqual(min(fm_bot_xs), x_min, places=4)
        self.assertAlmostEqual(max(fm_bot_xs) - min(fm_bot_xs), info['sma_mask_len'], places=4)
        self.assertLessEqual(min(fm_top_ys), min(gnd_top_ys) - 0.30 + 1e-4)
        self.assertGreaterEqual(max(fm_top_ys), max(gnd_top_ys) - 1e-4)
        self.assertLessEqual(min(fm_bot_ys), min(gnd_bot_ys) + 1e-4)
        self.assertGreaterEqual(max(fm_bot_ys), max(gnd_bot_ys) + 0.30 - 1e-4)
        # Solder mask dam separates SMA GND mask from RF_IN mask (t_junc_mask)
        rf_mask_half = info['w_50'] / 2.0 + 0.30
        self.assertLessEqual(max(fm_top_ys), (y_T_kicad - rf_mask_half) - 0.15 + 1e-4)
        self.assertGreaterEqual(min(fm_bot_ys), (y_T_kicad + rf_mask_half) + 0.15 - 1e-4)

    def test_sma_gsg_thin_substrate(self):
        """Verify SMA G-S-G for thinner board (h=0.8 mm, eps_r=4.4 -> narrow w_50)."""
        params = {'patch_L': 28.8, 'patch_W': 28.8, 'sub_h': 0.8, 'eps_r': 4.4}
        geom = get_model4_kicad_geometry(params, is_footprint=False)
        info = geom.routing_info

        self.assertLess(info['w_50'], 2.0)
        self.assertAlmostEqual(info['sma_gnd_inner'], info['w_50'] / 2.0 + SMA_GAP, places=6)
        self.assertAlmostEqual(info['sma_gnd_outer'], info['sma_gnd_inner'] + SMA_PAD_W, places=6)
        # For narrower traces, minimum 4.0 x 8.0 mm mask remains for SMA connector body
        self.assertAlmostEqual(info['sma_mask_len'], 4.0, places=6)
        self.assertAlmostEqual(info['sma_mask_half_h'], 4.0, places=6)

        y_T_kicad = geom.origin_y - info['y_T']
        self.assertAlmostEqual(abs(geom.sma_top_pad_center[1] - y_T_kicad), info['sma_gnd_center_y'], places=4)
        self.assertAlmostEqual(abs(geom.sma_bot_pad_center[1] - y_T_kicad), info['sma_gnd_center_y'], places=4)

    def test_sma_custom_params_and_validation(self):
        """Verify custom SMA parameter settings, aliases, via layout, and validation."""
        base = {'patch_L': 28.8, 'patch_W': 28.8, 'sub_h': 1.52, 'eps_r': 4.3}

        # 1. Longer and wider SMA pads with larger gap
        custom = dict(base, sma_gap=0.90, sma_pad_len=5.0, sma_pad_w=2.0)
        geom = get_model4_kicad_geometry(custom, is_footprint=False)
        info = geom.routing_info
        x_min, _, _, _ = geom.edge_cuts_rect

        self.assertAlmostEqual(info['sma_gap'], 0.90, places=6)
        self.assertAlmostEqual(info['sma_pad_len'], 5.0, places=6)
        self.assertAlmostEqual(info['sma_pad_w'], 2.0, places=6)
        self.assertEqual(geom.sma_pad_size, (5.0, 2.0))
        self.assertAlmostEqual(info['sma_mask_len'], 5.5, places=6)
        self.assertAlmostEqual(info['sma_mask_half_h'], info['sma_gnd_outer'] + 0.31, places=6)

        # All vias lie safely within [0.5, sma_pad_len - 0.5]
        via_x_offsets = sorted({round(v['x'] - x_min, 4) for v in geom.vias})
        self.assertEqual(len(via_x_offsets), 3)
        for off in via_x_offsets:
            self.assertGreaterEqual(off, 0.5 - 1e-4)
            self.assertLessEqual(off, 5.0 - 0.5 + 1e-4)

        # 2. Shorter SMA pads (e.g. 2.4 mm) and aliases
        short_alias = dict(base, sma_gsg_gap=0.55, sma_gnd_pad_len=2.4, sma_gnd_pad_w=1.2)
        geom_short = get_model4_kicad_geometry(short_alias, is_footprint=False)
        x_min_s, _, _, _ = geom_short.edge_cuts_rect
        via_x_short = sorted({round(v['x'] - x_min_s, 4) for v in geom_short.vias})
        self.assertEqual(len(via_x_short), 3)
        for off in via_x_short:
            self.assertGreaterEqual(off, 0.5 - 1e-4)
            self.assertLessEqual(off, 2.4 - 0.5 + 1e-4)

        # 3. Invalid value validation (<= 0 raises ValueError)
        for bad_update in (
            {'sma_gap': 0.0},
            {'sma_gap': -0.2},
            {'sma_pad_len': 0.0},
            {'sma_pad_len': -1.0},
            {'sma_pad_w': 0.0},
            {'sma_pad_w': -0.5},
        ):
            with self.assertRaises(ValueError):
                get_model4_kicad_geometry(dict(base, **bad_update))


class TestKiCadGenerator(unittest.TestCase):
    """Tests for KiCad 10 S-expression generation in kicad_generator.py."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.params = {
            'patch_L': 28.8,
            'patch_W': 28.8,
            'sub_h': 1.52,
            'eps_r': 4.3,
            'design_freq_ghz': 2.3325,
            'port_impedance': 50.0,
        }

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_generate_kicad_pcb(self):
        """Verify generation of a valid KiCad 10 printed circuit board."""
        pcb_file = os.path.join(self.temp_dir.name, "test_antenna.kicad_pcb")
        res = generate_kicad_pcb(self.params, pcb_file)

        self.assertTrue(os.path.exists(pcb_file))
        self.assertTrue(os.path.exists(res['dru_path']))
        self.assertGreater(res['file_size_bytes'], 5000)
        self.assertEqual(res['vias_count'], 6)
        self.assertEqual(res['rf_polygons_count'], 6)
        self.assertEqual(res['mask_openings_count'], 8)
        self.assertEqual(res['mask_openings_bottom_count'], 1)

        with open(pcb_file, "r", encoding="utf-8") as f:
            content = f.read()

        # Check key KiCad 10 elements
        self.assertIn('(kicad_pcb', content)
        self.assertIn('(version 20260206)', content)
        self.assertIn('(generator_version "10.0")', content)
        self.assertIn('(thickness 1.520)', content)
        self.assertIn('(embedded_fonts no)', content)

        # Layers (canonical KiCad 10 numbering)
        self.assertIn('(0 "F.Cu" signal)', content)
        self.assertIn('(2 "B.Cu" power)', content)
        self.assertIn('(1 "F.Mask" user)', content)
        self.assertIn('(3 "B.Mask" user)', content)
        self.assertIn('(17 "Dwgs.User" user "User.Drawings")', content)
        self.assertIn('(19 "Cmts.User" user "User.Comments")', content)
        self.assertIn('(21 "Eco1.User" user "User.Eco1")', content)
        self.assertIn('(23 "Eco2.User" user "User.Eco2")', content)
        self.assertIn('(25 "Edge.Cuts" user)', content)

        # Zones (KiCad 10 uses named nets, full pad connection, and unique priorities for clean DRC)
        self.assertIn('(net "RF_IN")', content)
        self.assertIn('(layer "F.Cu")', content)
        self.assertIn('(net "GND")', content)
        self.assertIn('(layer "B.Cu")', content)
        self.assertIn('(connect_pads yes (clearance 0.20))', content)
        self.assertIn('(filled_polygon\n      (layer "F.Cu")', content)
        self.assertIn('(filled_polygon\n      (layer "B.Cu")', content)
        # Unique priorities for all 6 RF_IN zones (eliminates DRC zones_intersect)
        rf_prios = re.findall(
            r'\(zone\n\s+\(net "RF_IN"\)\n\s+\(layer "F\.Cu"\)\n\s+\(uuid "[^"]+"\)\n\s+\(hatch [^\n]+\)\n\s+\(priority (\d+)\)',
            content,
        )
        self.assertEqual(len(rf_prios), 6)
        self.assertEqual(len(set(rf_prios)), 6)

        # Integrated SMA connector SMD interface (anchors RF_IN and GND nets against isolated_copper)
        self.assertIn('(footprint "SMA_Edge_Launch_142-0701-801"', content)
        self.assertIn('(layers "F.Cu") (net "RF_IN")', content)
        self.assertIn('(layers "B.Cu") (net "GND")', content)

        # Custom DRC rule for edge-launch SMA and full-board B.Cu ground
        with open(res['dru_path'], "r", encoding="utf-8") as f:
            dru_content = f.read()
        self.assertIn('(version 1)', dru_content)
        self.assertIn('(constraint edge_clearance (min -0.1mm))', dru_content)

        # Vias
        self.assertIn('(via (at ', content)
        self.assertIn('(size 0.6000) (drill 0.3000) (layers "F.Cu" "B.Cu") (net "GND")', content)
        self.assertEqual(content.count('(size 0.6000) (drill 0.3000)'), 6)

        # Edge.Cuts rectangle
        self.assertIn('(layer "Edge.Cuts")', content)

        # F.Mask and B.Mask openings
        self.assertIn('(layer "F.Mask")', content)
        self.assertIn('(layer "B.Mask")', content)
        self.assertIn('(fill yes) (layer "B.Mask")', content)

    def test_generate_kicad_footprint(self):
        """Verify generation of a valid library footprint (.kicad_mod)."""
        fp_file = os.path.join(self.temp_dir.name, "Antenna_Model4_LHCP.kicad_mod")
        res = generate_kicad_footprint(self.params, fp_file)

        self.assertTrue(os.path.exists(fp_file))
        self.assertGreater(res['file_size_bytes'], 3000)

        with open(fp_file, "r", encoding="utf-8") as f:
            content = f.read()

        # KiCad 10 footprint header
        self.assertIn('(footprint "Antenna_Model4_LHCP"', content)
        self.assertIn('(version 20260206)', content)
        self.assertIn('(generator_version "10.0")', content)
        self.assertIn('(duplicate_pad_numbers_are_jumpers no)', content)
        self.assertIn('(embedded_fonts no)', content)

        # Anchor point (0, 0) at radiator center in custom pad 1
        self.assertIn('(pad "1" smd custom (at 0 0) (size 1 1) (layers "F.Cu" "F.Mask")', content)
        self.assertIn('(zone_connect 2)', content)
        self.assertIn('(options (clearance outline) (anchor rect))', content)
        self.assertIn('(primitives', content)
        self.assertIn('(gr_poly', content)
        self.assertIn('(width 0) (fill yes)', content)

        # Pads 2 and 3 for SMA GND
        self.assertIn('(pad "2" smd rect (at ', content)
        self.assertIn('(pad "3" smd rect (at ', content)
        self.assertIn('(size 3.5000 1.5000) (layers "F.Cu" "F.Mask")', content)

        # F.Mask and B.Mask openings over SMA
        self.assertIn('(fill yes) (layer "F.Mask")', content)
        self.assertIn('(fill yes) (layer "B.Mask")', content)
        self.assertIn('(solder_mask_margin 0.3000)', content)

        # Outline on F.Fab and F.CrtYd
        self.assertIn('(fill no) (layer "F.Fab")', content)
        self.assertIn('(fill no) (layer "F.CrtYd")', content)

    def test_generate_kicad_pcb_tight_and_full(self):
        """Verify PCB generation in compact and full symmetric modes."""
        # 1. Compact mode
        pcb_tight = os.path.join(self.temp_dir.name, "tight.kicad_pcb")
        res_tight = generate_kicad_pcb(self.params, pcb_tight, tight_pcb=True)
        self.assertTrue(res_tight['tight_pcb'])
        self.assertLess(res_tight['W_sub'], res_tight['routing_info']['W_sub'])
        self.assertLess(res_tight['L_sub'], res_tight['routing_info']['L_sub'])

        with open(pcb_tight, "r", encoding="utf-8") as f:
            content_tight = f.read()
        self.assertIn('(gr_line (start 25.0000 25.0000)', content_tight)

        # 2. Full symmetric mode
        pcb_full = os.path.join(self.temp_dir.name, "full.kicad_pcb")
        res_full = generate_kicad_pcb(self.params, pcb_full, tight_pcb=False)
        self.assertFalse(res_full['tight_pcb'])
        self.assertAlmostEqual(res_full['W_sub'], res_full['routing_info']['W_sub'], places=4)
        self.assertAlmostEqual(res_full['L_sub'], res_full['routing_info']['L_sub'], places=4)

        with open(pcb_full, "r", encoding="utf-8") as f:
            content_full = f.read()
        self.assertIn(f'(end {25.0 + res_full["W_sub"]:.4f}', content_full)

    def test_generate_kicad_pcb_and_footprint_wide_substrate_sma(self):
        """Verify dynamic SMA F.Mask/B.Mask openings and GND pads in .kicad_pcb and .kicad_mod."""
        wide_params = {
            'patch_L': 28.8,
            'patch_W': 28.8,
            'sub_h': 2.0,
            'eps_r': 3.5,
            'design_freq_ghz': 2.3325,
            'port_impedance': 50.0,
            'sma_gap': 0.70,
            'sma_pad_len': 4.20,
            'sma_pad_w': 1.60,
        }
        pcb_file = os.path.join(self.temp_dir.name, "wide.kicad_pcb")
        fp_file = os.path.join(self.temp_dir.name, "wide.kicad_mod")

        res_pcb = generate_kicad_pcb(wide_params, pcb_file)
        res_fp = generate_kicad_footprint(wide_params, fp_file)

        info = res_fp['routing_info']
        expected_mask_len = max(4.0, 4.20 + 0.5)
        expected_half_h = info['sma_gnd_outer'] + 0.31
        self.assertAlmostEqual(info['sma_mask_len'], expected_mask_len, places=4)
        self.assertAlmostEqual(info['sma_mask_half_h'], expected_half_h, places=4)
        self.assertGreater(expected_half_h, 4.5)

        # Footprint (.kicad_mod) check: pads 2, 3 have size 4.20 x 1.60 and F.Mask/B.Mask match dimensions
        with open(fp_file, "r", encoding="utf-8") as f:
            fp_content = f.read()
        self.assertIn('(size 4.2000 1.6000) (layers "F.Cu" "F.Mask")', fp_content)

        # F.Mask in footprint: 2 separate SMA GND rectangles (with solder mask dam from RF_IN)
        f_mask_pattern = (
            r'\(fp_rect \(start ([\-\d\.]+) ([\-\d\.]+)\) \(end ([\-\d\.]+) ([\-\d\.]+)\) '
            r'\(stroke \(width 0\) \(type solid\)\) \(fill yes\) \(layer "F\.Mask"\)'
        )
        f_mask_matches = list(re.finditer(f_mask_pattern, fp_content))
        self.assertEqual(len(f_mask_matches), 2, "Expected 2 separate SMA GND fp_rect items on F.Mask")
        expected_gnd_h = expected_half_h - info['sma_gnd_mask_inner']
        for m in f_mask_matches:
            sx, sy, ex, ey = (float(m.group(i)) for i in range(1, 5))
            self.assertAlmostEqual(ex - sx, expected_mask_len, places=3)
            self.assertAlmostEqual(ey - sy, expected_gnd_h, places=3)

        # B.Mask in footprint: single rectangle across full SMA width
        b_mask_pattern = (
            r'\(fp_rect \(start ([\-\d\.]+) ([\-\d\.]+)\) \(end ([\-\d\.]+) ([\-\d\.]+)\) '
            r'\(stroke \(width 0\) \(type solid\)\) \(fill yes\) \(layer "B\.Mask"\)'
        )
        m_b = re.search(b_mask_pattern, fp_content)
        self.assertIsNotNone(m_b, "Missing SMA fp_rect on B.Mask layer")
        sx, sy, ex, ey = (float(m_b.group(i)) for i in range(1, 5))
        self.assertAlmostEqual(ex - sx, expected_mask_len, places=3)
        self.assertAlmostEqual(ey - sy, 2.0 * expected_half_h, places=3)

        # PCB (.kicad_pcb) check: B.Mask polygon has exact dynamic dimensions
        with open(pcb_file, "r", encoding="utf-8") as f:
            pcb_content = f.read()
        self.assertIn('(thickness 2.000)', pcb_content)
        self.assertEqual(res_pcb['vias_count'], 6)
        b_mask_block = re.search(
            r'\(gr_poly\n\s+\(pts\n((?:\s+\(xy [^\n]+\n)+)\s+\)\n'
            r'\s+\(stroke \(width 0\) \(type solid\)\) \(fill yes\) \(layer "B\.Mask"\)',
            pcb_content,
        )
        self.assertIsNotNone(b_mask_block, "Missing B.Mask SMA polygon in .kicad_pcb")
        coords = [
            (float(x), float(y))
            for x, y in re.findall(r'\(xy ([\-\d\.]+) ([\-\d\.]+)\)', b_mask_block.group(1))
        ]
        xs = [c[0] for c in coords]
        ys = [c[1] for c in coords]
        self.assertAlmostEqual(max(xs) - min(xs), expected_mask_len, places=3)
        self.assertAlmostEqual(max(ys) - min(ys), 2.0 * expected_half_h, places=3)


class TestExportCli(unittest.TestCase):
    """Tests for CLI script scripts/export_kicad.py."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp_dir.cleanup()

    @staticmethod
    def _no_profile_env(extra=None):
        """Return an environment isolated from any ANTENNA_PROFILE in root .env."""
        env = os.environ.copy()
        env["ANTENNA_PROFILE"] = ""
        env.pop("PROFILE_NAME", None)
        env.pop("SILKSCREEN_SUBTITLE", None)
        if extra:
            env.update(extra)
        return env

    def test_cli_export_all(self):
        """Run CLI script with --all into a temporary directory."""
        cmd = [
            sys.executable,
            os.path.join(SCRIPTS_DIR, "export_kicad.py"),
            "--output-dir", self.temp_dir.name,
            "--all",
            "--patch-l", "29.81",
            "--delta-l", "18.66",
        ]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=self._no_profile_env())
        self.assertEqual(proc.returncode, 0, f"Script failed with error:\n{proc.stderr}")

        pcb_file = os.path.join(self.temp_dir.name, "antenna_model4.kicad_pcb")
        dru_file = os.path.join(self.temp_dir.name, "antenna_model4.kicad_dru")
        fp_file = os.path.join(self.temp_dir.name, "Antenna_Model4_LHCP.kicad_mod")

        self.assertTrue(os.path.exists(pcb_file))
        self.assertTrue(os.path.exists(dru_file))
        self.assertTrue(os.path.exists(fp_file))
        self.assertIn("Export completed successfully", proc.stdout)

    def test_cli_export_pcb_only(self):
        """Run CLI script for PCB only (--pcb)."""
        cmd = [
            sys.executable,
            os.path.join(SCRIPTS_DIR, "export_kicad.py"),
            "--output-dir", self.temp_dir.name,
            "--pcb",
        ]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=self._no_profile_env())
        self.assertEqual(proc.returncode, 0)

        pcb_file = os.path.join(self.temp_dir.name, "antenna_model4.kicad_pcb")
        fp_file = os.path.join(self.temp_dir.name, "Antenna_Model4_LHCP.kicad_mod")

        self.assertTrue(os.path.exists(pcb_file))
        self.assertFalse(os.path.exists(fp_file))

    def test_cli_export_with_mask_clearance(self):
        """Run CLI script with optional --mask-clearance."""
        cmd = [
            sys.executable,
            os.path.join(SCRIPTS_DIR, "export_kicad.py"),
            "--output-dir", self.temp_dir.name,
            "--all",
            "--mask-clearance", "0.40",
        ]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=self._no_profile_env())
        self.assertEqual(proc.returncode, 0)
        self.assertRegex(proc.stdout, r"Solder mask clearance:\s*0\.40 mm")

        fp_file = os.path.join(self.temp_dir.name, "Antenna_Model4_LHCP.kicad_mod")
        with open(fp_file, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn('(solder_mask_margin 0.4000)', content)
        self.assertIn('(layer "B.Mask")', content)

    def test_cli_tight_pcb_options(self):
        """Verify board crop CLI flags: --tight-pcb, --no-tight-pcb, --crop-pcb, --full-pcb."""
        # 1. Default / explicit --tight-pcb (with reference profile urel)
        cmd_tight = [
            sys.executable,
            os.path.join(SCRIPTS_DIR, "export_kicad.py"),
            "--profile", "urel",
            "--output-dir", os.path.join(self.temp_dir.name, "tight"),
            "--tight-pcb",
            "--patch-l", "29.95",
        ]
        proc_tight = subprocess.run(cmd_tight, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(proc_tight.returncode, 0)
        self.assertIn("Compact / trimmed (tight_pcb=True)", proc_tight.stdout)
        # With TRANS_L_L=18.70 loaded from profile urel, compact width is 73.10 mm
        self.assertIn("73.10 mm", proc_tight.stdout)
        self.assertIn("area savings", proc_tight.stdout)

        # 2. Full symmetric mode --no-tight-pcb
        cmd_full = [
            sys.executable,
            os.path.join(SCRIPTS_DIR, "export_kicad.py"),
            "--profile", "urel",
            "--output-dir", os.path.join(self.temp_dir.name, "full"),
            "--no-tight-pcb",
            "--patch-l", "29.95",
        ]
        proc_full = subprocess.run(cmd_full, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(proc_full.returncode, 0)
        self.assertIn("Full symmetric (tight_pcb=False)", proc_full.stdout)
        self.assertIn("96.24 mm", proc_full.stdout)

        # 3. Aliases --crop-pcb and --full-pcb
        cmd_alias = [
            sys.executable,
            os.path.join(SCRIPTS_DIR, "export_kicad.py"),
            "--output-dir", os.path.join(self.temp_dir.name, "alias"),
            "--crop-pcb",
            "--margin-right", "12.0",
        ]
        proc_alias = subprocess.run(cmd_alias, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=self._no_profile_env())
        self.assertEqual(proc_alias.returncode, 0)
        self.assertIn("Compact / trimmed", proc_alias.stdout)

    def test_cli_sma_options_and_env_override(self):
        """Verify CLI flags --sma-gap, --sma-pad-len, --sma-pad-w and environment variables."""
        # 1. CLI overrides including wider substrate
        cmd_cli = [
            sys.executable,
            os.path.join(SCRIPTS_DIR, "export_kicad.py"),
            "--output-dir", os.path.join(self.temp_dir.name, "cli_sma"),
            "--all",
            "--sub-h", "2.0",
            "--eps-r", "3.5",
            "--sma-gap", "0.85",
            "--sma-pad-len", "4.50",
            "--sma-pad-w", "1.80",
        ]
        proc_cli = subprocess.run(cmd_cli, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=self._no_profile_env())
        self.assertEqual(proc_cli.returncode, 0, f"CLI failed:\n{proc_cli.stderr}")
        self.assertIn("gap=0.85 mm", proc_cli.stdout)
        self.assertIn("pad=4.50x1.80 mm", proc_cli.stdout)

        fp_file = os.path.join(self.temp_dir.name, "cli_sma", "Antenna_Model4_LHCP.kicad_mod")
        with open(fp_file, "r", encoding="utf-8") as f:
            fp_content = f.read()
        self.assertIn('(size 4.5000 1.8000) (layers "F.Cu" "F.Mask")', fp_content)

        # 2. Loading from SMA_GAP, SMA_PAD_LEN, SMA_PAD_W environment variables
        env = self._no_profile_env({
            "SMA_GAP": "0.60",
            "SMA_PAD_LEN": "4.00",
            "SMA_PAD_W": "1.60",
        })
        cmd_env = [
            sys.executable,
            os.path.join(SCRIPTS_DIR, "export_kicad.py"),
            "--output-dir", os.path.join(self.temp_dir.name, "env_sma"),
            "--footprint",
        ]
        proc_env = subprocess.run(cmd_env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
        self.assertEqual(proc_env.returncode, 0, f"CLI with env failed:\n{proc_env.stderr}")
        self.assertIn("gap=0.60 mm", proc_env.stdout)
        self.assertIn("pad=4.00x1.60 mm", proc_env.stdout)

        # 3. Invalid value --sma-gap <= 0 fails with error
        cmd_bad = [
            sys.executable,
            os.path.join(SCRIPTS_DIR, "export_kicad.py"),
            "--output-dir", os.path.join(self.temp_dir.name, "bad_sma"),
            "--pcb",
            "--sma-gap", "0",
        ]
        proc_bad = subprocess.run(cmd_bad, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=self._no_profile_env())
        self.assertNotEqual(proc_bad.returncode, 0)
        self.assertIn("ValueError", proc_bad.stderr)

    @staticmethod
    def _extract_rf_zones_from_pcb(pcb_content: str):
        """Extract lists of (x, y) points for all RF_IN zones in .kicad_pcb."""
        pattern = (
            r'\(zone\n\s+\(net "RF_IN"\)\n\s+\(layer "F\.Cu"\).*?'
            r'\(polygon\n\s+\(pts\n((?:\s+\(xy [^\n]+\n)+)\s+\)\n\s+\)'
        )
        polygons = []
        for match in re.finditer(pattern, pcb_content, re.DOTALL):
            pts = [
                (float(x), float(y))
                for x, y in re.findall(r'\(xy ([\-\d\.]+) ([\-\d\.]+)\)', match.group(1))
            ]
            polygons.append(pts)
        return polygons

    @staticmethod
    def _extract_gr_polys_from_footprint(fp_content: str):
        """Extract lists of (x, y) points for all gr_poly primitives of pad 1 in .kicad_mod."""
        pattern = r'\(gr_poly\n\s+\(pts\n((?:\s+\(xy [^\n]+\n)+)\s+\)'
        polygons = []
        for match in re.finditer(pattern, fp_content):
            pts = [
                (float(x), float(y))
                for x, y in re.findall(r'\(xy ([\-\d\.]+) ([\-\d\.]+)\)', match.group(1))
            ]
            polygons.append(pts)
        return polygons

    def test_load_model4_params_from_env_asymmetric_transformers_and_insets(self):
        """Verify loading asymmetric TRANS_* and FEED_INSET* from env and propagating to geometry and files."""
        env_asym = {
            "PATCH_L": "29.95",
            "PATCH_W": "29.95",
            "SUB_H": "1.52",
            "EPS_R": "4.3",
            "TRANS_W": "0.30",
            "TRANS_W_B": "0.36",
            "TRANS_W_L": "0.44",
            "TRANS_L": "19.00",
            "TRANS_L_B": "19.50",
            "TRANS_L_L": "18.70",
            "FEED_INSET": "2.80",
            "FEED_INSET_B": "2.20",
            "FEED_INSET_GAP": "0.60",
            "FEED_INSET_GAP_L": "0.45",
        }
        with mock.patch.dict(os.environ, env_asym, clear=True):
            params = load_model4_params_from_env()

        # 1. Verify loaded parameters and FEED_INSET / FEED_INSET_GAP fallbacks
        self.assertAlmostEqual(params['trans_w'], 0.30, places=6)
        self.assertAlmostEqual(params['trans_w_b'], 0.36, places=6)
        self.assertAlmostEqual(params['trans_w_l'], 0.44, places=6)
        self.assertAlmostEqual(params['trans_l'], 19.00, places=6)
        self.assertAlmostEqual(params['trans_l_b'], 19.50, places=6)
        self.assertAlmostEqual(params['trans_l_l'], 18.70, places=6)
        self.assertAlmostEqual(params['feed_inset_b'], 2.20, places=6)
        self.assertAlmostEqual(params['feed_inset_l'], 2.80, places=6)
        self.assertAlmostEqual(params['feed_inset_gap_b'], 0.60, places=6)
        self.assertAlmostEqual(params['feed_inset_gap_l'], 0.45, places=6)

        # 2. Verify transformer polygon geometry in get_model4_kicad_geometry()
        geom = get_model4_kicad_geometry(params, is_footprint=False)
        info = geom.routing_info
        self.assertAlmostEqual(info['w_T_b'], 0.36, places=6)
        self.assertAlmostEqual(info['w_T_l'], 0.44, places=6)
        self.assertAlmostEqual(info['l_T_b'], 19.50, places=6)
        self.assertAlmostEqual(info['l_T_l'], 18.70, places=6)
        self.assertAlmostEqual(info['inset_b'], 2.20, places=6)
        self.assertAlmostEqual(info['inset_l'], 2.80, places=6)
        self.assertAlmostEqual(info['inset_gap_b'], 0.60, places=6)
        self.assertAlmostEqual(info['inset_gap_l'], 0.45, places=6)

        # rf_polygons[1] = bottom transformer (width in X, length + 2*delta in Y)
        trans_b_xs = [p[0] for p in geom.rf_polygons[1]]
        trans_b_ys = [p[1] for p in geom.rf_polygons[1]]
        self.assertAlmostEqual(max(trans_b_xs) - min(trans_b_xs), 0.36, places=4)
        self.assertAlmostEqual(max(trans_b_ys) - min(trans_b_ys), 19.50 + 2.0 * OVERLAP_DELTA, places=4)

        # rf_polygons[2] = left transformer (length + 2*delta in X, width in Y)
        trans_l_xs = [p[0] for p in geom.rf_polygons[2]]
        trans_l_ys = [p[1] for p in geom.rf_polygons[2]]
        self.assertAlmostEqual(max(trans_l_xs) - min(trans_l_xs), 18.70 + 2.0 * OVERLAP_DELTA, places=4)
        self.assertAlmostEqual(max(trans_l_ys) - min(trans_l_ys), 0.44, places=4)

        # 3. Verify that asymmetric dimensions are actually written to .kicad_pcb and .kicad_mod
        pcb_file = os.path.join(self.temp_dir.name, "asym_env.kicad_pcb")
        fp_file = os.path.join(self.temp_dir.name, "asym_env.kicad_mod")
        generate_kicad_pcb(params, pcb_file)
        generate_kicad_footprint(params, fp_file)

        with open(pcb_file, "r", encoding="utf-8") as f:
            pcb_zones = self._extract_rf_zones_from_pcb(f.read())
        self.assertEqual(len(pcb_zones), 6)
        pcb_tb_xs = [p[0] for p in pcb_zones[1]]
        pcb_tb_ys = [p[1] for p in pcb_zones[1]]
        pcb_tl_xs = [p[0] for p in pcb_zones[2]]
        pcb_tl_ys = [p[1] for p in pcb_zones[2]]
        self.assertAlmostEqual(max(pcb_tb_xs) - min(pcb_tb_xs), 0.36, places=3)
        self.assertAlmostEqual(max(pcb_tb_ys) - min(pcb_tb_ys), 19.50 + 2.0 * OVERLAP_DELTA, places=3)
        self.assertAlmostEqual(max(pcb_tl_xs) - min(pcb_tl_xs), 18.70 + 2.0 * OVERLAP_DELTA, places=3)
        self.assertAlmostEqual(max(pcb_tl_ys) - min(pcb_tl_ys), 0.44, places=3)

        with open(fp_file, "r", encoding="utf-8") as f:
            fp_polys = self._extract_gr_polys_from_footprint(f.read())
        self.assertEqual(len(fp_polys), 6)
        fp_tb_xs = [p[0] for p in fp_polys[1]]
        fp_tb_ys = [p[1] for p in fp_polys[1]]
        fp_tl_xs = [p[0] for p in fp_polys[2]]
        fp_tl_ys = [p[1] for p in fp_polys[2]]
        self.assertAlmostEqual(max(fp_tb_xs) - min(fp_tb_xs), 0.36, places=3)
        self.assertAlmostEqual(max(fp_tb_ys) - min(fp_tb_ys), 19.50 + 2.0 * OVERLAP_DELTA, places=3)
        self.assertAlmostEqual(max(fp_tl_xs) - min(fp_tl_xs), 18.70 + 2.0 * OVERLAP_DELTA, places=3)
        self.assertAlmostEqual(max(fp_tl_ys) - min(fp_tl_ys), 0.44, places=3)

        # 4. Priority of branch-specific TRANS_L_B over general TRANS_L; left branch inherits TRANS_L
        env_partial = {
            "TRANS_L": "19.10",
            "TRANS_L_B": "19.65",
        }
        with mock.patch.dict(os.environ, env_partial, clear=True):
            params_partial = load_model4_params_from_env()
        info_partial = compute_model4_routing(params_partial)
        self.assertAlmostEqual(info_partial['l_T_b'], 19.65, places=6)
        self.assertAlmostEqual(info_partial['l_T_l'], 19.10, places=6)

    def test_cli_asymmetric_transformer_and_inset_options(self):
        """Verify asymmetric CLI flags --trans-*-{b,l} and --inset*-{b,l} in export_kicad.py."""
        out_dir = os.path.join(self.temp_dir.name, "cli_asym")
        cmd = [
            sys.executable,
            os.path.join(SCRIPTS_DIR, "export_kicad.py"),
            "--output-dir", out_dir,
            "--all",
            "--patch-l", "29.95",
            "--patch-w", "29.95",
            "--trans-w-b", "0.36",
            "--trans-w-l", "0.44",
            "--trans-l-b", "19.60",
            "--trans-l-l", "18.60",
            "--inset-b", "2.20",
            "--inset-l", "2.90",
            "--inset-gap-b", "0.45",
            "--inset-gap-l", "0.65",
        ]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=self._no_profile_env())
        self.assertEqual(proc.returncode, 0, f"CLI failed:\n{proc.stderr}")

        # Verify summary table output for both branches
        self.assertRegex(proc.stdout, r"Bottom transformer \(w_T_b/l_T_b\):\s*0\.360 mm / 19\.600 mm")
        self.assertRegex(proc.stdout, r"Left transformer \(w_T_l/l_T_l\):\s*0\.440 mm / 18\.600 mm")
        self.assertRegex(proc.stdout, r"Bottom inset \(inset_b / gap_b\):\s*2\.20 mm / 0\.45 mm")
        self.assertRegex(proc.stdout, r"Left inset \(inset_l / gap_l\):\s*2\.90 mm / 0\.65 mm")

        # Verify actual geometry in .kicad_mod (in footprint coordinates, patch center is at (0, 0))
        fp_file = os.path.join(out_dir, "Antenna_Model4_LHCP.kicad_mod")
        with open(fp_file, "r", encoding="utf-8") as f:
            fp_polys = self._extract_gr_polys_from_footprint(f.read())
        self.assertEqual(len(fp_polys), 6)

        # Transformers
        tb_xs = [p[0] for p in fp_polys[1]]
        tb_ys = [p[1] for p in fp_polys[1]]
        tl_xs = [p[0] for p in fp_polys[2]]
        tl_ys = [p[1] for p in fp_polys[2]]
        self.assertAlmostEqual(max(tb_xs) - min(tb_xs), 0.36, places=3)
        self.assertAlmostEqual(max(tb_ys) - min(tb_ys), 19.60 + 2.0 * OVERLAP_DELTA, places=3)
        self.assertAlmostEqual(max(tl_xs) - min(tl_xs), 18.60 + 2.0 * OVERLAP_DELTA, places=3)
        self.assertAlmostEqual(max(tl_ys) - min(tl_ys), 0.44, places=3)

        # Verify asymmetric inset notches on patch polygon (fp_polys[0]):
        # Left notch has depth 2.90 mm (-W/2 + 2.90) and height 0.44 + 2*0.65 = 1.74 mm
        # Bottom notch (in KiCad +Y downward) has depth 2.20 mm (L/2 - 2.20) and width 0.36 + 2*0.45 = 1.26 mm
        patch_pts = fp_polys[0]
        half_w = 29.95 / 2.0
        half_l = 29.95 / 2.0
        left_notch_pts = [p for p in patch_pts if abs(p[0] - (-half_w + 2.90)) < 1e-3]
        self.assertEqual(len(left_notch_pts), 2)
        self.assertAlmostEqual(
            max(p[1] for p in left_notch_pts) - min(p[1] for p in left_notch_pts),
            0.44 + 2.0 * 0.65,
            places=3,
        )
        bot_notch_pts = [p for p in patch_pts if abs(p[1] - (half_l - 2.20)) < 1e-3]
        self.assertEqual(len(bot_notch_pts), 2)
        self.assertAlmostEqual(
            max(p[0] for p in bot_notch_pts) - min(p[0] for p in bot_notch_pts),
            0.36 + 2.0 * 0.45,
            places=3,
        )

    def test_cli_branch_priority_over_general_and_symmetric_output(self):
        """Verify priority of branch flags over general flags (--trans-l, --inset) and symmetric output display."""
        # 1. Branch flags take precedence over general CLI flags (and general CLI flags override asymmetric .env)
        cmd_prio = [
            sys.executable,
            os.path.join(SCRIPTS_DIR, "export_kicad.py"),
            "--output-dir", os.path.join(self.temp_dir.name, "cli_prio"),
            "--footprint",
            "--trans-w", "0.35",
            "--trans-w-b", "0.41",
            "--trans-l", "19.00",
            "--trans-l-b", "19.80",
            "--inset", "2.40",
            "--inset-l", "3.10",
            "--inset-gap", "0.50",
            "--inset-gap-b", "0.40",
        ]
        proc_prio = subprocess.run(cmd_prio, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=self._no_profile_env())
        self.assertEqual(proc_prio.returncode, 0, f"CLI failed:\n{proc_prio.stderr}")
        self.assertRegex(proc_prio.stdout, r"Bottom transformer \(w_T_b/l_T_b\):\s*0\.410 mm / 19\.800 mm")
        self.assertRegex(proc_prio.stdout, r"Left transformer \(w_T_l/l_T_l\):\s*0\.350 mm / 19\.000 mm")
        self.assertRegex(proc_prio.stdout, r"Bottom inset \(inset_b / gap_b\):\s*2\.40 mm / 0\.40 mm")
        self.assertRegex(proc_prio.stdout, r"Left inset \(inset_l / gap_l\):\s*3\.10 mm / 0\.50 mm")

        # 2. General --trans-l / --trans-w overrides asymmetric .env and prints single-line symmetric summary
        cmd_sym = [
            sys.executable,
            os.path.join(SCRIPTS_DIR, "export_kicad.py"),
            "--output-dir", os.path.join(self.temp_dir.name, "cli_sym"),
            "--footprint",
            "--trans-w", "0.38",
            "--trans-l", "19.10",
            "--inset", "2.50",
            "--inset-gap", "0.50",
        ]
        proc_sym = subprocess.run(cmd_sym, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=self._no_profile_env())
        self.assertEqual(proc_sym.returncode, 0, f"CLI failed:\n{proc_sym.stderr}")
        self.assertRegex(proc_sym.stdout, r"Quarter-wave transformer w_T / l_T:\s*0\.380 mm / 19\.100 mm")
        self.assertNotIn("Bottom transformer", proc_sym.stdout)
        self.assertNotIn("Left transformer", proc_sym.stdout)

        # 3. Environment variable priority: TRANS_L_B overrides TRANS_L; left branch inherits TRANS_L
        env_prio = self._no_profile_env({
            "TRANS_W": "0.34",
            "TRANS_W_B": "",
            "TRANS_W_L": "",
            "TRANS_L": "19.00",
            "TRANS_L_B": "19.75",
            "TRANS_L_L": "",
        })
        cmd_env = [
            sys.executable,
            os.path.join(SCRIPTS_DIR, "export_kicad.py"),
            "--output-dir", os.path.join(self.temp_dir.name, "env_prio"),
            "--footprint",
        ]
        proc_env = subprocess.run(cmd_env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env_prio)
        self.assertEqual(proc_env.returncode, 0, f"CLI with env failed:\n{proc_env.stderr}")
        self.assertRegex(proc_env.stdout, r"Bottom transformer \(w_T_b/l_T_b\):\s*0\.340 mm / 19\.750 mm")
        self.assertRegex(proc_env.stdout, r"Left transformer \(w_T_l/l_T_l\):\s*0\.340 mm / 19\.000 mm")


if __name__ == "__main__":
    unittest.main()
