# Summary

The screen surfaced 3 significant effects at α = 0.05; the strongest were `NTPs_mM_each`, `MgCl2_mM`, `NTPs_mM_each × MgCl2_mM`. `NTPs_mM_each` had the positive effect on the response (t = 21.33, coef = +2.94). Overall model R² is 0.99.

# Analysis: `yield_ug_per_uL`

- Model: `yield_ug_per_uL ~ (NTPs_mM_each_coded + MgCl2_mM_coded + T7_uL_coded + PEG8000_pct_coded)**2`
- df_resid: 8
- R²: 0.990
- Adjusted R²: 0.978

## Ranked effects

| Term | Coef | Std Err | t | p |
|---|---:|---:|---:|---:|
| `NTPs_mM_each_coded` | 2.939 | 0.1378 | 21.331 | 2.454e-08 |
| `MgCl2_mM_coded` | -2.078 | 0.1378 | -15.084 | 3.691e-07 |
| `NTPs_mM_each_coded:MgCl2_mM_coded` | 1.521 | 0.1378 | 11.037 | 4.045e-06 |
| `PEG8000_pct_coded` | 0.138 | 0.1378 | 1.002 | 0.3458 |
| `MgCl2_mM_coded:PEG8000_pct_coded` | -0.09125 | 0.1378 | -0.662 | 0.5264 |
| `NTPs_mM_each_coded:PEG8000_pct_coded` | 0.085 | 0.1378 | 0.617 | 0.5544 |
| `MgCl2_mM_coded:T7_uL_coded` | -0.05413 | 0.1378 | -0.393 | 0.7047 |
| `T7_uL_coded:PEG8000_pct_coded` | -0.03925 | 0.1378 | -0.285 | 0.783 |
| `NTPs_mM_each_coded:T7_uL_coded` | -0.01912 | 0.1378 | -0.139 | 0.893 |
| `T7_uL_coded` | 0.01088 | 0.1378 | 0.079 | 0.939 |

## Center-point curvature

- Mean at centers: 9.462
- Mean at corners: 9.954
- t = -0.454, p = 0.6558

## Diagnostics

- No outliers flagged.
- Heteroscedasticity: Breusch-Pagan p = 1, White p = 0.913
- Lack-of-fit F = 0.55, p = 0.758 (df_LOF=6, df_PE=2)

## Model selection

| Model | AICc | BIC | Adj R² | df_resid |
|---|---:|---:|---:|---:|
| `main+2FI` | 74.56 | 47.23 | 0.978 | 8 |
| `main-only` | 82.56 | 82.67 | 0.793 | 14 |
| `quadratic` | 85.33 | 44.66 | 0.981 | 7 |

Best by AICc: **main+2FI**
