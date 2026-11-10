"""
sweep.py - Štíhlý dispečer parametrického sweepu mikropáskové antény.
Podle proměnné ANTENNA_MODEL v .env (nebo přepínače --model v CLI) automaticky deleguje:
  - ANTENNA_MODEL=1 -> src/sweep_model1.py (Původní T-dělič, 1 port, 50 Ohm)
  - ANTENNA_MODEL=2 -> src/sweep_model2.py (Nový dvouportový model, 100 Ohm LHCP)
  - ANTENNA_MODEL=3 -> src/sweep_model3.py (Hybridní dvoustupňové přizpůsobení)
"""

import os
import sys
import argparse

# Zajistíme dostupnost složek src a scripts pro importy
src_dir = os.path.dirname(os.path.abspath(__file__))
scripts_dir = os.path.abspath(os.path.join(src_dir, "..", "scripts"))
for d in (src_dir, scripts_dir):
    if d not in sys.path:
        sys.path.append(d)

from postpro_utils import load_env
load_env()


def run_sweep(**kwargs):
    """Univerzální rozhraní pro spuštění sweepu zvoleného modelu antény."""
    model_version = int(kwargs.get('antenna_model') or os.getenv("ANTENNA_MODEL", "1"))
    
    if model_version == 3:
        from sweep_model3 import run_sweep_model3
        return run_sweep_model3(**kwargs)
    elif model_version == 2:
        from sweep_model2 import run_sweep_model2
        return run_sweep_model2(**kwargs)
    else:
        from sweep_model1 import run_sweep_model1
        return run_sweep_model1(**kwargs)


