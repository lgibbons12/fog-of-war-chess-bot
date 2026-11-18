## Main effects (mean over all other factors)

### n

| n | configs | Truth coverage | Truth weight | Depletions/game | Brier (x100) | Log loss | Missed losses | Min-risk pick loses | Median s/move | Max s/move |
|---|---|---|---|---|---|---|---|---|---|---|
| 32 | 16 | 0.280 | 0.111 | 2.99 | 0.813 | 0.0408 | 0.035 | 0.0044 | 0.068 | 0.70 |
| 64 | 16 | 0.362 | 0.125 | 2.10 | 0.789 | 0.0380 | 0.030 | 0.0034 | 0.101 | 1.43 |
| 128 | 16 | 0.432 | 0.136 | 1.45 | 0.705 | 0.0321 | 0.021 | 0.0018 | 0.138 | 2.34 |
| 256 | 16 | 0.525 | 0.147 | 0.92 | 0.675 | 0.0293 | 0.018 | 0.0019 | 0.160 | 3.93 |
| 512 | 16 | 0.593 | 0.154 | 0.64 | 0.645 | 0.0261 | 0.011 | 0.0016 | 0.207 | 6.52 |

### model

| model | configs | Truth coverage | Truth weight | Depletions/game | Brier (x100) | Log loss | Missed losses | Min-risk pick loses | Median s/move | Max s/move |
|---|---|---|---|---|---|---|---|---|---|---|
| uniform | 40 | 0.437 | 0.133 | 1.62 | 0.725 | 0.0325 | 0.021 | 0.0026 | 0.136 | 3.02 |
| capture | 40 | 0.440 | 0.136 | 1.62 | 0.726 | 0.0340 | 0.025 | 0.0027 | 0.134 | 2.95 |

### trigger

| trigger | configs | Truth coverage | Truth weight | Depletions/game | Brier (x100) | Log loss | Missed losses | Min-risk pick loses | Median s/move | Max s/move |
|---|---|---|---|---|---|---|---|---|---|---|
| above_n | 40 | 0.455 | 0.141 | 1.55 | 0.702 | 0.0310 | 0.018 | 0.0024 | 0.131 | 3.40 |
| ess | 40 | 0.422 | 0.129 | 1.68 | 0.749 | 0.0355 | 0.029 | 0.0029 | 0.139 | 2.57 |

### recovery

| recovery | configs | Truth coverage | Truth weight | Depletions/game | Brier (x100) | Log loss | Missed losses | Min-risk pick loses | Median s/move | Max s/move |
|---|---|---|---|---|---|---|---|---|---|---|
| supports | 40 | 0.421 | 0.126 | 1.70 | 0.746 | 0.0341 | 0.023 | 0.0028 | 0.142 | 2.34 |
| reexpand | 40 | 0.456 | 0.143 | 1.54 | 0.705 | 0.0324 | 0.024 | 0.0025 | 0.127 | 3.62 |

### diversity

| diversity | configs | Truth coverage | Truth weight | Depletions/game | Brier (x100) | Log loss | Missed losses | Min-risk pick loses | Median s/move | Max s/move |
|---|---|---|---|---|---|---|---|---|---|---|
| False | 40 | 0.437 | 0.135 | 1.65 | 0.733 | 0.0343 | 0.027 | 0.0028 | 0.134 | 3.05 |
| True | 40 | 0.440 | 0.134 | 1.59 | 0.718 | 0.0322 | 0.019 | 0.0025 | 0.135 | 2.92 |

## Reference: possibility tracker as a predictor

| Brier (x100) | Log loss | Min-risk pick loses |
|---|---|---|
| 1.841 | 0.0764 | 0.0064 |

## Top 10 by Brier score (lower is better)

