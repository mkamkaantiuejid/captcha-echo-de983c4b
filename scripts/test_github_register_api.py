#!/usr/bin/env python3
"""GitHub registration — API-first flow.

  1. POST /harvest/github-signup  → browser harvest (DataDome + form scrape + cookies)
  2. curl_cffi POST /signup       → submit with harvested session (no browser typing)

Why not pure /solve + curl GET?
  GitHub blocks curl_cffi GET with DataDome captcha-delivery (403).
  Harvest loads /signup once in CloakBrowser; you replay only the POST via HTTP.

Usage:
  python scripts/test_github_register_api.py \\
    --email mkamkaantiuejid@proton.me \\
    --password '@https://vt.tiktok.com/ZS4J3HSE1/' \\
    --username mkamkaantiuejid
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

from curl_cffi import requests as cffi_requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("github-register-api")

DEFAULT_SOLVER = os.getenv("SOLVER_URL", "http://127.0.0.1:8877")
IMPERSONATE = "chrome131"


def harvest_session(solver_url: str, proxy: str | None, timeout_s: int) -> dict:
    payload: dict = {"timeout_s": timeout_s}
    if proxy:
        payload["proxy"] = proxy

    log.info("POST %s/harvest/github-signup", solver_url)
    req = urllib.request.Request(
        f"{solver_url.rstrip('/')}/harvest/github-signup",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s + 60) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            detail = json.loads(body).get("detail", body)
        except Exception:
            detail = body
        raise RuntimeError(f"Harvest HTTP {e.code}: {detail}") from e


def post_signup(
    harvest: dict,
    email: str,
    password: str,
    username: str,
    proxy: str | None,
    timeout_s: int,
) -> dict:
    form = harvest["form"]
    ua = harvest["user_agent"]
    octo = harvest.get("octocaptcha_token") or harvest.get("datadome_cookie") or ""

    proxies = {"http": proxy, "https": proxy} if proxy else None
    session = cffi_requests.Session(impersonate=IMPERSONATE, proxies=proxies, timeout=timeout_s)

    for c in harvest.get("cookies", []):
        session.cookies.set(
            c["name"], c["value"],
            domain=c.get("domain"),
            path=c.get("path", "/"),
        )

    headers = {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": "https://github.com",
        "Referer": "https://github.com/signup",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    post_data = {
        "authenticity_token": form["authenticity_token"],
        "return_to": form.get("return_to", ""),
        "disable_signup": form.get("disable_signup", "false"),
        "user[email]": email,
        "user[password]": password,
        "user[login]": username,
        "user_signup[country]": "US",
        "user_signup[copilot_opt_in]": "0",
        "user_signup[marketing_consent]": "0",
        "octocaptcha-token": octo,
        "timestamp": form["timestamp"],
        "timestamp_secret": form["timestamp_secret"],
    }
    if form.get("honeypot"):
        post_data[form["honeypot"]] = ""

    action = form["action"]
    log.info("POST %s (curl_cffi, %d cookies)", action, len(harvest.get("cookies", [])))
    resp = session.post(action, data=post_data, headers=headers, allow_redirects=True)

    body_l = (resp.text or "").lower()
    final_url = str(resp.url)
    ok = resp.status_code in (200, 302) and any(
        x in body_l or x in final_url.lower()
        for x in ("verify your email", "check your email", "/account/verify", "welcome to github")
    )

    err = None
    if not ok:
        em = re.search(r'class="[^"]*flash-error[^"]*"[^>]*>([^<]+)', resp.text or "", re.I)
        if em:
            err = em.group(1).strip()
        elif "captcha" in body_l:
            err = "Captcha rejected on POST — TLS/UA mismatch or stale session"
        else:
            err = f"HTTP {resp.status_code}"

    Path("github_signup_post_response.html").write_text((resp.text or "")[:100000], encoding="utf-8")

    return {
        "success": ok,
        "stage": "posted",
        "email": email,
        "username": username,
        "final_url": final_url,
        "http_status": resp.status_code,
        "error": err,
        "harvest_elapsed": harvest.get("elapsed"),
        "method": "harvest-api + curl_cffi-post",
    }


def main():
    p = argparse.ArgumentParser(description="GitHub signup — harvest API + HTTP POST")
    p.add_argument("--email", required=True)
    p.add_argument("--password", required=True)
    p.add_argument("--username", required=True)
    p.add_argument("--solver-url", default=DEFAULT_SOLVER)
    p.add_argument("--proxy", default=os.getenv("GITHUB_PROXY"))
    p.add_argument("--timeout", type=int, default=90)
    args = p.parse_args()

    print("API-first GitHub registration:")
    print(f"  email:    {args.email}")
    print(f"  username: {args.username}")
    print(f"  password: {'*' * len(args.password)} ({len(args.password)} chars)")
    print(f"  solver:   {args.solver_url}")
    print("  flow:     POST /harvest/github-signup -> curl_cffi POST signup")
    print("---")

    try:
        harvest = harvest_session(args.solver_url, args.proxy, args.timeout)
        result = post_signup(harvest, args.email, args.password, args.username, args.proxy, args.timeout)
    except Exception as e:
        print(json.dumps({"success": False, "error": str(e)}, indent=2))
        sys.exit(1)

    print(json.dumps(result, indent=2))
    if result.get("success"):
        print("\n>>> Check email to verify the account.")
    else:
        print("\n>>> Failed - see github_signup_post_response.html")
        sys.exit(1)


if __name__ == "__main__":
    main()
