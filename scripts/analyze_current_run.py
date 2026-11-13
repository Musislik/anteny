import numpy as np
import pandas as pd
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

print(f"{'Freq [GHz]':<12} | {'AR [dB]':<10} | {'D_LHCP [dBi]':<14} | {'D_RHCP [dBi]':<14} | {'D_tot [dBi]':<12}")
print("-" * 72)
for f in freqs:
    sub = df[np.isclose(df.iloc[:, 0], f, atol=1e-5)]
    m = compute_farfield_metrics(sub)
    b_idx = np.argmin(np.abs(m['th_deg']))
    ar = m['ar_db'][b_idx]
    d_lhcp = m['d_lhcp'][b_idx]
    d_rhcp = m['d_rhcp'][b_idx]
    d_tot = m['d_tot'][b_idx]
    print(f"{f:<12.4f} | {ar:<10.2f} | {d_lhcp:<14.2f} | {d_rhcp:<14.2f} | {d_tot:<12.2f}")
