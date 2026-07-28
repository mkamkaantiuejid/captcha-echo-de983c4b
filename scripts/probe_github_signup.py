"""Probe GitHub signup page for form fields and network endpoints."""
import asyncio
import json
import re
from cloakbrowser import launch_async

SIGNUP = "https://github.com/signup"


async def main():
    posts = []
    browser = await launch_async(headless=False, humanize=True)
    try:
        ctx = await browser.new_context()
        page = await ctx.new_page()

        async def on_request(req):
            if req.method == "POST" and "github" in req.url:
                posts.append({"url": req.url, "post": req.post_data})

        page.on("request", on_request)

        await page.goto(SIGNUP, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(5)

        html = await page.content()
        inputs = await page.evaluate("""() => {
            return [...document.querySelectorAll('input, button[type=submit]')].map(el => ({
                name: el.name, id: el.id, type: el.type, placeholder: el.placeholder,
                hidden: el.type === 'hidden', value: el.type === 'hidden' ? el.value?.slice(0,80) : ''
            }));
        }""")

        scripts = re.findall(r'timestamp_secret|honeypot|octocaptcha|signup', html, re.I)
        print("INPUTS:", json.dumps(inputs, indent=2))
        print("KEYWORDS in page:", sorted(set(scripts)))
        print("POST captures:", json.dumps(posts[:5], indent=2)[:2000])
        await page.screenshot(path="github_signup_probe.png", full_page=True)
        print("screenshot: github_signup_probe.png")
        await asyncio.sleep(3)
    finally:
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
