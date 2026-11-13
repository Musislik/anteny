import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.abspath("src"))

import numpy as np
import pandas as pd
from plot_radiation_pattern import compute_farfield_metrics

farfield_csv = sys.argv[1] if len(sys.argv) > 1 else 'data/postpro/farfield-rE.csv'
if not os.path.exists(farfield_csv):
    print(f"File not found: {farfield_csv}")
    sys.exit(1)

df = pd.read_csv(farfield_csv)
freqs = np.unique(df.iloc[:, 0])

print(f"{'Freq [GHz]':<10} | {'AR [dB]':<8} | {'D_LHCP':<8} | {'D_RHCP':<8} | {'|Ey|/|Ex|':<10} | {'dPhi [deg]':<11} | {'dPhi - (-90)':<12}")
print("-" * 85)
for f in freqs:
    sub = df[np.isclose(df.iloc[:, 0], f, atol=1e-5)]
    m = compute_farfield_metrics(sub)
    b_idx = np.argmin(np.abs(m['th_deg']))
    ar = m['ar_db'][b_idx]
    d_lhcp = m['d_lhcp'][b_idx]
    d_rhcp = m['d_rhcp'][b_idx]
    
    # Calculate Ex and Ey phasors at boresight
    row = sub[np.abs(sub.iloc[:, 2]) < 1e-2].iloc[0]
    ex = row.iloc[4] + 1j * row.iloc[5]
    ey = row.iloc[6] + 1j * row.iloc[7]
    amp_ratio = abs(ey) / max(abs(ex), 1e-12)
    phi_diff = np.rad2deg(np.angle(ey) - np.angle(ex))
    # normalize to [-180, 180]
    phi_diff = (phi_diff + 180) % 360 - 180
    dphi_err = phi_diff - (-90.0)
    
    print(f"{f:<10.4f} | {ar:<8.2f} | {d_lhcp:<8.2f} | {d_rhcp:<8.2f} | {amp_ratio:<10.3f} | {phi_diff:<11.2f} | {dphi_err:<+12.2f}")
