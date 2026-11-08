"""Train the risk MLP and export ``risk_fp32.onnx`` (fixed shape [1,11], opset 17).

Model: 11 -> 32 -> 16 -> 1, ReLU, MSE, Adam.  Inputs are standardized; the
scaler (mean/std per feature) is written to ``models/scaler.json`` and applied
at inference by ``orchestrator/inference.py`` (kept out of the graph so the same
ONNX works with or without the scaler).

Run (needs torch + onnx):
    python -m ai_pc.ml.gen_data
    python -m ai_pc.ml.train_risk
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

_HERE = Path(__file__).resolve().parent
_DATA = _HERE / "data" / "train.npz"
_MODELS = _HERE / "models"
_FP32 = _MODELS / "risk_fp32.onnx"
_SCALER = _MODELS / "scaler.json"


def _load():
    if not _DATA.is_file():
        raise SystemExit(f"missing {_DATA}; run `python -m ai_pc.ml.gen_data` first")
    d = np.load(_DATA, allow_pickle=True)
    return d["X"].astype(np.float32), d["y"].astype(np.float32)


def main() -> None:
    p = argparse.ArgumentParser(description="train risk MLP -> risk_fp32.onnx")
    p.add_argument("--epochs", type=int, default=40)
    p.add_argument("--batch", type=int, default=256)
    p.add_argument("--lr", type=float, default=1e-3)
    args = p.parse_args()

    import torch
    import torch.nn as nn

    X, y = _load()
    mean = X.mean(axis=0)
    std = X.std(axis=0)
    std[std == 0] = 1.0
    Xs = (X - mean) / std

    _MODELS.mkdir(parents=True, exist_ok=True)
    _SCALER.write_text(json.dumps({"mean": mean.tolist(), "std": std.tolist(),
                                   "feature_order_len": int(X.shape[1])}, indent=2),
                       encoding="utf-8")

    device = "cuda" if torch.cuda.is_available() else "cpu"
    Xt = torch.tensor(Xs, dtype=torch.float32, device=device)
    yt = torch.tensor(y, dtype=torch.float32, device=device).unsqueeze(1)

    model = nn.Sequential(
        nn.Linear(X.shape[1], 32), nn.ReLU(),
        nn.Linear(32, 16), nn.ReLU(),
        nn.Linear(16, 1),
    ).to(device)

    opt = torch.optim.Adam(model.parameters(), lr=args.lr)
    loss_fn = nn.MSELoss()
    n = Xt.shape[0]

    model.train()
    for epoch in range(args.epochs):
        perm = torch.randperm(n, device=device)
        total = 0.0
        for i in range(0, n, args.batch):
            idx = perm[i:i + args.batch]
            opt.zero_grad()
            out = model(Xt[idx])
            loss = loss_fn(out, yt[idx])
            loss.backward()
            opt.step()
            total += loss.item() * idx.numel()
        if (epoch + 1) % 5 == 0 or epoch == 0:
            print(f"epoch {epoch+1:>3}/{args.epochs}  mse={total/n:.3f}")

    # export to ONNX with a fixed [1, F] input, opset 17
    model.eval().to("cpu")
    dummy = torch.zeros(1, X.shape[1], dtype=torch.float32)
    torch.onnx.export(
        model, dummy, str(_FP32),
        input_names=["features"], output_names=["risk"],
        opset_version=17, dynamo=False,
    )
    print(f"exported {_FP32} (input [1,{X.shape[1]}], opset 17)")
    print(f"wrote scaler {_SCALER}")
    print("next: quantize on an x64 machine -> `python -m ai_pc.ml.quantize`")


if __name__ == "__main__":
    main()
