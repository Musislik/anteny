"""
test_kicad_export.py - Komplexní jednotkové testy pro Pure-Python KiCad generátor Modelu 4.
Testuje:
  1. antenna_geometry.py:
     - Analytický výpočet délek zakřivených tras (calc_curved_path_length).
     - Generování 2D polygonových obrysů tras s oblouky (compute_curved_ribbon_outline).
     - Konstrukci T-článku se zaobleními (compute_t_junction_polygon).
     - Analýzu trasování Modelu 4 a fázovou rovnováhu Delta L (compute_model4_routing).
     - Transformaci souřadnic z CAD do KiCad při striktním zachování LHCP polarizace.
     - Přesahy 50 µm pro eliminaci DRC mikro-mezer.
     - SMA G-S-G rozhraní (Cinch Johnson 142-0701-801, 6 prokovů).
  2. kicad_generator.py:
     - Generování výrobní DPS (.kicad_pcb) KiCad 10 (verze 20260206).
     - Ověření pojmenovaných sítí ("GND", "RF_IN") a kanonických vrstev KiCad 10.
     - Zóny F.Cu, celistvá zem B.Cu, Edge.Cuts obrys, F.Mask otvory, 6 GND prokovů.
     - Generování knihovního pouzdra (.kicad_mod) s kotevním bodem (0, 0) uprostřed flíčku.
     - Zákaznický SMD pad 1 s celou RF geometrií a SMD pady 2, 3 pro SMA GND.
  3. scripts/export_kicad.py:
     - CLI rozhraní a parametry (--pcb, --footprint, --all, parametrické přepisy).
"""

import math
import os
import re
import subprocess
import sys
import tempfile
import unittest

# Přidání kořene projektu a složek src a scripts do sys.path
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(TESTS_DIR, ".."))
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "scripts")

