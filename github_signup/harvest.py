"""Harvest GitHub /signup session — scrape form fields + cookies in one browser pass."""
import asyncio
import logging
import re
import time

import cloakbrowser

from common.browser import browser_kwargs
from datadome.solve import _parse_dd_cookie, _DD_ENDPOINT

log = logging.getLogger(__name__)
_harvest_lock = asyncio.Lock()

SIGNUP_URL = "https://github.com/signup"


def parse_signup_form(html: str) -> dict:
    """Find the email signup form (has octocaptcha-token), not OAuth side forms."""
    forms = re.findall(r"<form[^>]*>[\s\S]*?</form>", html, re.I)
    block = None
    for f in forms:
        if "octocaptcha-token" in f and "user[login]" in f:
            block = f
            break
    if not block:
        m = re.search(
            r'<form[^>]*>[\s\S]*?name="user\[login\]"[\s\S]*?</form>',
            html,
            re.I,
        )
        block = m.group(0) if m else html

    def field(name: str) -> str | None:
        for pat in (
            rf'name="{re.escape(name)}"[^>]*value="([^"]*)"',
            rf'value="([^"]*)"[^>]*name="{re.escape(name)}"',
        ):
            hit = re.search(pat, block, re.I)
            if hit:
                return hit.group(1)
        return None

    honeypot = None
    hm = re.search(r'name="(required_field_[^"]+)"', block)
    if hm:
        honeypot = hm.group(1)

    action_m = re.search(r'<form[^>]*action="([^"]*)"', block, re.I)
    action = action_m.group(1) if action_m else "/signup"
    if action.startswith("/"):
        action = "https://github.com" + action
    if "signup" not in action.lower() and "sessions" not in action.lower():
        action = "https://github.com/signup"

    return {
        "action": action,
        "authenticity_token": field("authenticity_token"),
        "timestamp": field("timestamp"),
        "timestamp_secret": field("timestamp_secret"),
        "honeypot": honeypot,
        "return_to": field("return_to") or "",
        "disable_signup": field("disable_signup") or "false",
    }


async def harvest_github_signup(proxy: str | None = None, timeout_s: int = 90) -> dict:
    """Load /signup in CloakBrowser, intercept DataDome, scrape anti-bot form fields."""
    t0 = time.monotonic()
    captured_dd: dict = {"cookie": None, "raw_json": None}

    async with _harvest_lock:
        async with await cloakbrowser.launch_async(**browser_kwargs("HCAPTCHA", proxy=proxy)) as browser:
            ctx = await browser.new_context(viewport={"width": 1280, "height": 900})
            page = await ctx.new_page()

            async def on_response(resp):
                if _DD_ENDPOINT in resp.url and resp.request.method == "POST":
                    try:
                        body = await resp.text()
                        captured_dd["raw_json"] = body[:500]
                        parsed = _parse_dd_cookie(body)
                        if parsed.get("value"):
                            captured_dd["cookie"] = parsed["value"]
                            log.info("DataDome cookie captured on signup page")
                    except Exception as e:
                        log.warning("datadome intercept: %s", e)

            page.on("response", lambda r: asyncio.create_task(on_response(r)))

            try:
                await page.goto(SIGNUP_URL, wait_until="domcontentloaded", timeout=60000)
            except Exception as e:
                return {
                    "success": False,
                    "error": f"goto signup failed: {e}",
                    "elapsed": round(time.monotonic() - t0, 1),
                }

            deadline = time.monotonic() + min(timeout_s, 45)
            while time.monotonic() < deadline and not captured_dd["cookie"]:
                await asyncio.sleep(0.5)

            html = await page.content()
            final_url = page.url
            ua = await page.evaluate("() => navigator.userAgent")

            if "captcha-delivery" in html.lower() and not captured_dd["cookie"]:
                return {
                    "success": False,
                    "error": "DataDome interactive challenge — silent pass failed (try residential proxy)",
                    "final_url": final_url,
                    "raw_json": captured_dd["raw_json"],
                    "elapsed": round(time.monotonic() - t0, 1),
                }

            form = parse_signup_form(html)
            if not form.get("authenticity_token") or not form.get("timestamp_secret"):
                return {
                    "success": False,
                    "error": "Could not scrape authenticity_token / timestamp_secret",
                    "final_url": final_url,
                    "form": form,
                    "elapsed": round(time.monotonic() - t0, 1),
                }

            cookies = await ctx.cookies()
            cookie_list = [
                {"name": c["name"], "value": c["value"], "domain": c["domain"], "path": c.get("path", "/")}
                for c in cookies
            ]

            return {
                "success": True,
                "user_agent": ua,
                "cookies": cookie_list,
                "cookie_header": "; ".join(f"{c['name']}={c['value']}" for c in cookie_list),
                "datadome_cookie": captured_dd["cookie"],
                "octocaptcha_token": captured_dd["cookie"],
                "form": form,
                "final_url": final_url,
                "proxy": proxy,
                "method": "browser-harvest",
                "elapsed": round(time.monotonic() - t0, 1),
                "warning": "Replay signup POST with curl_cffi using this user_agent + cookies + proxy.",
            }