| config | Truth coverage | Truth weight | Depletions/game | Brier (x100) | Log loss | Missed losses | Min-risk pick loses | Median s/move | Max s/move |
|---|---|---|---|---|---|---|---|---|---|
| n512-uniform-above_n-reexpand-div | 0.644 | 0.174 | 0.53 | 0.552 | 0.0194 | 0.000 | 0.0016 | 0.177 | 7.73 |
| n512-capture-above_n-reexpand-sys | 0.661 | 0.179 | 0.43 | 0.564 | 0.0198 | 0.002 | 0.0016 | 0.157 | 5.83 |
| n512-capture-above_n-reexpand-div | 0.629 | 0.169 | 0.50 | 0.585 | 0.0215 | 0.001 | 0.0016 | 0.181 | 7.83 |
| n256-capture-ess-supports-div | 0.564 | 0.155 | 0.78 | 0.599 | 0.0238 | 0.010 | 0.0016 | 0.153 | 2.72 |
| n256-capture-ess-reexpand-div | 0.564 | 0.155 | 0.78 | 0.599 | 0.0238 | 0.010 | 0.0016 | 0.151 | 3.18 |
| n128-capture-above_n-reexpand-div | 0.519 | 0.166 | 1.03 | 0.599 | 0.0263 | 0.016 | 0.0016 | 0.104 | 3.19 |
| n512-uniform-above_n-reexpand-sys | 0.633 | 0.171 | 0.43 | 0.599 | 0.0210 | 0.001 | 0.0016 | 0.164 | 9.98 |
| n256-uniform-above_n-reexpand-sys | 0.575 | 0.173 | 0.72 | 0.602 | 0.0222 | 0.003 | 0.0024 | 0.137 | 6.70 |
| n512-uniform-ess-supports-div | 0.535 | 0.133 | 0.77 | 0.619 | 0.0235 | 0.003 | 0.0016 | 0.249 | 6.56 |
| n512-capture-above_n-supports-div | 0.551 | 0.132 | 0.73 | 0.624 | 0.0234 | 0.001 | 0.0016 | 0.249 | 6.16 |

## Top 10 by truth coverage

| config | Truth coverage | Truth weight | Depletions/game | Brier (x100) | Log loss | Missed losses | Min-risk pick loses | Median s/move | Max s/move |
|---|---|---|---|---|---|---|---|---|---|
| n512-capture-above_n-reexpand-sys | 0.661 | 0.179 | 0.43 | 0.564 | 0.0198 | 0.002 | 0.0016 | 0.157 | 5.83 |
| n512-uniform-above_n-reexpand-div | 0.644 | 0.174 | 0.53 | 0.552 | 0.0194 | 0.000 | 0.0016 | 0.177 | 7.73 |
| n512-uniform-above_n-reexpand-sys | 0.633 | 0.171 | 0.43 | 0.599 | 0.0210 | 0.001 | 0.0016 | 0.164 | 9.98 |
| n512-capture-above_n-reexpand-div | 0.629 | 0.169 | 0.50 | 0.585 | 0.0215 | 0.001 | 0.0016 | 0.181 | 7.83 |
| n512-uniform-ess-reexpand-sys | 0.610 | 0.162 | 0.67 | 0.680 | 0.0351 | 0.042 | 0.0016 | 0.203 | 6.57 |
| n512-uniform-ess-supports-sys | 0.606 | 0.160 | 0.68 | 0.681 | 0.0352 | 0.042 | 0.0016 | 0.212 | 7.70 |
| n512-capture-ess-supports-div | 0.592 | 0.153 | 0.58 | 0.628 | 0.0224 | 0.000 | 0.0016 | 0.209 | 5.31 |
| n512-capture-ess-reexpand-div | 0.592 | 0.153 | 0.58 | 0.628 | 0.0224 | 0.000 | 0.0016 | 0.174 | 5.28 |
| n512-uniform-above_n-supports-sys | 0.591 | 0.146 | 0.57 | 0.701 | 0.0299 | 0.017 | 0.0024 | 0.211 | 6.00 |
| n512-capture-above_n-supports-sys | 0.589 | 0.150 | 0.60 | 0.680 | 0.0284 | 0.015 | 0.0016 | 0.203 | 5.88 |

## All configurations

