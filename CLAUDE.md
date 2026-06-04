# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Setup (Python 3.12+ required)
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[test]"

# Tests (Qt WebEngine needs a display)
xvfb-run -a pytest
pytest tests/test_hostprofile.py          # no display needed
xvfb-run -a pytest tests/test_browser.py  # requires xvfb + libegl1 libgl1 libxkbcommon0

# Single test
xvfb-run -a pytest tests/test_browser.py::test_browser_reports_loaded_url

# Lint / format
black .
flake8
pre-commit run -a

# Build wheel
python -m build
```

## Architecture

openconnect-sso is a CLI wrapper that performs Cisco AnyConnect SSO authentication via an embedded Qt WebEngine browser, then hands off the session token to `openconnect` running under `sudo`/`doas`.

### Auth flow

```
cli.py → app.run() → asyncio.run(_run())
  → authenticator.py: POST to VPN endpoint → parse XML → get SSO login URL
  → saml_authenticator.py: spawn browser subprocess → wait for token cookie
  → authenticator.py: POST auth-finish with token → get session-token
  → app.run_openconnect(): sudo openconnect --cookie-on-stdin
```

### Process boundary

The Qt WebEngine browser runs in a **separate `multiprocessing.Process`** (`browser/webengine_process.py`). Communication is via `multiprocessing.Queue`:
- Main → browser: `StartupInfo(url, credentials)`
- Browser → main: `Url(url)` and `SetCookie(name, value)` messages

`browser/browser.py` is the async wrapper that owns the subprocess and exposes `authenticate_at()` / `page_loaded()` / `cookies`.

### Key files

| File | Role |
|------|------|
| `cli.py` | argparse entry point |
| `app.py` | orchestration, `asyncio.run`, `run_openconnect`, `handle_disconnect` |
| `authenticator.py` | HTTP auth flow, lxml XML parsing, `AuthRequestResponse`/`AuthCompleteResponse` |
| `saml_authenticator.py` | drives `Browser` through the SAML login page |
| `browser/browser.py` | async `Browser` wrapper around the subprocess |
| `browser/webengine_process.py` | PyQt6 WebEngine subprocess; injects `user.js`, harvests cookies |
| `config.py` | TOML config + attrs models (`Config`, `HostProfile`, `Credentials`) |
| `profile.py` | AnyConnect XML profile parser |

### Config & credentials

- Config stored at `$XDG_CONFIG_HOME/openconnect-sso/config.toml` (enforced `0600`)
- Passwords/TOTP secrets stored in OS keyring via `keyring`; never written to disk
- Session token passed to `openconnect` via stdin (`--cookie-on-stdin`), not argv

### on_disconnect

`cfg.on_disconnect` runs on VPN disconnect. Default: `shell=False` via `shlex.split`. Set `on_disconnect_shell = true` in config.toml (or pass `--on-disconnect-shell`) to enable `shell=True` — only for commands needing pipes/expansion.

### XML parsing

Both `authenticator.py` and `profile.py` use `objectify.makeparser(resolve_entities=False, no_network=True, load_dtd=False)` — must use `objectify.makeparser()` not `etree.XMLParser()`, otherwise `objectify` attribute access (e.g. `xml.auth`) breaks.

### Qt/display notes

- WebEngine profile is off-the-record (`QWebEngineProfile()`) — cookies memory-only
- `DisplayMode.HIDDEN` adds `-platform minimal` to Qt argv (no real display needed for hidden mode, but tests still need xvfb)
- `user.js` is package data loaded via `importlib.resources`
