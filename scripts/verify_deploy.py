#!/usr/bin/env python3
"""Pre-flight checks before deploy. Run: python scripts/verify_deploy.py [--url http://127.0.0.1:8877]"""
import argparse
import importlib
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def check_imports() -> list[str]:
    errors = []
    modules = [
        "fastapi", "uvicorn", "pydantic", "cloakbrowser",
        "PIL", "onnxruntime", "cv2", "numpy", "curl_cffi",
    ]
    for m in modules:
        try:
            importlib.import_module(m)
        except ImportError as e:
            errors.append(f"import {m}: {e}")
    try:
        import server  # noqa: F401
    except Exception as e:
        errors.append(f"import server: {e}")
    return errors


def check_files() -> list[str]:
    errors = []
    required = [
        "server.py",
        "requirements.txt",
        "dashboard/index.html",
        "common/mistral.json.example",
        "common/browser.py",
        "turnstile/solve.py",
        "recaptcha/solve.py",
        "arkose/solve.py",
        "github_signup/harvest.py",
    ]
    optional = [
        "common/apikey.txt",
        "recaptcha/models/recaptcha_cls_s.onnx",
        "aliyun/best.onnx",
        "arkose/models/",
    ]
    for rel in required:
        if not (ROOT / rel).exists():
            errors.append(f"missing required: {rel}")
    warnings = []
    for rel in optional:
        if not (ROOT / rel).exists():
            warnings.append(f"optional missing: {rel}")
    return errors, warnings


def check_http(url: str) -> list[str]:
    errors = []
    try:
        with urllib.request.urlopen(f"{url.rstrip('/')}/health", timeout=10) as r:
            data = json.loads(r.read().decode())
        if data.get("status") != "ok":
            errors.append(f"health: unexpected {data}")
        types = data.get("supported_types", [])
        if len(types) < 11:
            errors.append(f"health: expected 11 solvers, got {len(types)}")
    except Exception as e:
        errors.append(f"health HTTP: {e}")
    try:
        with urllib.request.urlopen(f"{url.rstrip('/')}/dashboard", timeout=10) as r:
            if r.status != 200:
                errors.append(f"dashboard HTTP {r.status}")
    except Exception as e:
        errors.append(f"dashboard: {e}")
    return errors


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--url", default="", help="If set, ping /health and /dashboard")
    args = p.parse_args()

    print("Captcha Solver — deploy verification")
    print("=" * 40)

    imp_err = check_imports()
    file_err, warnings = check_files()

    if imp_err:
        print("\n[FAIL] Imports:")
        for e in imp_err:
            print(f"  - {e}")
    else:
        print("[OK] Python imports")

    if file_err:
        print("\n[FAIL] Files:")
        for e in file_err:
            print(f"  - {e}")
    else:
        print("[OK] Required files")

    if warnings:
        print("\n[WARN] Optional:")
        for w in warnings:
            print(f"  - {w}")

    http_err: list[str] = []
    if args.url:
        http_err = check_http(args.url)
        if http_err:
            print("\n[FAIL] HTTP:")
            for e in http_err:
                print(f"  - {e}")
        else:
            print(f"[OK] HTTP {args.url}")

    failed = bool(imp_err or file_err or (args.url and http_err))
    print("\n" + ("NOT READY — fix errors above" if failed else "READY TO DEPLOY"))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