| config | Truth coverage | Truth weight | Depletions/game | Brier (x100) | Log loss | Missed losses | Min-risk pick loses | Median s/move | Max s/move |
|---|---|---|---|---|---|---|---|---|---|
| n32-uniform-above_n-supports-sys | 0.298 | 0.125 | 2.93 | 0.798 | 0.0387 | 0.028 | 0.0072 | 0.057 | 0.37 |
| n32-uniform-above_n-supports-div | 0.252 | 0.101 | 3.03 | 0.877 | 0.0418 | 0.023 | 0.0024 | 0.060 | 0.32 |
| n32-uniform-above_n-reexpand-sys | 0.352 | 0.146 | 2.58 | 0.796 | 0.0433 | 0.058 | 0.0056 | 0.059 | 1.48 |
| n32-uniform-above_n-reexpand-div | 0.287 | 0.114 | 2.85 | 0.655 | 0.0262 | 0.004 | 0.0016 | 0.067 | 1.34 |
| n32-uniform-ess-supports-sys | 0.253 | 0.098 | 3.30 | 0.851 | 0.0419 | 0.033 | 0.0024 | 0.071 | 0.35 |
| n32-uniform-ess-supports-div | 0.260 | 0.103 | 3.10 | 0.825 | 0.0433 | 0.047 | 0.0040 | 0.069 | 0.32 |
| n32-uniform-ess-reexpand-sys | 0.258 | 0.100 | 3.13 | 0.938 | 0.0480 | 0.044 | 0.0072 | 0.070 | 0.61 |
| n32-uniform-ess-reexpand-div | 0.263 | 0.106 | 3.03 | 0.725 | 0.0347 | 0.026 | 0.0048 | 0.069 | 0.55 |
| n32-capture-above_n-supports-sys | 0.293 | 0.110 | 3.08 | 0.774 | 0.0363 | 0.018 | 0.0072 | 0.067 | 0.37 |
| n32-capture-above_n-supports-div | 0.275 | 0.106 | 3.03 | 0.825 | 0.0425 | 0.028 | 0.0032 | 0.074 | 0.43 |
| n32-capture-above_n-reexpand-sys | 0.329 | 0.135 | 2.62 | 0.808 | 0.0503 | 0.072 | 0.0032 | 0.065 | 1.47 |
| n32-capture-above_n-reexpand-div | 0.303 | 0.117 | 2.90 | 0.690 | 0.0321 | 0.014 | 0.0016 | 0.070 | 1.43 |
| n32-capture-ess-supports-sys | 0.258 | 0.100 | 3.00 | 0.839 | 0.0453 | 0.056 | 0.0048 | 0.072 | 0.39 |
| n32-capture-ess-supports-div | 0.250 | 0.097 | 3.12 | 0.955 | 0.0445 | 0.028 | 0.0056 | 0.072 | 0.34 |
| n32-capture-ess-reexpand-sys | 0.275 | 0.107 | 2.93 | 0.855 | 0.0484 | 0.067 | 0.0072 | 0.071 | 0.76 |
| n32-capture-ess-reexpand-div | 0.275 | 0.112 | 3.13 | 0.793 | 0.0363 | 0.020 | 0.0024 | 0.071 | 0.62 |
| n64-uniform-above_n-supports-sys | 0.360 | 0.117 | 2.27 | 0.781 | 0.0359 | 0.025 | 0.0032 | 0.104 | 0.72 |
| n64-uniform-above_n-supports-div | 0.337 | 0.112 | 2.08 | 0.830 | 0.0378 | 0.016 | 0.0032 | 0.104 | 0.74 |
| n64-uniform-above_n-reexpand-sys | 0.430 | 0.146 | 1.83 | 0.693 | 0.0306 | 0.023 | 0.0016 | 0.085 | 2.03 |
| n64-uniform-above_n-reexpand-div | 0.396 | 0.134 | 1.70 | 0.751 | 0.0357 | 0.025 | 0.0032 | 0.089 | 2.75 |
| n64-uniform-ess-supports-sys | 0.323 | 0.111 | 2.32 | 0.813 | 0.0375 | 0.022 | 0.0024 | 0.096 | 0.68 |
| n64-uniform-ess-supports-div | 0.369 | 0.122 | 2.02 | 0.811 | 0.0368 | 0.022 | 0.0040 | 0.102 | 0.69 |
| n64-uniform-ess-reexpand-sys | 0.335 | 0.123 | 2.20 | 0.794 | 0.0373 | 0.023 | 0.0016 | 0.100 | 1.36 |
| n64-uniform-ess-reexpand-div | 0.376 | 0.124 | 2.03 | 0.732 | 0.0322 | 0.021 | 0.0024 | 0.099 | 1.43 |
| n64-capture-above_n-supports-sys | 0.318 | 0.111 | 2.50 | 0.860 | 0.0437 | 0.041 | 0.0048 | 0.108 | 0.72 |
| n64-capture-above_n-supports-div | 0.380 | 0.129 | 1.93 | 0.704 | 0.0290 | 0.003 | 0.0016 | 0.100 | 1.27 |
| n64-capture-above_n-reexpand-sys | 0.415 | 0.140 | 2.12 | 0.751 | 0.0381 | 0.033 | 0.0024 | 0.111 | 2.77 |
| n64-capture-above_n-reexpand-div | 0.423 | 0.150 | 1.77 | 0.802 | 0.0393 | 0.035 | 0.0016 | 0.095 | 2.85 |
| n64-capture-ess-supports-sys | 0.307 | 0.111 | 2.25 | 0.909 | 0.0494 | 0.057 | 0.0080 | 0.115 | 1.02 |
| n64-capture-ess-supports-div | 0.338 | 0.117 | 2.23 | 0.763 | 0.0385 | 0.035 | 0.0048 | 0.108 | 1.11 |
| n64-capture-ess-reexpand-sys | 0.331 | 0.125 | 2.10 | 0.886 | 0.0485 | 0.061 | 0.0072 | 0.102 | 1.63 |
| n64-capture-ess-reexpand-div | 0.348 | 0.129 | 2.22 | 0.743 | 0.0377 | 0.036 | 0.0032 | 0.101 | 1.13 |
| n128-uniform-above_n-supports-sys | 0.365 | 0.114 | 1.73 | 0.723 | 0.0291 | 0.007 | 0.0032 | 0.165 | 1.64 |
| n128-uniform-above_n-supports-div | 0.427 | 0.122 | 1.50 | 0.703 | 0.0307 | 0.019 | 0.0024 | 0.161 | 1.49 |
| n128-uniform-above_n-reexpand-sys | 0.467 | 0.157 | 1.32 | 0.647 | 0.0263 | 0.008 | 0.0016 | 0.121 | 3.70 |
| n128-uniform-above_n-reexpand-div | 0.514 | 0.162 | 1.08 | 0.628 | 0.0245 | 0.005 | 0.0016 | 0.110 | 3.83 |
| n128-uniform-ess-supports-sys | 0.418 | 0.128 | 1.55 | 0.648 | 0.0260 | 0.007 | 0.0000 | 0.150 | 1.65 |
| n128-uniform-ess-supports-div | 0.398 | 0.126 | 1.48 | 0.874 | 0.0451 | 0.044 | 0.0032 | 0.145 | 1.42 |
| n128-uniform-ess-reexpand-sys | 0.415 | 0.131 | 1.52 | 0.643 | 0.0255 | 0.007 | 0.0000 | 0.142 | 1.46 |
| n128-uniform-ess-reexpand-div | 0.412 | 0.138 | 1.45 | 0.804 | 0.0428 | 0.045 | 0.0040 | 0.139 | 2.81 |
| n128-capture-above_n-supports-sys | 0.392 | 0.123 | 1.67 | 0.694 | 0.0282 | 0.008 | 0.0008 | 0.146 | 1.36 |
| n128-capture-above_n-supports-div | 0.410 | 0.123 | 1.50 | 0.662 | 0.0260 | 0.003 | 0.0016 | 0.138 | 1.41 |
| n128-capture-above_n-reexpand-sys | 0.501 | 0.163 | 1.30 | 0.703 | 0.0313 | 0.020 | 0.0000 | 0.112 | 5.33 |
| n128-capture-above_n-reexpand-div | 0.519 | 0.166 | 1.03 | 0.599 | 0.0263 | 0.016 | 0.0016 | 0.104 | 3.19 |
| n128-capture-ess-supports-sys | 0.413 | 0.129 | 1.48 | 0.685 | 0.0343 | 0.033 | 0.0016 | 0.141 | 1.88 |
| n128-capture-ess-supports-div | 0.426 | 0.129 | 1.57 | 0.765 | 0.0368 | 0.029 | 0.0024 | 0.148 | 1.94 |
| n128-capture-ess-reexpand-sys | 0.414 | 0.131 | 1.43 | 0.701 | 0.0369 | 0.040 | 0.0024 | 0.140 | 1.62 |
| n128-capture-ess-reexpand-div | 0.425 | 0.131 | 1.60 | 0.803 | 0.0431 | 0.045 | 0.0032 | 0.136 | 2.71 |
| n256-uniform-above_n-supports-sys | 0.532 | 0.140 | 0.92 | 0.659 | 0.0246 | 0.003 | 0.0016 | 0.157 | 3.80 |
| n256-uniform-above_n-supports-div | 0.503 | 0.135 | 1.02 | 0.733 | 0.0332 | 0.025 | 0.0032 | 0.174 | 2.73 |
| n256-uniform-above_n-reexpand-sys | 0.575 | 0.173 | 0.72 | 0.602 | 0.0222 | 0.003 | 0.0024 | 0.137 | 6.70 |
| n256-uniform-above_n-reexpand-div | 0.572 | 0.170 | 0.88 | 0.638 | 0.0227 | 0.000 | 0.0024 | 0.161 | 6.81 |
| n256-uniform-ess-supports-sys | 0.499 | 0.135 | 1.05 | 0.723 | 0.0301 | 0.014 | 0.0016 | 0.182 | 2.49 |
| n256-uniform-ess-supports-div | 0.498 | 0.133 | 0.95 | 0.720 | 0.0348 | 0.030 | 0.0032 | 0.153 | 2.62 |
| n256-uniform-ess-reexpand-sys | 0.502 | 0.137 | 1.03 | 0.700 | 0.0290 | 0.014 | 0.0016 | 0.177 | 2.67 |
| n256-uniform-ess-reexpand-div | 0.497 | 0.133 | 0.95 | 0.720 | 0.0348 | 0.030 | 0.0032 | 0.148 | 2.79 |
| n256-capture-above_n-supports-sys | 0.476 | 0.133 | 1.10 | 0.657 | 0.0292 | 0.018 | 0.0008 | 0.171 | 2.59 |
| n256-capture-above_n-supports-div | 0.524 | 0.152 | 0.92 | 0.722 | 0.0347 | 0.031 | 0.0032 | 0.172 | 2.71 |
| n256-capture-above_n-reexpand-sys | 0.536 | 0.161 | 0.88 | 0.637 | 0.0282 | 0.018 | 0.0008 | 0.145 | 6.06 |
| n256-capture-above_n-reexpand-div | 0.567 | 0.172 | 0.80 | 0.699 | 0.0309 | 0.019 | 0.0008 | 0.146 | 6.35 |
| n256-capture-ess-supports-sys | 0.498 | 0.133 | 0.98 | 0.699 | 0.0336 | 0.032 | 0.0016 | 0.166 | 2.64 |
| n256-capture-ess-supports-div | 0.564 | 0.155 | 0.78 | 0.599 | 0.0238 | 0.010 | 0.0016 | 0.153 | 2.72 |
| n256-capture-ess-reexpand-sys | 0.498 | 0.133 | 1.00 | 0.698 | 0.0337 | 0.032 | 0.0016 | 0.163 | 5.95 |
| n256-capture-ess-reexpand-div | 0.564 | 0.155 | 0.78 | 0.599 | 0.0238 | 0.010 | 0.0016 | 0.151 | 3.18 |
| n512-uniform-above_n-supports-sys | 0.591 | 0.146 | 0.57 | 0.701 | 0.0299 | 0.017 | 0.0024 | 0.211 | 6.00 |
| n512-uniform-above_n-supports-div | 0.569 | 0.141 | 0.75 | 0.686 | 0.0281 | 0.014 | 0.0016 | 0.242 | 5.73 |
| n512-uniform-above_n-reexpand-sys | 0.633 | 0.171 | 0.43 | 0.599 | 0.0210 | 0.001 | 0.0016 | 0.164 | 9.98 |
| n512-uniform-above_n-reexpand-div | 0.644 | 0.174 | 0.53 | 0.552 | 0.0194 | 0.000 | 0.0016 | 0.177 | 7.73 |
| n512-uniform-ess-supports-sys | 0.606 | 0.160 | 0.68 | 0.681 | 0.0352 | 0.042 | 0.0016 | 0.212 | 7.70 |
| n512-uniform-ess-supports-div | 0.535 | 0.133 | 0.77 | 0.619 | 0.0235 | 0.003 | 0.0016 | 0.249 | 6.56 |
| n512-uniform-ess-reexpand-sys | 0.610 | 0.162 | 0.67 | 0.680 | 0.0351 | 0.042 | 0.0016 | 0.203 | 6.57 |
| n512-uniform-ess-reexpand-div | 0.535 | 0.133 | 0.77 | 0.640 | 0.0268 | 0.013 | 0.0016 | 0.244 | 6.11 |
| n512-capture-above_n-supports-sys | 0.589 | 0.150 | 0.60 | 0.680 | 0.0284 | 0.015 | 0.0016 | 0.203 | 5.88 |
| n512-capture-above_n-supports-div | 0.551 | 0.132 | 0.73 | 0.624 | 0.0234 | 0.001 | 0.0016 | 0.249 | 6.16 |
| n512-capture-above_n-reexpand-sys | 0.661 | 0.179 | 0.43 | 0.564 | 0.0198 | 0.002 | 0.0016 | 0.157 | 5.83 |
| n512-capture-above_n-reexpand-div | 0.629 | 0.169 | 0.50 | 0.585 | 0.0215 | 0.001 | 0.0016 | 0.181 | 7.83 |
| n512-capture-ess-supports-sys | 0.573 | 0.154 | 0.82 | 0.727 | 0.0304 | 0.014 | 0.0016 | 0.224 | 5.54 |
| n512-capture-ess-supports-div | 0.592 | 0.153 | 0.58 | 0.628 | 0.0224 | 0.000 | 0.0016 | 0.209 | 5.31 |
| n512-capture-ess-reexpand-sys | 0.573 | 0.154 | 0.80 | 0.725 | 0.0302 | 0.014 | 0.0016 | 0.221 | 6.08 |
| n512-capture-ess-reexpand-div | 0.592 | 0.153 | 0.58 | 0.628 | 0.0224 | 0.000 | 0.0016 | 0.174 | 5.28 |

## Timing run (single worker)

| config | Median s/move | p95 s/move | Max s/move | Truth coverage |
|---|---|---|---|---|
| n32-uniform-above_n-supports-sys | 0.021 | 0.108 | 0.14 | 0.343 |
| n32-uniform-above_n-reexpand-sys | 0.018 | 0.106 | 0.28 | 0.405 |
| n64-uniform-above_n-supports-sys | 0.029 | 0.200 | 0.25 | 0.437 |
| n64-uniform-above_n-reexpand-sys | 0.026 | 0.212 | 0.31 | 0.462 |
| n128-uniform-above_n-supports-sys | 0.029 | 0.371 | 0.49 | 0.423 |
| n128-uniform-above_n-reexpand-sys | 0.025 | 0.414 | 1.05 | 0.505 |
| n256-uniform-above_n-supports-sys | 0.026 | 0.701 | 0.97 | 0.548 |
| n256-uniform-above_n-reexpand-sys | 0.022 | 0.684 | 1.30 | 0.602 |
| n512-uniform-above_n-supports-sys | 0.039 | 1.257 | 2.31 | 0.606 |
| n512-uniform-above_n-reexpand-sys | 0.025 | 1.206 | 1.89 | 0.663 |

