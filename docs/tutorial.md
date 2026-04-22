# Screenase tutorial — why DoE, then how

This is a short self-contained tour. By the end you'll know **why** a designed
experiment beats the one-factor-at-a-time (OFAT) screening most IVT protocols
default to, and **how** to plan, run, and analyze a real screen end-to-end
using Screenase.

If you'd rather click than read, the same material lives in the app's
**Tutorial** tab: [huggingface.co/spaces/ethanarnold/screenase](https://huggingface.co/spaces/ethanarnold/screenase).

---

## Part 1 — Why DoE?

### The setup

Picture a 4-factor IVT screen that shows up every week in a lab: NTPs, MgCl₂,
T7 polymerase, PEG8000. You want to find the combination that maximizes yield.

The IVT literature is clear that **MgCl₂ interacts with NTPs** — the "right"
magnesium depends on how much NTP is around, because Mg²⁺ chelates the
phosphate groups. That's a *two-factor interaction*, and as we'll see, it
trips OFAT screening flat on its face.

### The two plans

**One-factor-at-a-time (OFAT).** The traditional protocol: hold three factors
at their midpoint, sweep the fourth across low/mid/high, record yield, pick the
winning level for that factor, move to the next. For 4 factors with 3 center
replicates, that's 3 + 2×4 = **11 runs**.

**Designed experiment (DoE).** Every corner of the 2⁴ hypercube plus 3 center
replicates = **19 runs**. You fit a linear model with main effects *and*
two-factor interactions, then search the fitted surface for the optimum.

### The scoreboard

We simulated both plans against a realistic IVT truth surface (intercept 10,
NTPs +2.5, MgCl₂ −1.5, T7 +0.5, PEG8000 +0.3, **NTPs×MgCl₂ +2.5**, with
σ = 0.35 Gaussian noise). Results at seed = 7:

| Strategy | Runs | Picked (NTPs, MgCl₂, T7, PEG) | True yield |
| --- | --- | --- | --- |
| OFAT | 11 | (+1, **−1**, +1, +1) | **12.5 µg/µL** |
| DoE  | 19 | (+1, **+1**, +1, +1) | **14.5 µg/µL** |
| True optimum | — | (+1, +1, +1, +1) | 14.5 µg/µL |

OFAT picks MgCl₂ *low* — a locally optimal move if you only vary one factor
at a time, because at the center point for NTPs, more MgCl₂ indeed reduces
yield. But once you push NTPs high, the sign flips: the NTPs × MgCl₂
interaction (+2.5 per unit of coded product) makes *high-MgCl₂, high-NTPs*
the real winner. OFAT never tests that corner, so it can't see the flip.

**The yield gap is 2 µg/µL — a 16% lift from the same reagents on the same
day, just from a better plan.**

### What DoE sees that OFAT can't

The analysis of the 19-run DoE screen reports the interactions it flagged at
α = 0.05:

- `NTPs_mM_each:MgCl2_mM` — the one that flipped OFAT's pick.
- `NTPs_mM_each:T7_uL` — a smaller, real synergy.

OFAT's plan doesn't contain any pairs of non-center points, so its design
matrix is *rank-deficient* for interaction terms. You can't estimate what the
plan never excited. This is not an analysis choice; it's a limit of the data.

### Counterargument: "DoE uses more runs"

True. 19 > 11. But:

- **Plackett-Burman** designs get 4-factor main effects in 12 runs — 1 more
  than OFAT — while still giving a proper design matrix you can analyze
  rigorously. Use them when k > 5 factors.
- **19 runs that find a 14.5 µg/µL optimum** beat 11 runs that find a
  12.5 µg/µL one almost every time. Reagents are cheap relative to a month of
  bench work that ended at the wrong setpoint.
- **Replicated center points** in DoE give you a noise estimate and a
  curvature test for free. OFAT gives you neither unless you add replicates,
  at which point you're paying the extra runs anyway.

---

## Part 2 — Your first screen in Screenase

Six steps from blank slate to a bench-ready plan.

### 1. Configure the screen

Open the app ([live demo](https://huggingface.co/spaces/ethanarnold/screenase)
or `streamlit run streamlit_app.py` locally). In the sidebar:

- **Reaction volume, DNA template, center points, seed** — reasonable
  defaults; change `seed` if you want a different randomization.
- **High/Low setpoints** — the only thing you really have to think about.
  Pick low/high values that (a) your stocks can deliver, (b) your pipettes
  can reliably dispense, and (c) span a wide enough range to see real
  effects. *Too narrow → everything looks flat. Too wide → you may step
  outside physical feasibility.*

### 2. Pick a design type

Under **Design Type** in the sidebar:

- **Full factorial** (2ᵏ + centers) — your workhorse for k ≤ 5. Every
  main effect and every 2-factor interaction is estimable.
- **Central-composite (CCD)** — second-phase design. After a full factorial
  flags curvature (via the center-point test), a CCD adds axial points so
  you can fit a quadratic model and find a true optimum.
- **Plackett-Burman** — main-effect screening for k > 5. 12 runs handles
  up to 11 factors; interactions are aliased.

### 3. Assign a plate layout

Under **Plate Layout**:

- **Column-major** — the default; fills A1, B1, …, H1, A2, B2, …
- **Row-major** — fills A1, A2, …, A12, B1, B2, …
- **Randomized** — breaks up positional systematics (edge effects, thermal
  gradients). Recommended for anything you'd publish.

### 4. Generate and download

The **Generate screen** tab shows:

- A **metrics row** — run count, factor count, config hash (12 char sha256
  of the canonical JSON; same config + same seed = byte-identical output).
- The **design table** with each run's factor setpoints and a `center?`
  checkbox.
- A **bench sheet preview** — the printable HTML, with per-run pipetting
  volumes and embedded plate map.
- **Downloads**: screen CSV (real values, for the bench), coded CSV (±1
  values, for analysis), bench sheet HTML, and plate-layout CSV.

### 5. Run the screen at the bench

Work down the bench sheet row by row. The volumes are computed from your
stock concentrations and factor setpoints; the plate map tells you which
well is which. Record your yield (or whatever response you're optimizing)
in a new column on the coded CSV — call it `yield_ug_per_uL` or similar.

### 6. Analyze the results

The **Analyze results** tab takes the filled coded CSV and returns:

- **R², Adjusted R², df residual, N** — fit quality at a glance.
- **Plain-English summary** — a one-paragraph narration of the top drivers
  and the overall fit, generated by `screenase.narrate`.
- **Pareto of standardized effects** — a bar chart of |t| for every term,
  with a red line at the α = 0.05 threshold. Bars that cross the line are
  real effects.
- **Ranked effects table** — every term, its coefficient, std err, t, and
  p-value.
- **Response surface** — a 2D contour over the two most-significant factors,
  with other factors held at center.
- **Desirability optimum** — the coded setpoint that maximizes (or
  minimizes) the fitted response.
- **CCD follow-up recommendation** — if the center-point curvature test
  comes back significant at α = 0.05, Screenase prints the exact CLI
  command to run the CCD follow-up.

---

## Worked example, without a bench

1. Open the live demo: [huggingface.co/spaces/ethanarnold/screenase](https://huggingface.co/spaces/ethanarnold/screenase).
2. **Generate screen** tab — the sidebar defaults to the canonical 4-factor
   IVT. Click through the design and bench sheet to see what gets produced.
3. **Analyze results** tab → **Demo results** → you'll see exactly the
   analysis pack above, run on a pre-filled simulated response column.
4. Note the CCD recommendation if/when it appears, and the `?cfg=…` share
   link in the Generate tab — that URL encodes your sidebar state so you
   can send it to a colleague.

The whole loop takes ~90 seconds and shows you exactly what you'd get back
from a real screen.

---

## Going further

- **CLI**: `screenase generate --config my.yaml --out-dir out/` produces
  the same artifacts as the app. `screenase analyze results.csv --response
  yield_ug_per_uL --out-dir out/` runs the analysis pipeline.
- **Worked artifact gallery**: [`docs/examples/`](examples/) has pre-rendered
  CSVs, bench sheets, PDFs, plate maps, and analysis reports from several
  design types.
- **Walkthrough notebook**: [`docs/walkthrough.ipynb`](walkthrough.ipynb)
  runs the full loop in code. The companion [`docs/examples/tutorial/tutorial.ipynb`](examples/tutorial/tutorial.ipynb)
  reproduces the OFAT-vs-DoE comparison from this document, numerically, so
  you can rerun it under your own noise assumptions.
- **Benchling integration**: the `screenase.benchling` subpackage scaffolds
  Request / Result / Entry schemas and handles webhooks — see
  [`docs/benchling_mapping.md`](benchling_mapping.md).
