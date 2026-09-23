# M05 Stress-Testing Engine

Status: **Complete for the phase-one synthetic zero-coupon portfolio**

## Objective

Measure the current frozen portfolio's response to deterministic hypothetical, historical, PCA-factor, and reverse stress scenarios. M05 uses the same 2026-09-18 base curve, USD 10 million 3Y/7Y/15Y portfolio, continuously compounded zero-rate units, full-repricing function, and positive-loss convention accepted in M03 and M04.

Stress results are conditional scenario losses. No probability or forecast frequency is assigned to a deterministic stress.

## Common valuation and attribution

For every node shock vector `Delta y`:

```text
scenario_curve = base_curve + Delta y
full_loss = V(base_curve, frozen_positions) - V(scenario_curve, frozen_positions)
```

Position losses are calculated by full repricing and reconcile exactly to portfolio loss. The explanatory linear estimate uses a central-difference key-rate DV01 at every 1Y-30Y node:

```text
KRDV01_j = [V(y - 1 bp at node j) - V(y + 1 bp at node j)] / 2
linear_node_contribution_j = KRDV01_j * Delta y_j / 1 bp
full_minus_linear = full_loss - sum(linear_node_contribution_j)
```

The full-repricing loss remains the primary result. The difference from the key-rate estimate exposes convexity and other nonlinear effects under large shocks.

## Hypothetical scenarios

The accepted deterministic library contains 14 scenarios:

- Parallel: +/-50, +/-100, and +/-200 bp at every curve node.
- Steepener and flattener: 50 and 100 bp maximum node amplitude, piecewise linear from the 1Y node through a 7Y zero-shock pivot to the 30Y node.
- Positive and negative butterfly: 50 and 100 bp maximum amplitude, piecewise linear through 0 bp at 1Y, the signed peak at 7Y, and 0 bp at 30Y.

Selected live results are:

| Scenario | Full-repricing loss | Linear loss | Full minus linear |
|---|---:|---:|---:|
| Parallel +50 bp | USD 405,130.53 | USD 416,666.77 | USD -11,536.24 |
| Parallel +100 bp | USD 788,175.57 | USD 833,333.54 | USD -45,157.97 |
| Parallel +200 bp | USD 1,493,530.03 | USD 1,666,667.08 | USD -173,137.05 |
| Steepener 100 bp | USD 102,116.26 | USD 107,246.44 | USD -5,130.18 |
| Positive butterfly 100 bp | USD 569,165.84 | USD 592,753.77 | USD -23,587.93 |

For this long-only zero-coupon portfolio, negative parallel shocks produce gains. Convexity makes the gain from a downward shock larger in magnitude than the loss from an equal upward shock.

## Historical extreme replay

The engine selects the five largest current-portfolio losses from complete one-day shocks. It also constructs every eligible 5- and 10-source-day cumulative curve change, rejects any window containing an incomplete curve date, fully reprices all successful candidates, and retains the three largest losses per horizon.

Selected historical results are:

| Horizon | Shock end date | Full-repricing loss | Maximum absolute node shock |
|---:|---:|---:|---:|
| 1 source day | 2020-03-17 | USD 257,172.37 | 37.87 bp |
| 5 source days | 2025-04-11 | USD 393,142.68 | 52.10 bp |
| 10 source days | 2010-12-14 | USD 486,628.07 | 74.35 bp |

Across the two multi-day horizons, 11,315 candidate windows were audited: 7,537 succeeded and 3,778 remained explicitly marked `missing_input`. A failed date is never bridged and never converted to a zero shock or zero loss.

The historical labels identify curve dates only. No causal event claim is inferred from the market data.

## PCA factor stresses

PCA is fitted to the latest 750 successful 30-node daily zero-rate changes, covering 2023-07-31 through 2026-09-18. Inputs are mean-centered and decomposed by SVD. Factor shocks use each loading multiplied by its historical factor standard deviation and +/-2, +/-3, or +/-4.

| Factor | Explained variance | Loading interpretation after inspection |
|---|---:|---|
| PC1 | 88.00% | Level: all loadings have the same sign |
| PC2 | 8.45% | Slope: positive short-end and negative long-end loadings with one main sign change |
| PC3 | 2.62% | Curvature-like: changing middle and wing exposures with a more complex shape |
| Residual after PC1-PC3 | 0.93% | Retained and reported |

The largest PCA loss was USD 176,589.63 for the `PC1 +4 standard deviations` scenario. PCA labels are assigned only after inspecting loadings; the reusable engine stores the factors as PC1, PC2, and PC3.

M05 uses PCA only for deterministic factor stresses. M07 separately implements and validates stochastic PCA simulation and benchmark risk models.

## Reverse stress

Reverse stress searches within five normalized shape families: parallel-up, steepener, flattener, positive butterfly, and negative butterfly. Amplitude means the maximum absolute curve-node shock. A 1 bp grid locates the first threshold crossing, then bisection refines the boundary to 0.01 bp. The maximum permitted amplitude is 500 bp.

For each loss threshold, the engine reports every family that can breach the threshold and identifies the minimum comparable maximum-node amplitude:

| Loss threshold | Minimum family | Minimum amplitude | Achieved loss |
|---:|---|---:|---:|
| USD 100,000 | Parallel up | 12.0859 bp | USD 100,030.84 |
| USD 200,000 | Parallel up | 24.3359 bp | USD 200,035.82 |
| USD 300,000 | Parallel up | 36.7578 bp | USD 300,044.24 |

Within 500 bp, parallel-up, steepener, and positive-butterfly directions reached all three thresholds. Flattener and negative-butterfly directions did not, and remain explicitly marked `threshold_not_reached`.

Reverse-stress minimality is conditional on the five configured shape families and the maximum-node-amplitude metric. It is not an unconstrained optimization over every possible 30-node curve.

## Acceptance evidence

- Zero shock produces exactly zero loss.
- All 43 standard stress scenarios value successfully with unique IDs.
- Parallel-up shocks produce losses and parallel-down shocks produce gains.
- Full-repricing position losses reconcile to portfolio loss.
- Key-rate node contributions reconcile to the linear estimate.
- Full minus linear residual reconciles for every successful scenario.
- Historical scenarios use no information after the valuation date.
- Multi-day historical windows never bridge incomplete curves.
- PCA loadings are orthonormal.
- PCA residual variance is positive and retained.
- Every configured reverse-loss threshold is reached by at least one permitted family.
- Successful reverse-stress boundaries bracket their loss thresholds.
- Forty-three standard-library unit tests pass across M02-M05.
- The live official-GSW end-to-end report passes all fourteen checks.

## Completion boundary

M05 provides deterministic stress losses and conditional reverse-stress thresholds. It does not estimate scenario probabilities or validate forecast calibration. M06 separately implements rolling VaR exceptions, Kupiec and Christoffersen tests, and ES tail diagnostics. M07 separately implements Parametric Normal and stochastic PCA models.
