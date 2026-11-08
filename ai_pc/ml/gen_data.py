"""Generate a synthetic training set for the risk model.

**Honest hackathon disclosure:** the *training data* is synthetic — sampled
across realistic sensor ranges and labeled by the documented ``heuristic()``
(plus small Gaussian noise).  At *inference* time the model runs on **real**
sensor values from the BME + GP2Y1010.  This is a deliberate, disclosed choice:
it lets us ship a real NPU-quantized model without a labeled field dataset,
while the same heuristic remains the runtime fallback.

Features are emitted in the canonical ``FEATURE_ORDER``.

Run:
    python -m ai_pc.ml.gen_data --n 40000 --out ai_pc/ml/data/train.npz
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from ai_pc.ml.heuristic import FEATURE_ORDER, heuristic

_DEFAULT_OUT = Path(__file__).resolve().parent / "data" / "train.npz"


def sample(n: int, seed: int = 42):
    rng = np.random.default_rng(seed)
    pm25 = rng.uniform(0, 400, n)
    pm10 = np.clip(pm25 * rng.uniform(1.2, 1.6, n), 0, 500)
    temp = rng.uniform(5, 45, n)
    humidity = rng.uniform(10, 95, n)
    voc = rng.uniform(0, 500, n)
    pressure = rng.uniform(990, 1030, n)
    pm25_rate = rng.normal(0, 8, n)          # +/- per minute
    hum_rate = rng.normal(0, 4, n)
    temp_rate = rng.normal(0, 1.5, n)
    severity = rng.integers(0, 3, n).astype(float)
    sensitivity = rng.uniform(0, 1, n)

    X = np.stack([pm25, pm10, temp, humidity, voc, pressure,
                  pm25_rate, hum_rate, temp_rate, severity, sensitivity], axis=1)
    assert X.shape[1] == len(FEATURE_ORDER)

    # label each row with the heuristic + noise, clamp to [0,100]
    y = np.empty(n, dtype=np.float32)
    for i in range(n):
        score, _ = heuristic({k: float(v) for k, v in zip(FEATURE_ORDER, X[i])})
        y[i] = score
    y = np.clip(y + rng.normal(0, 2.5, n), 0, 100).astype(np.float32)
    return X.astype(np.float32), y


def main() -> None:
    p = argparse.ArgumentParser(description="generate synthetic risk training data")
    p.add_argument("--n", type=int, default=40000)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out", type=Path, default=_DEFAULT_OUT)
    args = p.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    X, y = sample(args.n, args.seed)
    np.savez_compressed(args.out, X=X, y=y, feature_order=np.array(FEATURE_ORDER))
    print(f"wrote {args.out}  X={X.shape}  y={y.shape}  "
          f"(SYNTHETIC labels via heuristic; model runs on REAL sensors at inference)")


if __name__ == "__main__":
    main()
