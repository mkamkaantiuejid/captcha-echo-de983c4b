# Deployment

Production checklist for the captcha-solver HTTP sidecar.

## Quick verify (before deploy)

```bash
pip install -r requirements.txt
python -m playwright install chromium
python scripts/verify_deploy.py
python server.py
# in another shell:
python scripts/verify_deploy.py --url http://127.0.0.1:8877
```

## Linux production (recommended)

```bash
sudo bash deploy/install.sh
sudo systemctl start captcha-solver.service
sudo systemctl status captcha-solver.service
curl http://127.0.0.1:8877/health
```

The systemd unit runs under **Xvfb** with `BROWSER_HEADLESS=0` (headed in a virtual display). No `.env` file is required by default.

## Windows / dev

```bat
pip install -r requirements.txt
python -m playwright install chromium
copy common\mistral.json.example common\mistral.json
copy common\apikey.example.txt common\apikey.txt
run.bat
```

Open http://127.0.0.1:8877/dashboard → **Global Setup** to configure Mistral models.

## Required configuration

| What | When |
|------|------|
| Nothing | Turnstile, reCAPTCHA v3/invisible, Cloudflare, DataDome, etc. work without Mistral |
| `common/apikey.txt` | reCAPTCHA/hCaptcha **image** challenges |
| `common/mistral.json` | Vision model names (defaults ship in `mistral.json.example`) |

```bash
copy common/apikey.example.txt common/apikey.txt   # add keys, chmod 600
copy common/mistral.json.example common/mistral.json
```

Or use dashboard **Global Setup** / `PUT /config/mistral` for models.

## Optional models

| Path | Solver | If missing |
|------|--------|------------|
| `recaptcha/models/recaptcha_cls_s.onnx` | reCAPTCHA hybrid | Falls back to Mistral |
| `aliyun/best.onnx` | Aliyun YOLO gap | Falls back to cv2 |
| `arkose/models/*.onnx` (~1.4GB) | Arkose FunCaptcha | Arkose solve fails |

## Optional environment overrides

For systemd or shell only — **not required**. See `deploy/env.optional.example` (`PORT`, `SOLVER_PUBLIC_URL`, `TURNSTILE_GEOIP`, etc.).

Mistral models are **not** set via `.env`; use `common/mistral.json` or the dashboard.

## Public exposure

The service has **no built-in auth**. For public deploy:

1. Set `SOLVER_PUBLIC_URL` via optional `.env` or systemd `Environment=`
2. Put **Caddy/nginx** in front with Bearer token on `/solve`, `/status`, `/logs`, `/harvest/*`, `/config/*`
3. Allow public: `/health`, `/docs`, `/redoc`, `/dashboard`, `/openapi.json`

See main README “Remote access” section.

## API endpoints

| Endpoint | Description |
|----------|-------------|
| `POST /solve` | Solve captcha (11 types) |
| `POST /harvest/github-signup` | GitHub signup session harvest |
| `GET /config/mistral` | Mistral setup status |
| `PUT /config/mistral` | Save vision models |
| `POST /config/mistral/keys` | Append API keys |
| `PUT /config/mistral/keys` | Replace all API keys |
| `DELETE /config/mistral/keys` | Clear or remove one key (`?index=`) |
| `GET /health` | Liveness |
| `GET /status` | Running tasks + browser mode |
| `GET /dashboard` | Web UI + tutorials |

## Proxy

Per-request only: `"proxy": "http://user:pass@host:port"` in JSON body.  
Cookie/token replay must use the **same proxy IP** + returned `user_agent`.

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `No module named cloakbrowser` | `pip install -r requirements.txt` |
| Browser won't start | `python -m playwright install chromium` |
| Headless detected / fails | `BROWSER_HEADLESS=0` + Xvfb on Linux |
| reCAPTCHA/hCaptcha image 500 | Add keys to `common/apikey.txt` |
| Arkose fails | Download models to `arkose/models/` |

## Scripts (not part of core service)

| Script | Purpose |
|--------|---------|
| `scripts/verify_deploy.py` | Pre-flight checks |
| `scripts/test_github_register_api.py` | GitHub signup via API harvest + curl_cffi |
| `scripts/test_github_register.py` | GitHub signup full browser |

These are **caller examples**, not required on the server.
