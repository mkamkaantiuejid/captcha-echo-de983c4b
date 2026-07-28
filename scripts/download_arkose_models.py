#!/usr/bin/env python3
"""Download Arkose FunCaptcha ONNX models into arkose/models/.

Source: haloworker/td-captcha-model-v1 on Hugging Face (~1.4GB total).
Run: python scripts/download_arkose_models.py [--one NAME]
"""
from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = ROOT / "arkose" / "models"
BASE = "https://huggingface.co/haloworker/td-captcha-model-v1/resolve/main/funcaptcha_model"
UA = "Mozilla/5.0 (compatible; captcha-solver/1.0)"

# Files present on HuggingFace (sync with arkose/predict.py _VARIANT_MODELS values)
MODEL_FILES = sorted({
    "conveyor.onnx",
    "coordinatesmatch.onnx",
    "coordinatesmatch_cv.onnx",
    "3d_rollball_objects_v2.onnx",
    "3d_rollball_objects_cv.onnx",
    "penguin.onnx",
    "hopscotch_highsec.onnx",
    "train_coordinates.onnx",
    "train_coordinates_cv.onnx",
    "BrokenJigsawbrokenjigsaw_swap.onnx",
    "shadows.onnx",
    "penguins.onnx",
    "frankenhead.onnx",
    "counting.onnx",
    "knotsCrossesCircle.onnx",
    "hand_number_puzzle.onnx",
    "card.onnx",
    "rockstack.onnx",
    "cardistance.onnx",
    "penguins-icon.onnx",
    "dicematch.onnx",
    "unbentobjects.onnx",
    "dice_pair.onnx",
    "rockstack_v2.onnx",
})


def download(name: str) -> None:
    dest = MODELS_DIR / name
    if dest.exists() and dest.stat().st_size > 1_000_000:
        print(f"[skip] {name}")
        return
    url = f"{BASE}/{name}"
    print(f"[get]  {name} ...")
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=600) as resp, open(tmp, "wb") as out:
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)
    tmp.replace(dest)
    print(f"[ok]   {name} ({dest.stat().st_size // (1024 * 1024)} MB)")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--one", help="Download a single model file (e.g. conveyor.onnx)")
    args = p.parse_args()
    targets = [args.one] if args.one else MODEL_FILES
    failed = []
    for name in targets:
        try:
            download(name)
        except Exception as e:
            print(f"[fail] {name}: {e}", file=sys.stderr)
            failed.append(name)
    if failed:
        print(f"Failed: {failed}", file=sys.stderr)
        return 1
    count = len(list(MODELS_DIR.glob("*.onnx")))
    print(f"Done. {count} model(s) in {MODELS_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
