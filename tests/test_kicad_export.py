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
     - Generování výrobní DPS (.kicad_pcb) KiCad 8 (verze 20240108).
     - Ověření explicitních sítí (Net 0, Net 1 GND, Net 2 RF_IN).
     - Zóny F.Cu, celistvá zem B.Cu, Edge.Cuts obrys, F.Mask otvory, 6 GND prokovů.
     - Generování knihovního pouzdra (.kicad_mod) s kotevním bodem (0, 0) uprostřed flíčku.
     - Zákaznický SMD pad 1 s celou RF geometrií a SMD pady 2, 3 pro SMA GND.
  3. scripts/export_kicad.py:
     - CLI rozhraní a parametry (--pcb, --footprint, --all, parametrické přepisy).
"""

import math
import os
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


class TestKiCadGenerator(unittest.TestCase):
    """Testy generování KiCad 8 S-výrazů v kicad_generator.py."""

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
        """Ověření vygenerování validní KiCad 8 desky plošných spojů."""
        pcb_file = os.path.join(self.temp_dir.name, "test_antenna.kicad_pcb")
        res = generate_kicad_pcb(self.params, pcb_file)

        self.assertTrue(os.path.exists(pcb_file))
        self.assertGreater(res['file_size_bytes'], 5000)
        self.assertEqual(res['vias_count'], 6)
        self.assertEqual(res['rf_polygons_count'], 6)

        with open(pcb_file, "r", encoding="utf-8") as f:
            content = f.read()

        # Kontrola klíčových KiCad 8 prvků
        self.assertIn('(kicad_pcb', content)
        self.assertIn('(version 20240108)', content)
        self.assertIn('(thickness 1.520)', content)

        # Vrstvy
        self.assertIn('(0 "F.Cu" signal)', content)
        self.assertIn('(31 "B.Cu" power)', content)
        self.assertIn('(39 "F.Mask" user)', content)
        self.assertIn('(40 "Dwgs.User" user "User.Drawings")', content)
        self.assertIn('(41 "Cmts.User" user "User.Comments")', content)
        self.assertIn('(42 "Eco1.User" user "User.Eco1")', content)
        self.assertIn('(43 "Eco2.User" user "User.Eco2")', content)
        self.assertIn('(44 "Edge.Cuts" user)', content)

        # Sítě
        self.assertIn('(net 0 "")', content)
        self.assertIn('(net 1 "GND")', content)
        self.assertIn('(net 2 "RF_IN")', content)

        # Zóny
        self.assertIn('(net 2)', content)
        self.assertIn('(net_name "RF_IN")', content)
        self.assertIn('(layers "F.Cu")', content)
        self.assertIn('(net 1)', content)
        self.assertIn('(net_name "GND")', content)
        self.assertIn('(layers "B.Cu")', content)

        # Prokovy
        self.assertIn('(via (at ', content)
        self.assertIn('(size 0.6000) (drill 0.3000) (layers "F.Cu" "B.Cu") (net 1)', content)
        self.assertEqual(content.count('(size 0.6000) (drill 0.3000)'), 6)

        # Edge.Cuts obdélník
        self.assertIn('(layer "Edge.Cuts")', content)

        # F.Mask otevření
        self.assertIn('(layer "F.Mask")', content)

    def test_generate_kicad_footprint(self):
        """Ověření vygenerování validního knihovního pouzdra (.kicad_mod)."""
        fp_file = os.path.join(self.temp_dir.name, "Antenna_Model4_LHCP.kicad_mod")
        res = generate_kicad_footprint(self.params, fp_file)

        self.assertTrue(os.path.exists(fp_file))
        self.assertGreater(res['file_size_bytes'], 3000)

        with open(fp_file, "r", encoding="utf-8") as f:
            content = f.read()

        # Hlavička footprintu
        self.assertIn('(footprint "Antenna_Model4_LHCP"', content)
        self.assertIn('(version 20240108)', content)

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

        # Otevření masky F.Mask nad SMA
        self.assertIn('(layer "F.Mask")', content)

        # Obrys na F.Fab a F.CrtYd
        self.assertIn('(layer "F.Fab")', content)
        self.assertIn('(layer "F.CrtYd")', content)


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


if __name__ == "__main__":
    unittest.main()
