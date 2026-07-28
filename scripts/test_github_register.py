#!/usr/bin/env python3
"""GitHub signup — full browser flow with retries until success.

Usage:
  python scripts/test_github_register.py \\
    --email mkamkaantiuejid@proton.me \\
    --password '@https://vt.tiktok.com/ZS4J3HSE1/' \\
    --username mkamkaantiuejid
"""
import argparse
import asyncio
import json
import logging
import os
import random
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cloakbrowser
from common.browser import browser_kwargs
from datadome.solve import _parse_dd_cookie, _DD_ENDPOINT

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("github-register")

SIGNUP_URL = "https://github.com/signup"
# Email signup form — NOT OAuth google form
SIGNUP_FORM = "form:has(input[name='octocaptcha-token'])"


async def _blur_and_wait_username_ok(page, form, timeout_s: float = 20) -> bool:
    """GitHub only validates username on blur — click empty space, wait for green check."""
    login = form.locator("input[name='user[login]']").first

    # Blur username field (fires availability AJAX)
    await form.evaluate(
        """(form) => {
            const input = form.querySelector("input[name='user[login]']");
            if (input) {
                input.dispatchEvent(new Event('input', { bubbles: true }));
                input.blur();
                input.dispatchEvent(new Event('blur', { bubbles: true }));
            }
        }"""
    )
    # Click empty space on the form card (user tip: needed for green check)
    box = await form.bounding_box()
    if box:
        await page.mouse.click(box["x"] + box["width"] - 20, box["y"] + 20)
    else:
        await page.mouse.click(400, 280)
    await asyncio.sleep(0.6)

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        state = await form.evaluate(
            """(form) => {
                const input = form.querySelector("input[name='user[login]']");
                if (!input) return { ok: false, why: 'no input' };
                const root = input.closest('.FormControl') || input.parentElement?.parentElement;
                const caption = root?.querySelector('.FormControl-caption--success')
                    || root?.querySelector('[class*="success"]');
                const errCaption = root?.querySelector('.FormControl-caption--error');
                const ariaInvalid = input.getAttribute('aria-invalid');
                const hasError = ariaInvalid === 'true' || !!errCaption;
                const hasSuccess = !!caption
                    || ariaInvalid === 'false'
                    || !!root?.querySelector('svg.octicon-check');
                return {
                    ok: hasSuccess && !hasError,
                    hasSuccess, hasError, ariaInvalid,
                };
            }"""
        )
        if state.get("ok"):
            log.info("Username validation green")
            return True
        if state.get("hasError"):
            log.warning("Username validation error (aria=%s)", state.get("ariaInvalid"))
            return False
        await asyncio.sleep(0.4)

    log.warning("Username validation did not turn green within %.0fs", timeout_s)
    return False


def _is_success(url: str, html: str) -> bool:
    u, h = url.lower(), html.lower()
    return any(x in u or x in h for x in (
        "account_verifications", "account/verify", "verify your email",
        "check your email", "welcome to github",
    ))