if __name__ == "__main__":
    # Rychlá předběžná detekce --model pro směrování
    env_model = int(os.getenv("ANTENNA_MODEL", "1"))
    
    parser = argparse.ArgumentParser(
        description="Dispečer parametrického sweepu antény (Model 1: T-dělič / Model 2: 2-port LHCP / Model 3: Hybridní přizpůsobení)",
        add_help=False,
        allow_abbrev=False
    )
    parser.add_argument("--model", type=int, choices=[1, 2, 3], default=env_model, dest="antenna_model",
                        help="Verze modelu antény (1: T-dělič, 2: dvouportový LHCP, 3: hybridní přizpůsobení). Výchozí z ANTENNA_MODEL.")
    known_args, remaining_argv = parser.parse_known_args()

    selected_model = known_args.antenna_model

    if selected_model == 3:
        from sweep_model3 import run_sweep_model3
        parser_m3 = argparse.ArgumentParser(description="Parametrický sweep Modelu 3 (Hybridní dvoustupňové přizpůsobení)")
        parser_m3.add_argument("--sweep-target", choices=["inset", "y0", "trans_w", "w_t", "trans_l", "l_t", "delta_l", "patch_l"], default=None,
                                help="Cíl sweepování: 'inset' (y0, výchozí), 'trans_w' (w_T), 'trans_l' (l_T), 'delta_l', 'patch_l'")
        parser_m3.add_argument("--mode", choices=["symmetric", "single_fixed", "grid", "manual"], default=None)
        parser_m3.add_argument("--pairs", "--manual-pairs", type=str, nargs="+", default=None, dest="manual_pairs")
        parser_m3.add_argument("--insets", type=float, nargs="+", default=None)
        parser_m3.add_argument("--insets-b", type=float, nargs="+", default=None)
        parser_m3.add_argument("--insets-l", type=float, nargs="+", default=None)
        parser_m3.add_argument("--fixed-name", choices=["inset_b", "inset_l"], default=None)
        parser_m3.add_argument("--fixed-val", type=float, default=None)
        parser_m3.add_argument("--trans-w-list", "--w-t-list", type=float, nargs="+", default=None, dest="trans_w_list")
        parser_m3.add_argument("--trans-l-list", "--l-t-list", type=float, nargs="+", default=None, dest="trans_l_list")
        parser_m3.add_argument("--delta-l", "--sweep-delta-l", type=float, nargs="+", default=None, dest="delta_l")
        parser_m3.add_argument("--patch-lengths", type=float, nargs="+", default=None, dest="patch_lengths")
        parser_m3.add_argument("--trans-w", "--w-t", type=float, default=None, dest="trans_w")
        parser_m3.add_argument("--trans-l", "--l-t", type=float, default=None, dest="trans_l")
        parser_m3.add_argument("--inset-b", type=float, default=None, dest="inset_b")
        parser_m3.add_argument("--inset-l", type=float, default=None, dest="inset_l")
        parser_m3.add_argument("--feed-delta-l", type=float, default=None, dest="feed_delta_l")
        parser_m3.add_argument("--patch-l", type=float, default=None, dest="patch_l")
        parser_m3.add_argument("--patch-w", type=float, default=None, dest="patch_w")
        parser_m3.add_argument("--freq-min", type=float, default=None, dest="freq_min")
        parser_m3.add_argument("--freq-max", type=float, default=None, dest="freq_max")
        parser_m3.add_argument("--freq-step", type=float, default=None, dest="freq_step")
        parser_m3.add_argument("--amr-its", type=int, default=None, dest="amr_max_its")
        parser_m3.add_argument("--linear-tol", type=float, default=None, dest="linear_tol")
        parser_m3.add_argument("--linear-its", type=int, default=None, dest="linear_max_its")
        parser_m3.add_argument("--farfield-nsample", type=int, default=None, dest="farfield_nsample")
        parser_m3.add_argument("--no-export", dest="export_each", action="store_false", default=None)
        parser_m3.add_argument("--skip-simulation", "--no-docker", dest="skip_simulation", action="store_true", default=False)
        parser_m3.add_argument("--driven-port", choices=["all", "1", "2"], default=None)
        m3_args = parser_m3.parse_args(remaining_argv)

        run_sweep_model3(
            mode=m3_args.mode,
            sweep_target=m3_args.sweep_target,
            insets=m3_args.insets,
            insets_b=m3_args.insets_b,
            insets_l=m3_args.insets_l,
            fixed_name=m3_args.fixed_name,
            fixed_val=m3_args.fixed_val,
            manual_pairs=m3_args.manual_pairs,
            trans_w_list=m3_args.trans_w_list,
            trans_l_list=m3_args.trans_l_list,
            delta_l=m3_args.delta_l,
            patch_lengths=m3_args.patch_lengths,
            trans_w=m3_args.trans_w,
            trans_l=m3_args.trans_l,
            inset_b=m3_args.inset_b,
            inset_l=m3_args.inset_l,
            feed_delta_l=m3_args.feed_delta_l,
            patch_l=m3_args.patch_l,
            patch_w=m3_args.patch_w,
            freq_min=m3_args.freq_min,
            freq_max=m3_args.freq_max,
            freq_step=m3_args.freq_step,
            amr_max_its=m3_args.amr_max_its,
            farfield_nsample=m3_args.farfield_nsample,
            linear_tol=m3_args.linear_tol,
            linear_max_its=m3_args.linear_max_its,
            export_each=m3_args.export_each,
            skip_simulation=m3_args.skip_simulation,
            driven_port=m3_args.driven_port,
        )

    elif selected_model == 2:
        from sweep_model2 import run_sweep_model2
        sys.argv = [sys.argv[0]] + remaining_argv
        parser_m2 = argparse.ArgumentParser(description="Parametrický sweep Modelu 2 (Dvouportový LHCP)")
        parser_m2.add_argument("--sweep-target", choices=["inset", "patch_l", "feed_len_b", "feed_len_l", "feed_delta_l", "delta_l", "feed_lens"], default=None,
                                help="Cíl sweepování: 'inset' (výchozí), 'patch_l', 'delta_l', 'feed_len_b', 'feed_len_l', 'feed_lens'")
        parser_m2.add_argument("--mode", choices=["symmetric", "single_fixed", "grid", "manual"], default=None)
        parser_m2.add_argument("--pairs", "--manual-pairs", type=str, nargs="+", default=None, dest="manual_pairs",
                               help="Manuálně definované dvojice zanoření pro Model 2")
        parser_m2.add_argument("--insets", type=float, nargs="+", default=None)
        parser_m2.add_argument("--insets-b", type=float, nargs="+", default=None)
        parser_m2.add_argument("--insets-l", type=float, nargs="+", default=None)
        parser_m2.add_argument("--fixed-name", choices=["inset_b", "inset_l"], default=None)
        parser_m2.add_argument("--fixed-val", type=float, default=None)

        # Argumenty pro sweepování délky flíčku
        parser_m2.add_argument("--patch-lengths", type=float, nargs="+", default=None, dest="patch_lengths",
                                help="Hodnoty délky flíčku patch_L v mm pro sweepování")

        # Argumenty pro sweepování a fixaci délek napaječů
        parser_m2.add_argument("--delta-l", "--sweep-delta-l", type=float, nargs="+", default=None, dest="delta_l",
                                help="Hodnoty fázovacího úseku Delta L v mm pro sweepování")
        parser_m2.add_argument("--feed-delta-l", type=float, default=None, dest="feed_delta_l",
                                help="Fixní hodnota rozdílu délek přívodů Delta L v mm")
        parser_m2.add_argument("--feed-lens-b", type=float, nargs="+", default=None, dest="feed_lens_b",
                                help="Hodnoty délky spodního přívodu pro sweepování")
        parser_m2.add_argument("--feed-lens-l", type=float, nargs="+", default=None, dest="feed_lens_l",
                                help="Hodnoty délky levého přívodu pro sweepování")
        parser_m2.add_argument("--feed-len-b", type=float, default=None, dest="feed_len_b",
                                help="Fixní délka spodního přívodu v mm")
        parser_m2.add_argument("--feed-len-l", type=float, default=None, dest="feed_len_l",
                                help="Fixní délka levého přívodu v mm")
        parser_m2.add_argument("--inset-b", type=float, default=None, dest="inset_b",
                                help="Fixní zanoření spodního napaječe v mm")
        parser_m2.add_argument("--inset-l", type=float, default=None, dest="inset_l",
                                help="Fixní zanoření levého napaječe v mm")
        parser_m2.add_argument("--patch-l", type=float, default=None, dest="patch_l")
        parser_m2.add_argument("--patch-w", type=float, default=None, dest="patch_w")
        parser_m2.add_argument("--freq-min", type=float, default=None, dest="freq_min")
        parser_m2.add_argument("--freq-max", type=float, default=None, dest="freq_max")
        parser_m2.add_argument("--freq-step", type=float, default=None, dest="freq_step")
        parser_m2.add_argument("--amr-its", type=int, default=None, dest="amr_max_its")
        parser_m2.add_argument("--linear-tol", type=float, default=None, dest="linear_tol")
        parser_m2.add_argument("--linear-its", type=int, default=None, dest="linear_max_its")
        parser_m2.add_argument("--farfield-nsample", type=int, default=None, dest="farfield_nsample")
        parser_m2.add_argument("--no-export", dest="export_each", action="store_false", default=None)
        parser_m2.add_argument("--skip-simulation", "--no-docker", dest="skip_simulation", action="store_true", default=False)
        parser_m2.add_argument("--driven-port", choices=["all", "1", "2"], default=None,
                                help="Volba buzeného portu pro Model 2: 'all' (obě větve LHCP), '1' (pouze spodní Ey), '2' (pouze levý Ex)")
        m2_args = parser_m2.parse_args(remaining_argv)

        run_sweep_model2(
            mode=m2_args.mode,
            sweep_target=m2_args.sweep_target,
            insets=m2_args.insets,
            insets_b=m2_args.insets_b,
            insets_l=m2_args.insets_l,
            fixed_name=m2_args.fixed_name,
            fixed_val=m2_args.fixed_val,
            manual_pairs=m2_args.manual_pairs,
            feed_lens_b=m2_args.feed_lens_b,
            feed_lens_l=m2_args.feed_lens_l,
            delta_l=m2_args.delta_l,
            feed_len_b=m2_args.feed_len_b,
            feed_len_l=m2_args.feed_len_l,
            feed_delta_l=m2_args.feed_delta_l,
            inset_b=m2_args.inset_b,
            inset_l=m2_args.inset_l,
            patch_l=m2_args.patch_l,
            patch_w=m2_args.patch_w,
            patch_lengths=m2_args.patch_lengths,
            freq_min=m2_args.freq_min,
            freq_max=m2_args.freq_max,
            freq_step=m2_args.freq_step,
            amr_max_its=m2_args.amr_max_its,
            farfield_nsample=m2_args.farfield_nsample,
            linear_tol=m2_args.linear_tol,
            linear_max_its=m2_args.linear_max_its,
            export_each=m2_args.export_each,
            skip_simulation=m2_args.skip_simulation,
            driven_port=m2_args.driven_port,
        )

    else:
        from sweep_model1 import run_sweep_model1
        parser_m1 = argparse.ArgumentParser(description="Parametrický sweep Modelu 1 (T-dělič)")
        parser_m1.add_argument("--param", choices=["inset", "patch_l"], default="inset")
        parser_m1.add_argument("--insets", type=float, nargs="+", default=None)
        parser_m1.add_argument("--patch-lengths", type=float, nargs="+", default=None, dest="patch_lengths")
        parser_m1.add_argument("--patch-l", type=float, default=None, dest="patch_l")
        parser_m1.add_argument("--patch-w", type=float, default=None, dest="patch_w")
        parser_m1.add_argument("--freq-min", type=float, default=None, dest="freq_min")
        parser_m1.add_argument("--freq-max", type=float, default=None, dest="freq_max")
        parser_m1.add_argument("--freq-step", type=float, default=None, dest="freq_step")
        parser_m1.add_argument("--amr-its", type=int, default=None, dest="amr_max_its")
        parser_m1.add_argument("--linear-tol", type=float, default=None, dest="linear_tol")
        parser_m1.add_argument("--linear-its", type=int, default=None, dest="linear_max_its")
        parser_m1.add_argument("--farfield-nsample", type=int, default=None, dest="farfield_nsample")
        parser_m1.add_argument("--no-export", dest="export_each", action="store_false", default=None)
        parser_m1.add_argument("--skip-simulation", "--no-docker", dest="skip_simulation", action="store_true", default=False)
        m1_args = parser_m1.parse_args(remaining_argv)

        run_sweep_model1(
            param=m1_args.param,
            insets=m1_args.insets,
            patch_lengths=m1_args.patch_lengths,
            patch_l=m1_args.patch_l,
            patch_w=m1_args.patch_w,
            freq_min=m1_args.freq_min,
            freq_max=m1_args.freq_max,
            freq_step=m1_args.freq_step,
            amr_max_its=m1_args.amr_max_its,
            farfield_nsample=m1_args.farfield_nsample,
            linear_tol=m1_args.linear_tol,
            linear_max_its=m1_args.linear_max_its,
            export_each=m1_args.export_each,
            skip_simulation=m1_args.skip_simulation,
        )