for p in (PROJECT_ROOT, SRC_DIR, SCRIPTS_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

from antenna_geometry import (
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
from kicad_generator import (
    generate_kicad_footprint,
    generate_kicad_pcb,
)


class TestAntennaGeometry(unittest.TestCase):
    """Testy analytických výpočtů a geometrie v antenna_geometry.py."""

    def test_rf_formulas_pure_python(self):
        """Ověření analytických vzorců pro mikropásek a čtvrtvlnnou délku."""
        h = 1.52
        eps_r = 4.3
        # Syntéza 50 Ohm vedení
        w_50 = synth_microstrip_w(50.0, h, eps_r)
        self.assertAlmostEqual(w_50, 2.98, delta=0.05)

        # Kontrola zpětného výpočtu impedance
        z0_calc = calc_microstrip_z0(w_50, h, eps_r)
        self.assertAlmostEqual(z0_calc, 50.0, delta=0.01)

        # Efektivní permitivita a čtvrtvlnná délka
        eps_eff = calc_microstrip_eps_eff(w_50, h, eps_r)
        self.assertTrue(1.0 < eps_eff < eps_r)
        lambda_g_4 = calc_quarter_wave_length(2.3325, eps_eff)
        self.assertTrue(15.0 < lambda_g_4 < 25.0)

    def test_curved_path_length(self):
        """Ověření výpočtu délky ortogonální trasy s 90° kruhovými oblouky."""
        # 90° roh: rovný úsek 1 (10 - R) + rovný úsek 2 (10 - R) + čtvrtkruh (pi * R / 2)
        r = 3.0
        pts = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)]
        expected = (10.0 - r) + (10.0 - r) + 0.5 * math.pi * r
        calc_len = calc_curved_path_length(pts, r)
        self.assertAlmostEqual(calc_len, expected, places=7)

        # Přímá čára bez rohů
        pts_straight = [(0.0, 0.0), (15.0, 0.0)]
        self.assertAlmostEqual(calc_curved_path_length(pts_straight, r), 15.0, places=7)

        # Příliš krátký segment vzhledem k poloměru vyvolá výjimku
        pts_short = [(0.0, 0.0), (2.0, 0.0), (2.0, 10.0)]
        with self.assertRaises(ValueError):
            calc_curved_path_length(pts_short, 3.0)

    def test_curved_ribbon_outline(self):
        """Ověření generování 2D polygonu vedení s kruhovými oblouky."""
        pts = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)]
        width = 0.694
        outline = compute_curved_ribbon_outline(pts, width, bend_radius=3.0, arc_samples=16)

        self.assertGreater(len(outline), 20)
        # První bod leží v kolmici k počátku na vzdálenost width/2
        self.assertAlmostEqual(outline[0][0], 0.0, places=4)
        self.assertAlmostEqual(abs(outline[0][1]), width / 2.0, places=4)
        # Poslední bod leží v kolmici k počátku na opačné straně
        self.assertAlmostEqual(outline[-1][0], 0.0, places=4)
        self.assertAlmostEqual(abs(outline[-1][1]), width / 2.0, places=4)

    def test_t_junction_polygon(self):
        """Ověření geometrie T-článku bez zaoblení i s kruhovými zaobleními."""
        # Bez zaoblení
        poly_sharp = compute_t_junction_polygon(
            x_port=-45.0, x_T=-38.0, y_T=-28.0, w_50=2.98, w_feed=0.694, t_fillet_r=0.0
        )
        self.assertEqual(len(poly_sharp), 8)

        # Se zaoblením r = 0.8 mm
        poly_fillet = compute_t_junction_polygon(
            x_port=-45.0, x_T=-38.0, y_T=-28.0, w_50=2.98, w_feed=0.694, t_fillet_r=0.8, arc_samples=8
        )
        self.assertGreater(len(poly_fillet), 12)
        # Kontrola, že polygon začíná i končí na x_port
        self.assertAlmostEqual(poly_fillet[0][0], -45.0, places=4)
        self.assertAlmostEqual(poly_fillet[-1][0], -45.0, places=4)

    def test_patch_with_insets_polygon(self):
        """Ověření uzavřeného obrysu vyzařujícího flíčku se zářezy."""
        poly = compute_patch_with_insets_polygon(
            W=28.8, L=28.8, inset_b=2.5, inset_l=2.5, w_T_b=0.42, w_T_l=0.42, gap_b=0.5, gap_l=0.5
        )
        self.assertGreater(len(poly), 8)
        # Flíček sahá k W/2 = 14.4 a L/2 = 14.4
        xs = [p[0] for p in poly]
        ys = [p[1] for p in poly]
        self.assertAlmostEqual(max(xs), 14.4, places=4)
        self.assertAlmostEqual(min(xs), -14.4, places=4)
        self.assertAlmostEqual(max(ys), 14.4, places=4)
        self.assertAlmostEqual(min(ys), -14.4, places=4)

    def test_model4_routing_and_phase_balance(self):
        """Ověření, že rozdíl drah L_100_b - L_100_l přesně odpovídá Delta L."""
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
        Ověření, že transformace x_kicad = x0 + x_cad, y_kicad = y0 - y_cad
        striktně zachovává prostorovou orientaci a LHCP polarizaci.
        """
        params = {'patch_L': 28.8, 'sub_h': 1.52, 'eps_r': 4.3}
        geom = get_model4_kicad_geometry(params, is_footprint=False)

        # 1. Počátek desky a kladné souřadnice
        x_min, y_min, x_max, y_max = geom.edge_cuts_rect
        self.assertGreater(x_min, 0.0)
        self.assertGreater(y_min, 0.0)
        self.assertAlmostEqual(x_max - x_min, geom.W_sub, places=4)
        self.assertAlmostEqual(y_max - y_min, geom.L_sub, places=4)

        # 2. V CAD leží spodní větev (Ey, zpoždění -90°) na záporném Y.
        # V KiCadu (kde +Y směřuje dolů) musí spodní větev ležet na VĚTŠÍM y_kicad než střed desky!
        info = geom.routing_info
        cad_y_T = info['y_T']  # záporné číslo (např. -28.4 mm)
        self.assertLess(cad_y_T, 0.0)

        # Y souřadnice v KiCadu:
        kicad_y_T = geom.origin_y - cad_y_T
        self.assertGreater(kicad_y_T, geom.origin_y)

        # Levá větev (Ex, 0°) leží na záporném X v CAD -> menší x_kicad než střed
        cad_x_T = info['x_T']
        self.assertLess(cad_x_T, 0.0)
        kicad_x_T = geom.origin_x + cad_x_T
        self.assertLess(kicad_x_T, geom.origin_x)

        # 3. Kontrola SMA rozhraní: 6 prokovů
        self.assertEqual(len(geom.vias), 6)
        for v in geom.vias:
            self.assertEqual(v['drill'], 0.30)
            self.assertEqual(v['size'], 0.60)
            self.assertEqual(v['net'], 1)
            self.assertEqual(v['net_name'], "GND")

    def test_solder_mask_clearance_and_bottom_opening(self):
        """Ověření přesahu nepájivé masky (solder mask clearance) a otvoru na B.Mask."""
        params = {
            'patch_L': 28.8,
            'patch_W': 28.8,
            'sub_h': 1.52,
            'eps_r': 4.3,
            'mask_clearance': 0.30,
        }
        geom = get_model4_kicad_geometry(params, is_footprint=False)

        # 1. Počty polygonů otvorů masky
        # F.Mask má 7 polygonů (SMA, patch, trans_b, trans_l, arm_l, arm_b, t_junc)
        self.assertEqual(len(geom.mask_openings), 7)
        # B.Mask má 1 polygon (SMA rozhraní)
        self.assertEqual(len(geom.mask_openings_bottom), 1)

        # 2. Ověření rozměrů masky vyzařovače (rozšíření o mask_clearance na každé straně)
        patch_mask = geom.mask_openings[1]
        xs = [p[0] for p in patch_mask]
        ys = [p[1] for p in patch_mask]
        patch_w_mask = max(xs) - min(xs)
        patch_l_mask = max(ys) - min(ys)
        self.assertAlmostEqual(patch_w_mask, 28.8 + 2 * 0.30, places=4)
        self.assertAlmostEqual(patch_l_mask, 28.8 + 2 * 0.30, places=4)

        # 3. Ověření spodního transformátoru v masce (rozšířen v šířce o 2 * mask_clearance)
        trans_b_mask = geom.mask_openings[2]
        tb_xs = [p[0] for p in trans_b_mask]
        w_tb_mask = max(tb_xs) - min(tb_xs)
        info = geom.routing_info
        self.assertAlmostEqual(w_tb_mask, info['w_T_b'] + 2 * 0.30, places=4)

        # 4. Ověření levého transformátoru v masce (rozšířen v šířce o 2 * mask_clearance v ose Y)
        trans_l_mask = geom.mask_openings[3]
        tl_ys = [p[1] for p in trans_l_mask]
        w_tl_mask = max(tl_ys) - min(tl_ys)
        self.assertAlmostEqual(w_tl_mask, info['w_T_l'] + 2 * 0.30, places=4)

        # 5. Ověření otvoru na B.Mask (SMA rozhraní 4.0 mm x 8.0 mm na hraně desky)
        b_mask_poly = geom.mask_openings_bottom[0]
        bm_xs = [p[0] for p in b_mask_poly]
        bm_ys = [p[1] for p in b_mask_poly]
        self.assertAlmostEqual(max(bm_xs) - min(bm_xs), 4.0, places=4)
        self.assertAlmostEqual(max(bm_ys) - min(bm_ys), 8.0, places=4)
        # Začíná přesně na levé hraně desky (x_min Edge.Cuts)
        x_min, _, _, _ = geom.edge_cuts_rect
        self.assertAlmostEqual(min(bm_xs), x_min, places=4)

    def test_tight_pcb_bounds_and_cropping(self):
        """Ověření kompaktního ořezu desky (tight_pcb=True) a plného symetrického režimu (tight_pcb=False)."""
        params_sdars = {
            'patch_L': 29.95,
            'patch_W': 29.95,
            'sub_h': 1.52,
            'eps_r': 4.3,
            'design_freq_ghz': 2.3325,
            'port_impedance': 50.0,
        }

        # 1. Kompaktní ořez (tight_pcb=True, výchozí)
        geom_tight = get_model4_kicad_geometry(params_sdars, tight_pcb=True)
        info = geom_tight.routing_info

        self.assertTrue(geom_tight.tight_pcb)
        # Efektivní rozměry jsou výrazně menší než plný symetrický substrát (~40 % úspora plochy)
        self.assertLess(geom_tight.W_sub, info['W_sub'])
        self.assertLess(geom_tight.L_sub, info['L_sub'])

        # Kontrola kompaktních rozměrů pro ~30 mm patch: W_sub ~ 73.4 mm
        self.assertAlmostEqual(geom_tight.W_sub, 73.40, delta=0.5)
        self.assertTrue(67.0 <= geom_tight.L_sub <= 77.0)

        # Kontrola přesných vztahů dle analytických vzorců
        expected_w = info['cad_x_max'] - info['cad_x_min']
        expected_l = info['cad_y_max'] - info['cad_y_min']
        self.assertAlmostEqual(geom_tight.W_sub, expected_w, places=4)
        self.assertAlmostEqual(geom_tight.L_sub, expected_l, places=4)

        self.assertAlmostEqual(info['cad_x_min'], info['x_port'], places=4)
        self.assertAlmostEqual(info['cad_x_max'], 29.95 / 2.0 + 10.0, places=4)
        self.assertAlmostEqual(info['cad_y_min'], info['y_bot'] - 5.0, places=4)
        self.assertAlmostEqual(info['cad_y_max'], 29.95 / 2.0 + 10.0, places=4)

        # Edge.Cuts obdélník v KiCad souřadnicích
        x_min, y_min, x_max, y_max = geom_tight.edge_cuts_rect
        self.assertAlmostEqual(x_max - x_min, geom_tight.W_sub, places=4)
        self.assertAlmostEqual(y_max - y_min, geom_tight.L_sub, places=4)
        self.assertAlmostEqual(x_min, 25.0, places=4)
        self.assertAlmostEqual(y_min, 25.0, places=4)

        # Kontrola spodního GND polygonu na B.Cu: přesně pokrývá Edge.Cuts
        b_cu_poly = geom_tight.gnd_polygon_bottom
        b_xs = [p[0] for p in b_cu_poly]
        b_ys = [p[1] for p in b_cu_poly]
        self.assertAlmostEqual(min(b_xs), x_min, places=4)
        self.assertAlmostEqual(max(b_xs), x_max, places=4)
        self.assertAlmostEqual(min(b_ys), y_min, places=4)
        self.assertAlmostEqual(max(b_ys), y_max, places=4)

        # 2. Plný symetrický režim (tight_pcb=False) pro zpětnou kompatibilitu
        geom_full = get_model4_kicad_geometry(params_sdars, tight_pcb=False)
        self.assertFalse(geom_full.tight_pcb)
        self.assertAlmostEqual(geom_full.W_sub, info['W_sub'], places=4)
        self.assertAlmostEqual(geom_full.L_sub, info['L_sub'], places=4)
        self.assertGreaterEqual(geom_full.W_sub, 95.0)
        self.assertGreaterEqual(geom_full.L_sub, 93.0)

        fx_min, fy_min, fx_max, fy_max = geom_full.edge_cuts_rect
        self.assertAlmostEqual(fx_max - fx_min, info['W_sub'], places=4)
        self.assertAlmostEqual(fy_max - fy_min, info['L_sub'], places=4)

        # 3. Volitelná konfigurace okrajů (margin_right, margin_top, margin_bottom)
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
        """Ověření zpětné kompatibility SMA G-S-G pro výchozí substrát h=1.52 mm, eps_r=4.3."""
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

        # Prokovy na X offsetech [1.0, 2.0, 3.0] od x_min a Y vycentrovaném na y_T +- sma_gnd_center_y
        x_min, _, _, _ = geom.edge_cuts_rect
        y_T_kicad = geom.origin_y - info['y_T']
        via_x_offsets = sorted({round(v['x'] - x_min, 4) for v in geom.vias})
        self.assertEqual(via_x_offsets, [1.0, 2.0, 3.0])

        for v in geom.vias:
            self.assertAlmostEqual(abs(v['y'] - y_T_kicad), info['sma_gnd_center_y'], places=3)

    def test_sma_gsg_wide_50ohm_line_no_short_and_mask_coverage(self):
        """Ověření SMA G-S-G pro tlustší desku / nižší eps_r (h=2.0, eps_r=3.5 -> w_50 > 4.4 mm)."""
        params = {
            'patch_L': 28.8,
            'patch_W': 28.8,
            'sub_h': 2.0,
            'eps_r': 3.5,
            'mask_clearance': 0.30,
        }
        geom = get_model4_kicad_geometry(params, is_footprint=False)
        info = geom.routing_info

        # Ověř, že w_50 > 4.4 mm (dříve by došlo ke zkratu na pevné hranici +-2.19 mm)
        self.assertGreater(info['w_50'], 4.4)
        self.assertGreater(info['w_50'] / 2.0, 2.19)

        y_T_kicad = geom.origin_y - info['y_T']
        x_min, _, _, _ = geom.edge_cuts_rect

        # 50 Ohm přívod u portu (rf_polygons[5] = t_junc_kicad)
        t_junc_poly = geom.rf_polygons[5]
        port_pts = [p for p in t_junc_poly if abs(p[0] - x_min) < 1e-4]
        self.assertEqual(len(port_pts), 2)
        rf_y_min = min(p[1] for p in port_pts)
        rf_y_max = max(p[1] for p in port_pts)
        self.assertAlmostEqual(rf_y_max - rf_y_min, info['w_50'], places=4)

        # Horní a spodní GND plošky na F.Cu (v KiCadu: menší Y = CAD +Y, větší Y = CAD -Y)
        gnd_top_poly, gnd_bot_poly = geom.gnd_polygons_top
        gnd_top_ys = [p[1] for p in gnd_top_poly]
        gnd_bot_ys = [p[1] for p in gnd_bot_poly]

        # Žádný překryv RF a GND a přesná mezera sma_gap = 0.70 mm na obou stranách
        gap_upper = rf_y_min - max(gnd_top_ys)
        gap_lower = min(gnd_bot_ys) - rf_y_max
        self.assertGreater(gap_upper, 0.0)
        self.assertGreater(gap_lower, 0.0)
        self.assertAlmostEqual(gap_upper, SMA_GAP, places=4)
        self.assertAlmostEqual(gap_lower, SMA_GAP, places=4)

        # Všechny prokovy leží přesně uprostřed (v ose Y) a uvnitř (v ose X) příslušných GND plošek
        top_center_y = 0.5 * (min(gnd_top_ys) + max(gnd_top_ys))
        bot_center_y = 0.5 * (min(gnd_bot_ys) + max(gnd_bot_ys))
        self.assertEqual(len(geom.vias), 6)
        for v in geom.vias:
            self.assertGreaterEqual(v['x'], x_min + 0.5 - 1e-4)
            self.assertLessEqual(v['x'], x_min + info['sma_pad_len'] - 0.5 + 1e-4)
            dist_to_nearest_center = min(abs(v['y'] - top_center_y), abs(v['y'] - bot_center_y))
            self.assertAlmostEqual(dist_to_nearest_center, 0.0, places=4)

        # Maska F.Mask i B.Mask se zvětšila (> 8.0 mm) a bezpečně pokrývá vnější hrany GND plošek
        self.assertGreater(info['sma_mask_half_h'], 4.0)
        expected_half_h = info['sma_gnd_outer'] + 0.31
        self.assertAlmostEqual(info['sma_mask_half_h'], expected_half_h, places=4)

        for mask_poly in (geom.mask_openings[0], geom.mask_openings_bottom[0]):
            m_xs = [p[0] for p in mask_poly]
            m_ys = [p[1] for p in mask_poly]
            self.assertAlmostEqual(min(m_xs), x_min, places=4)
            self.assertAlmostEqual(max(m_xs) - min(m_xs), info['sma_mask_len'], places=4)
            self.assertAlmostEqual(max(m_ys) - min(m_ys), 2.0 * info['sma_mask_half_h'], places=4)
            self.assertLessEqual(min(m_ys), min(gnd_top_ys) - 0.30 + 1e-4)
            self.assertGreaterEqual(max(m_ys), max(gnd_bot_ys) + 0.30 - 1e-4)
            self.assertAlmostEqual(0.5 * (min(m_ys) + max(m_ys)), y_T_kicad, places=4)

    def test_sma_gsg_thin_substrate(self):
        """Ověření SMA G-S-G pro tenčí desku (h=0.8 mm, eps_r=4.4 -> úzké w_50)."""
        params = {'patch_L': 28.8, 'patch_W': 28.8, 'sub_h': 0.8, 'eps_r': 4.4}
        geom = get_model4_kicad_geometry(params, is_footprint=False)
        info = geom.routing_info

        self.assertLess(info['w_50'], 2.0)
        self.assertAlmostEqual(info['sma_gnd_inner'], info['w_50'] / 2.0 + SMA_GAP, places=6)
        self.assertAlmostEqual(info['sma_gnd_outer'], info['sma_gnd_inner'] + SMA_PAD_W, places=6)
        # Pro užší vedení zůstává minimální maska 4.0 x 8.0 mm pro tělo SMA konektoru
        self.assertAlmostEqual(info['sma_mask_len'], 4.0, places=6)
        self.assertAlmostEqual(info['sma_mask_half_h'], 4.0, places=6)

        y_T_kicad = geom.origin_y - info['y_T']
        self.assertAlmostEqual(abs(geom.sma_top_pad_center[1] - y_T_kicad), info['sma_gnd_center_y'], places=4)
        self.assertAlmostEqual(abs(geom.sma_bot_pad_center[1] - y_T_kicad), info['sma_gnd_center_y'], places=4)

    def test_sma_custom_params_and_validation(self):
        """Ověření vlastního nastavení SMA parametrů, aliasů, rozvržení prokovů a validace."""
        base = {'patch_L': 28.8, 'patch_W': 28.8, 'sub_h': 1.52, 'eps_r': 4.3}

        # 1. Delší a širší SMA plošky s větší mezerou
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

        # Všechny prokovy leží bezpečně v [0.5, sma_pad_len - 0.5]
        via_x_offsets = sorted({round(v['x'] - x_min, 4) for v in geom.vias})
        self.assertEqual(len(via_x_offsets), 3)
        for off in via_x_offsets:
            self.assertGreaterEqual(off, 0.5 - 1e-4)
            self.assertLessEqual(off, 5.0 - 0.5 + 1e-4)

        # 2. Kratší SMA plošky (např. 2.4 mm) a aliasy
        short_alias = dict(base, sma_gsg_gap=0.55, sma_gnd_pad_len=2.4, sma_gnd_pad_w=1.2)
        geom_short = get_model4_kicad_geometry(short_alias, is_footprint=False)
        x_min_s, _, _, _ = geom_short.edge_cuts_rect
        via_x_short = sorted({round(v['x'] - x_min_s, 4) for v in geom_short.vias})
        self.assertEqual(len(via_x_short), 3)
        for off in via_x_short:
            self.assertGreaterEqual(off, 0.5 - 1e-4)
            self.assertLessEqual(off, 2.4 - 0.5 + 1e-4)

        # 3. Validace neplatných hodnot (<= 0 vyhodí ValueError)
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
    """Testy generování KiCad 10 S-výrazů v kicad_generator.py."""

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
        """Ověření vygenerování validní KiCad 10 desky plošných spojů."""
        pcb_file = os.path.join(self.temp_dir.name, "test_antenna.kicad_pcb")
        res = generate_kicad_pcb(self.params, pcb_file)

        self.assertTrue(os.path.exists(pcb_file))
        self.assertGreater(res['file_size_bytes'], 5000)
        self.assertEqual(res['vias_count'], 6)
        self.assertEqual(res['rf_polygons_count'], 6)
        self.assertEqual(res['mask_openings_count'], 7)
        self.assertEqual(res['mask_openings_bottom_count'], 1)

        with open(pcb_file, "r", encoding="utf-8") as f:
            content = f.read()

        # Kontrola klíčových KiCad 10 prvků
        self.assertIn('(kicad_pcb', content)
        self.assertIn('(version 20260206)', content)
        self.assertIn('(generator_version "10.0")', content)
        self.assertIn('(thickness 1.520)', content)
        self.assertIn('(embedded_fonts no)', content)

        # Vrstvy (kanonické číslování KiCad 10)
        self.assertIn('(0 "F.Cu" signal)', content)
        self.assertIn('(2 "B.Cu" power)', content)
        self.assertIn('(1 "F.Mask" user)', content)
        self.assertIn('(3 "B.Mask" user)', content)
        self.assertIn('(17 "Dwgs.User" user "User.Drawings")', content)
        self.assertIn('(19 "Cmts.User" user "User.Comments")', content)
        self.assertIn('(21 "Eco1.User" user "User.Eco1")', content)
        self.assertIn('(23 "Eco2.User" user "User.Eco2")', content)
        self.assertIn('(25 "Edge.Cuts" user)', content)

        # Zóny (KiCad 10 používá jmenné sítě a (layer "...") i ve filled_polygon)
        self.assertIn('(net "RF_IN")', content)
        self.assertIn('(layer "F.Cu")', content)
        self.assertIn('(net "GND")', content)
        self.assertIn('(layer "B.Cu")', content)
        self.assertIn('(filled_polygon\n      (layer "F.Cu")', content)
        self.assertIn('(filled_polygon\n      (layer "B.Cu")', content)

        # Prokovy
        self.assertIn('(via (at ', content)
        self.assertIn('(size 0.6000) (drill 0.3000) (layers "F.Cu" "B.Cu") (net "GND")', content)
        self.assertEqual(content.count('(size 0.6000) (drill 0.3000)'), 6)

        # Edge.Cuts obdélník
        self.assertIn('(layer "Edge.Cuts")', content)

        # F.Mask a B.Mask otevření
        self.assertIn('(layer "F.Mask")', content)
        self.assertIn('(layer "B.Mask")', content)
        self.assertIn('(fill yes) (layer "B.Mask")', content)

    def test_generate_kicad_footprint(self):
        """Ověření vygenerování validního knihovního pouzdra (.kicad_mod)."""
        fp_file = os.path.join(self.temp_dir.name, "Antenna_Model4_LHCP.kicad_mod")
        res = generate_kicad_footprint(self.params, fp_file)

        self.assertTrue(os.path.exists(fp_file))
        self.assertGreater(res['file_size_bytes'], 3000)

        with open(fp_file, "r", encoding="utf-8") as f:
            content = f.read()

        # Hlavička footprintu KiCad 10
        self.assertIn('(footprint "Antenna_Model4_LHCP"', content)
        self.assertIn('(version 20260206)', content)
        self.assertIn('(generator_version "10.0")', content)
        self.assertIn('(duplicate_pad_numbers_are_jumpers no)', content)
        self.assertIn('(embedded_fonts no)', content)

        # Kotevní bod (0, 0) uprostřed vyzařovače v custom padu 1
        self.assertIn('(pad "1" smd custom (at 0 0) (size 1 1) (layers "F.Cu" "F.Mask")', content)
        self.assertIn('(zone_connect 2)', content)
        self.assertIn('(options (clearance outline) (anchor rect))', content)
        self.assertIn('(primitives', content)
        self.assertIn('(gr_poly', content)
        self.assertIn('(width 0) (fill yes)', content)

        # Pady 2 a 3 pro SMA GND
        self.assertIn('(pad "2" smd rect (at ', content)
        self.assertIn('(pad "3" smd rect (at ', content)
        self.assertIn('(size 3.5000 1.5000) (layers "F.Cu" "F.Mask")', content)

        # Otevření masky F.Mask a B.Mask nad SMA
        self.assertIn('(fill yes) (layer "F.Mask")', content)
        self.assertIn('(fill yes) (layer "B.Mask")', content)
        self.assertIn('(solder_mask_margin 0.3000)', content)

        # Obrys na F.Fab a F.CrtYd
        self.assertIn('(fill no) (layer "F.Fab")', content)
        self.assertIn('(fill no) (layer "F.CrtYd")', content)

    def test_generate_kicad_pcb_tight_and_full(self):
        """Ověření vygenerování PCB v kompaktním i plném symetrickém režimu."""
        # 1. Kompaktní režim
        pcb_tight = os.path.join(self.temp_dir.name, "tight.kicad_pcb")
        res_tight = generate_kicad_pcb(self.params, pcb_tight, tight_pcb=True)
        self.assertTrue(res_tight['tight_pcb'])
        self.assertLess(res_tight['W_sub'], res_tight['routing_info']['W_sub'])
        self.assertLess(res_tight['L_sub'], res_tight['routing_info']['L_sub'])

        with open(pcb_tight, "r", encoding="utf-8") as f:
            content_tight = f.read()
        self.assertIn('(gr_line (start 25.0000 25.0000)', content_tight)

        # 2. Plný symetrický režim
        pcb_full = os.path.join(self.temp_dir.name, "full.kicad_pcb")
        res_full = generate_kicad_pcb(self.params, pcb_full, tight_pcb=False)
        self.assertFalse(res_full['tight_pcb'])
        self.assertAlmostEqual(res_full['W_sub'], res_full['routing_info']['W_sub'], places=4)
        self.assertAlmostEqual(res_full['L_sub'], res_full['routing_info']['L_sub'], places=4)

        with open(pcb_full, "r", encoding="utf-8") as f:
            content_full = f.read()
        self.assertIn(f'(end {25.0 + res_full["W_sub"]:.4f}', content_full)

    def test_generate_kicad_pcb_and_footprint_wide_substrate_sma(self):
        """Ověření dynamických SMA maskových otvorů F.Mask/B.Mask a GND padů v .kicad_pcb i .kicad_mod."""
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

        # Kontrola footprintu (.kicad_mod): pady 2, 3 mají rozměr 4.20 x 1.60 a masky F.Mask/B.Mask odpovídají rozměrům
        with open(fp_file, "r", encoding="utf-8") as f:
            fp_content = f.read()
        self.assertIn('(size 4.2000 1.6000) (layers "F.Cu" "F.Mask")', fp_content)

        for layer in ("F.Mask", "B.Mask"):
            pattern = (
                r'\(fp_rect \(start ([\-\d\.]+) ([\-\d\.]+)\) \(end ([\-\d\.]+) ([\-\d\.]+)\) '
                r'\(stroke \(width 0\) \(type solid\)\) \(fill yes\) \(layer "' + re.escape(layer) + r'"\)'
            )
            m = re.search(pattern, fp_content)
            self.assertIsNotNone(m, f"Chybí SMA fp_rect na vrstvě {layer}")
            sx, sy, ex, ey = (float(m.group(i)) for i in range(1, 5))
            self.assertAlmostEqual(ex - sx, expected_mask_len, places=3)
            self.assertAlmostEqual(ey - sy, 2.0 * expected_half_h, places=3)

        # Kontrola PCB (.kicad_pcb): B.Mask polygon má přesně dynamický rozměr
        with open(pcb_file, "r", encoding="utf-8") as f:
            pcb_content = f.read()
        self.assertIn('(thickness 2.000)', pcb_content)
        self.assertEqual(res_pcb['vias_count'], 6)
        b_mask_block = re.search(
            r'\(gr_poly\n\s+\(pts\n((?:\s+\(xy [^\n]+\n)+)\s+\)\n'
            r'\s+\(stroke \(width 0\) \(type solid\)\) \(fill yes\) \(layer "B\.Mask"\)',
            pcb_content,
        )
        self.assertIsNotNone(b_mask_block, "Chybí B.Mask SMA polygon v .kicad_pcb")
        coords = [
            (float(x), float(y))
            for x, y in re.findall(r'\(xy ([\-\d\.]+) ([\-\d\.]+)\)', b_mask_block.group(1))
        ]
        xs = [c[0] for c in coords]
        ys = [c[1] for c in coords]
        self.assertAlmostEqual(max(xs) - min(xs), expected_mask_len, places=3)
        self.assertAlmostEqual(max(ys) - min(ys), 2.0 * expected_half_h, places=3)


class TestExportCli(unittest.TestCase):
    """Testy CLI skriptu scripts/export_kicad.py."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_cli_export_all(self):
        """Spuštění CLI skriptu s volbou --all do dočasné složky."""
        cmd = [
            sys.executable,
            os.path.join(SCRIPTS_DIR, "export_kicad.py"),
            "--output-dir", self.temp_dir.name,
            "--all",
            "--patch-l", "29.81",
            "--delta-l", "18.66",
        ]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(proc.returncode, 0, f"Skript selhal s chybou:\n{proc.stderr}")

        pcb_file = os.path.join(self.temp_dir.name, "antenna_model4.kicad_pcb")
        fp_file = os.path.join(self.temp_dir.name, "Antenna_Model4_LHCP.kicad_mod")

        self.assertTrue(os.path.exists(pcb_file))
        self.assertTrue(os.path.exists(fp_file))
        self.assertIn("Export úspěšně dokončen", proc.stdout)

    def test_cli_export_pcb_only(self):
        """Spuštění CLI skriptu pouze pro DPS (--pcb)."""
        cmd = [
            sys.executable,
            os.path.join(SCRIPTS_DIR, "export_kicad.py"),
            "--output-dir", self.temp_dir.name,
            "--pcb",
        ]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(proc.returncode, 0)

        pcb_file = os.path.join(self.temp_dir.name, "antenna_model4.kicad_pcb")
        fp_file = os.path.join(self.temp_dir.name, "Antenna_Model4_LHCP.kicad_mod")

        self.assertTrue(os.path.exists(pcb_file))
        self.assertFalse(os.path.exists(fp_file))

    def test_cli_export_with_mask_clearance(self):
        """Spuštění CLI skriptu s volitelným odsazením masky --mask-clearance."""
        cmd = [
            sys.executable,
            os.path.join(SCRIPTS_DIR, "export_kicad.py"),
            "--output-dir", self.temp_dir.name,
            "--all",
            "--mask-clearance", "0.40",
        ]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("Odsazení nepájivé masky (clearance):0.40 mm", proc.stdout)

        fp_file = os.path.join(self.temp_dir.name, "Antenna_Model4_LHCP.kicad_mod")
        with open(fp_file, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn('(solder_mask_margin 0.4000)', content)
        self.assertIn('(layer "B.Mask")', content)

    def test_cli_tight_pcb_options(self):
        """Ověření CLI přepínačů pro ořez desky: --tight-pcb, --no-tight-pcb, --crop-pcb, --full-pcb."""
        # 1. Výchozí / explicitní --tight-pcb
        cmd_tight = [
            sys.executable,
            os.path.join(SCRIPTS_DIR, "export_kicad.py"),
            "--output-dir", os.path.join(self.temp_dir.name, "tight"),
            "--tight-pcb",
            "--patch-l", "29.95",
        ]
        proc_tight = subprocess.run(cmd_tight, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(proc_tight.returncode, 0)
        self.assertIn("Kompaktní / oříznutý (tight_pcb=True)", proc_tight.stdout)
        self.assertIn("73.40 mm", proc_tight.stdout)
        self.assertIn("úspora plochy", proc_tight.stdout)

        # 2. Plný symetrický režim --no-tight-pcb
        cmd_full = [
            sys.executable,
            os.path.join(SCRIPTS_DIR, "export_kicad.py"),
            "--output-dir", os.path.join(self.temp_dir.name, "full"),
            "--no-tight-pcb",
            "--patch-l", "29.95",
        ]
        proc_full = subprocess.run(cmd_full, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(proc_full.returncode, 0)
        self.assertIn("Plný symetrický (tight_pcb=False)", proc_full.stdout)
        self.assertIn("96.84 mm", proc_full.stdout)

        # 3. Aliases --crop-pcb a --full-pcb
        cmd_alias = [
            sys.executable,
            os.path.join(SCRIPTS_DIR, "export_kicad.py"),
            "--output-dir", os.path.join(self.temp_dir.name, "alias"),
            "--crop-pcb",
            "--margin-right", "12.0",
        ]
        proc_alias = subprocess.run(cmd_alias, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(proc_alias.returncode, 0)
        self.assertIn("Kompaktní / oříznutý", proc_alias.stdout)

    def test_cli_sma_options_and_env_override(self):
        """Ověření CLI přepínačů --sma-gap, --sma-pad-len, --sma-pad-w a env proměnných."""
        # 1. CLI přepisy včetně širšího substrátu
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
        proc_cli = subprocess.run(cmd_cli, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(proc_cli.returncode, 0, f"CLI selhalo:\n{proc_cli.stderr}")
        self.assertIn("gap=0.85 mm", proc_cli.stdout)
        self.assertIn("pad=4.50x1.80 mm", proc_cli.stdout)

        fp_file = os.path.join(self.temp_dir.name, "cli_sma", "Antenna_Model4_LHCP.kicad_mod")
        with open(fp_file, "r", encoding="utf-8") as f:
            fp_content = f.read()
        self.assertIn('(size 4.5000 1.8000) (layers "F.Cu" "F.Mask")', fp_content)

        # 2. Načtení z env proměnných SMA_GAP, SMA_PAD_LEN, SMA_PAD_W
        env = os.environ.copy()
        env.update({
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
        self.assertEqual(proc_env.returncode, 0, f"CLI s env selhalo:\n{proc_env.stderr}")
        self.assertIn("gap=0.60 mm", proc_env.stdout)
        self.assertIn("pad=4.00x1.60 mm", proc_env.stdout)

        # 3. Neplatná hodnota --sma-gap <= 0 selže s chybou
        cmd_bad = [
            sys.executable,
            os.path.join(SCRIPTS_DIR, "export_kicad.py"),
            "--output-dir", os.path.join(self.temp_dir.name, "bad_sma"),
            "--pcb",
            "--sma-gap", "0",
        ]
        proc_bad = subprocess.run(cmd_bad, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertNotEqual(proc_bad.returncode, 0)
        self.assertIn("ValueError", proc_bad.stderr)


if __name__ == "__main__":
    unittest.main()