async def _attempt(email: str, password: str, username: str, proxy: str | None, timeout_s: int) -> dict:
    t0 = time.monotonic()
    captured_dd: dict = {"cookie": None}

    async with await cloakbrowser.launch_async(**browser_kwargs("HCAPTCHA", proxy=proxy)) as browser:
        ctx = await browser.new_context(viewport={"width": 1280, "height": 900})
        page = await ctx.new_page()

        async def on_response(resp):
            if _DD_ENDPOINT in resp.url and resp.request.method == "POST":
                try:
                    parsed = _parse_dd_cookie(await resp.text())
                    if parsed.get("value"):
                        captured_dd["cookie"] = parsed["value"]
                except Exception:
                    pass

        page.on("response", lambda r: asyncio.create_task(on_response(r)))

        await page.goto(SIGNUP_URL, wait_until="domcontentloaded", timeout=60000)

        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and not captured_dd["cookie"]:
            await asyncio.sleep(0.5)

        html = await page.content()
        if "captcha-delivery" in html.lower() and not captured_dd["cookie"]:
            return {
                "success": False,
                "error": "DataDome interactive challenge (try residential proxy)",
                "elapsed": round(time.monotonic() - t0, 1),
            }

        form = page.locator(SIGNUP_FORM).first
        await form.wait_for(state="visible", timeout=20000)

        for sel, val in (
            ("input[name='user[email]']", email),
            ("input[name='user[password]']", password),
        ):
            loc = form.locator(sel).first
            await loc.wait_for(state="visible", timeout=10000)
            await loc.fill(val)
            await asyncio.sleep(0.3)

        user_loc = form.locator("input[name='user[login]']").first
        await user_loc.wait_for(state="visible", timeout=10000)
        await user_loc.fill(username)
        await asyncio.sleep(0.3)

        username_ok = await _blur_and_wait_username_ok(page, form)
        if not username_ok:
            return {
                "success": False,
                "error": "Username did not validate (taken or blur check failed)",
                "username": username,
                "elapsed": round(time.monotonic() - t0, 1),
            }

        if captured_dd["cookie"]:
            await form.evaluate(
                """(form, token) => {
                    const o = form.querySelector("input[name='octocaptcha-token']");
                    if (o) { o.value = token; o.dispatchEvent(new Event('input', {bubbles: true})); }
                }""",
                captured_dd["cookie"],
            )

        await form.evaluate(
            """(form) => {
                for (const el of form.querySelectorAll("input[name^='required_field_']")) el.value = '';
            }"""
        )

        filled = await form.evaluate("""(form) => ({
            email: form.querySelector("input[name='user[email]']")?.value,
            username: form.querySelector("input[name='user[login]']")?.value,
        })""")
        log.info("Filled email=%s username=%s", filled.get("email"), filled.get("username"))

        await page.screenshot(path="github_signup_before_submit.png")

        submit = form.locator("button[type='submit']").first
        # Wait until submit is enabled (GitHub disables until username is green)
        try:
            await submit.wait_for(state="visible", timeout=10000)
            for _ in range(40):
                disabled = await submit.evaluate("el => el.disabled")
                if not disabled:
                    break
                await asyncio.sleep(0.25)
        except Exception as e:
            log.warning("Submit button wait: %s", e)

        log.info("Clicking Create account")
        try:
            async with page.expect_navigation(wait_until="domcontentloaded", timeout=timeout_s * 1000):
                await submit.click()
        except Exception as e:
            log.warning("Navigation: %s", e)

        await asyncio.sleep(2)
        final_url = page.url
        content = await page.content()
        await page.screenshot(path="github_signup_after_submit.png")

        ok = _is_success(final_url, content)
        err = None
        if not ok:
            m = re.search(r'class="[^"]*flash-error[^"]*"[^>]*>([^<]+)', content, re.I)
            if m:
                err = re.sub(r"\s+", " ", m.group(1)).strip()
            elif "already" in content.lower():
                err = "Email or username already in use"
            elif "captcha" in content.lower():
                err = "Captcha rejected"
            else:
                err = f"Unexpected page: {final_url}"

        return {
            "success": ok,
            "email": email,
            "username": username,
            "final_url": final_url,
            "error": err,
            "elapsed": round(time.monotonic() - t0, 1),
        }


async def register_until_success(
    email: str,
    password: str,
    username: str,
    proxy: str | None,
    timeout_s: int,
    max_attempts: int,
) -> dict:
    base_username = username
    last = None
    for attempt in range(1, max_attempts + 1):
        u = base_username if attempt == 1 else f"{base_username}{random.randint(10, 99)}"
        log.info("Attempt %d/%d username=%s", attempt, max_attempts, u)
        last = await _attempt(email, password, u, proxy, timeout_s)
        if last.get("success"):
            last["attempts"] = attempt
            return last
        err = (last.get("error") or "").lower()
        if "already" in err or "not available" in err or "taken" in err:
            log.warning("Username conflict — retrying with new username")
            continue
        if "datadome" in err or "captcha" in err or "proxy" in err:
            await asyncio.sleep(3)
            continue
        log.warning("Failed: %s", last.get("error"))
        await asyncio.sleep(2)
    last = last or {"success": False, "error": "max attempts exhausted"}
    last["attempts"] = max_attempts
    return last


def main():
    p = argparse.ArgumentParser(description="GitHub browser signup — retry until success")
    p.add_argument("--email", required=True)
    p.add_argument("--password", required=True)
    p.add_argument("--username", required=True)
    p.add_argument("--proxy", default=os.getenv("GITHUB_PROXY"))
    p.add_argument("--timeout", type=int, default=90)
    p.add_argument("--max-attempts", type=int, default=5)
    args = p.parse_args()

    # Optional: load .proxy.env from repo root (GITHUB_PROXY=...)
    proxy_file = Path(__file__).resolve().parent.parent / ".proxy.env"
    if not args.proxy and proxy_file.is_file():
        for line in proxy_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("GITHUB_PROXY="):
                args.proxy = line.split("=", 1)[1].strip()
                break

    print("Browser registration (headed):")
    print(f"  email:    {args.email}")
    print(f"  username: {args.username}")
    print(f"  password: {'*' * len(args.password)} ({len(args.password)} chars)")
    print(f"  retries:  {args.max_attempts}")
    if args.proxy:
        print(f"  proxy:    {args.proxy.split('@')[-1] if '@' in args.proxy else 'set'}")
    print("---")

    result = asyncio.run(
        register_until_success(
            args.email, args.password, args.username,
            args.proxy, args.timeout, args.max_attempts,
        )
    )
    print(json.dumps(result, indent=2))
    if result.get("success"):
        print("\n>>> Registered! Check email to verify.")
    else:
        print("\n>>> Failed after retries. See github_signup_after_submit.png")
    sys.exit(0 if result.get("success") else 1)


if __name__ == "__main__":
    main()
