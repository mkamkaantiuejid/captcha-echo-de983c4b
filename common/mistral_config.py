"""Mistral vision configuration — models in common/mistral.json, keys in common/apikey.txt.

No .env required. Environment variables still override models when set:
  RECAPTCHA_MISTRAL_MODEL, HCAPTCHA_MISTRAL_MODEL, ALIYUN_MISTRAL_MODEL
"""
import json
import logging
import os
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_COMMON = Path(__file__).resolve().parent
CONFIG_PATH = _COMMON / "mistral.json"
KEYFILE = _COMMON / "apikey.txt"
DEFAULT_MODEL = "mistral-medium-latest"

_DEFAULTS = {
    "recaptcha_model": DEFAULT_MODEL,
    "hcaptcha_model": DEFAULT_MODEL,
    "aliyun_model": DEFAULT_MODEL,
}

_ENV_OVERRIDES = {
    "recaptcha": "RECAPTCHA_MISTRAL_MODEL",
    "hcaptcha": "HCAPTCHA_MISTRAL_MODEL",
    "aliyun": "ALIYUN_MISTRAL_MODEL",
}

_SOLVER_FIELDS = {
    "recaptcha": "recaptcha_model",
    "hcaptcha": "hcaptcha_model",
    "aliyun": "aliyun_model",
}


def _read_json_config() -> dict[str, str]:
    if not CONFIG_PATH.exists():
        return {}
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        log.warning("mistral config unreadable (%s): %s", CONFIG_PATH, e)
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: str(v) for k, v in data.items() if k in _DEFAULTS and v}


def load_models() -> dict[str, str]:
    """Merged model names from mistral.json with env overrides."""
    merged = dict(_DEFAULTS)
    merged.update(_read_json_config())
    for solver, env_name in _ENV_OVERRIDES.items():
        override = os.getenv(env_name)
        if override:
            merged[_SOLVER_FIELDS[solver]] = override.strip()
    return merged


def get_model(solver: str) -> str:
    """Effective vision model for recaptcha | hcaptcha | aliyun."""
    field = _SOLVER_FIELDS.get(solver)
    if not field:
        raise ValueError(f"unknown mistral solver {solver!r}")
    return load_models()[field]


def count_keys() -> int:
    return len(read_keys())


def read_keys() -> list[str]:
    if not KEYFILE.exists():
        return []
    seen: set[str] = set()
    keys: list[str] = []
    for line in KEYFILE.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s and not s.startswith("#") and s not in seen:
            seen.add(s)
            keys.append(s)
    return keys


def key_hint(key: str) -> str:
    if len(key) <= 4:
        return "…" + key
    return "…" + key[-4:]


def _write_keys(keys: list[str]) -> None:
    KEYFILE.parent.mkdir(parents=True, exist_ok=True)
    KEYFILE.write_text(("\n".join(keys) + "\n") if keys else "", encoding="utf-8")
    try:
        KEYFILE.chmod(0o600)
    except OSError:
        pass
    invalidate_keypools()


def add_keys(raw_keys: list[str]) -> dict[str, int]:
    new = [k.strip() for k in raw_keys if k and k.strip() and not k.strip().startswith("#")]
    if not new:
        raise ValueError("no keys provided")
    merged = read_keys()
    seen = set(merged)
    added = 0
    for k in new:
        if k not in seen:
            merged.append(k)
            seen.add(k)
            added += 1
    _write_keys(merged)
    return {"keys_count": len(merged), "added": added}


def replace_keys(raw_keys: list[str]) -> dict[str, int]:
    seen: set[str] = set()
    keys = [
        k for k in [s.strip() for s in raw_keys if s and s.strip() and not s.strip().startswith("#")]
        if not (k in seen or seen.add(k))
    ]
    _write_keys(keys)
    return {"keys_count": len(keys)}


def remove_key_at(index: int) -> dict[str, int]:
    keys = read_keys()
    if index < 0 or index >= len(keys):
        raise ValueError(f"invalid key index {index}")
    keys.pop(index)
    _write_keys(keys)
    return {"keys_count": len(keys)}


def clear_keys() -> dict[str, int]:
    _write_keys([])
    return {"keys_count": 0}


def keys_configured() -> bool:
    return count_keys() > 0


def save_models(recaptcha_model: str, hcaptcha_model: str, aliyun_model: str) -> dict[str, str]:
    """Write mistral.json (creates parent dir if needed). Returns saved models."""
    data = {
        "recaptcha_model": (recaptcha_model or DEFAULT_MODEL).strip(),
        "hcaptcha_model": (hcaptcha_model or DEFAULT_MODEL).strip(),
        "aliyun_model": (aliyun_model or DEFAULT_MODEL).strip(),
    }
    CONFIG_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    invalidate_keypools()
    return data


def get_status() -> dict[str, Any]:
    models = load_models()
    env_active = {
        solver: bool(os.getenv(env))
        for solver, env in _ENV_OVERRIDES.items()
    }
    return {
        "config_path": str(CONFIG_PATH),
        "keyfile_path": str(KEYFILE),
        "config_exists": CONFIG_PATH.exists(),
        "keyfile_exists": KEYFILE.exists(),
        "keys_count": count_keys(),
        "keys_configured": keys_configured(),
        "key_hints": [{"index": i, "hint": key_hint(k)} for i, k in enumerate(read_keys())],
        "models": {
            "recaptcha": models["recaptcha_model"],
            "hcaptcha": models["hcaptcha_model"],
            "aliyun": models["aliyun_model"],
        },
        "env_override_active": env_active,
        "default_model": DEFAULT_MODEL,
        "setup": [
            "Add Mistral API keys below (dashboard) or edit common/apikey.txt (one key per line)",
            "Set vision models in common/mistral.json or via dashboard Global Setup",
            "Required only for reCAPTCHA/hCaptcha image grids and Aliyun VLM gap detection",
        ],
    }


def invalidate_keypools():
    """Clear cached KeyPools so model / keyfile changes apply on next solve."""
    for mod_name, fn_name in (
        ("recaptcha.solve", "invalidate_keypool_cache"),
        ("hcaptcha.solve", "invalidate_keypool_cache"),
        ("aliyun.gap_vlm", "invalidate_pool"),
    ):
        try:
            import importlib
            mod = importlib.import_module(mod_name)
            getattr(mod, fn_name)()
        except Exception:
            pass
