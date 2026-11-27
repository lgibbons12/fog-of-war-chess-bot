# Particle metrics: `particle_ev100` (1200 games)

## Calibration (chosen move's p_loss vs immediate king-capture loss)

| Mode | Bucket | Moves | Mean p_loss | Lost | Loss rate |
|---|---|---|---|---|---|
| particles | 0 | 35881 | 0.0000 | 118 | 0.0033 |
| particles | (0,.01] | 38 | 0.0025 | 0 | 0.0000 |
| particles | (.01,.05] | 2662 | 0.0275 | 98 | 0.0368 |
| particles | (.05,.2] | 1822 | 0.0950 | 127 | 0.0697 |
| particles | >.2 | 183 | 0.3447 | 38 | 0.2077 |
| unavailable | 0 | 2 | 0.0000 | 0 | 0.0000 |
| unavailable | >.2 | 4 | 1.0000 | 1 | 0.2500 |

## Truth coverage and per-square log loss on '?' squares

Overall: coverage 0.325, truth weight 0.112 over 81328 observations; log loss particles 0.4401 vs possibility 0.5776 nats over 3208076 squares.

| Plies | Observations | Coverage | Truth weight | Unavailable | Log loss (particles) | Log loss (possibility) |
|---|---|---|---|---|---|---|
| 0-19 | 23756 | 0.544 | 0.223 | 3 | 0.4095 | 0.9652 |
| 20-39 | 21253 | 0.265 | 0.101 | 6 | 0.5931 | 0.6750 |
| 40-59 | 17012 | 0.187 | 0.047 | 3 | 0.4497 | 0.4239 |
| 60-79 | 11345 | 0.215 | 0.037 | 4 | 0.3452 | 0.3467 |
| 80-99 | 5476 | 0.276 | 0.050 | 0 | 0.3240 | 0.3185 |
| 100-119 | 1835 | 0.304 | 0.064 | 0 | 0.3299 | 0.3092 |
| 120-139 | 489 | 0.321 | 0.044 | 0 | 0.3680 | 0.3150 |
| 140-159 | 116 | 0.353 | 0.064 | 0 | 0.4197 | 0.3617 |
| 160-179 | 34 | 0.000 | 0.000 | 0 | 0.5849 | 0.5151 |
| 180-199 | 12 | 0.000 | 0.000 | 0 | 0.8102 | 0.5477 |

## Set health

- depletions: 3022
- regenerations: 1763
- regeneration_failures: 16
- reexpansions: 1257
- reexpansion_failures: 1779
- resamples: 16334
- unavailable_observations: 16
- depletions_per_game: 2.518
- recovery_success: 0.999
- median_distinct: 36.000
- median_ess: 28.199
- particles switched off: never

## Time per move

40592 moves: median 0.117 s, p95 0.588 s, max 4.439 s (updates since the previous decision plus the decision).
