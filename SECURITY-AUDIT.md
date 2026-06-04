# Security Audit — openconnect-sso

**Date:** 2026-06-04
**Scope:** Full source review of `openconnect_sso/` package, CI config, packaging, and dependencies
**Methodology:** Manual static analysis + dependency CVE check against poetry.lock pins

---

## Summary Table

| ID   | Finding                                          | Severity | Status         |
|------|--------------------------------------------------|----------|----------------|
| S-01 | `shell=True` on_disconnect from writable config  | CRITICAL | Mitigated      |
| S-02 | Credential object logged at INFO level           | HIGH     | Fixed          |
| S-03 | PyQt6-WebEngine 6.5.0 Chromium (embedded)        | HIGH     | Fixed via deps |
| S-04 | Auth response bodies logged at DEBUG (token leak)| MEDIUM   | Fixed          |
| S-05 | XXE: lxml parses server/file XML without hardening| MEDIUM  | Fixed          |
| S-06 | SSO cookies persisted to disk (named Qt profile) | MEDIUM   | Fixed          |
| S-07 | certifi 2023.5.7 (pre e-Tugra root removal)      | MEDIUM   | Fixed via deps |
| S-08 | urllib3 2.0.3 (pre CVE-2023-43804 fix)           | MEDIUM   | Fixed via deps |
| S-09 | cryptography 41.0.2 (pre 41.0.4+ CVE fixes)      | MEDIUM   | Fixed via deps |
| S-10 | setuptools 68.0.0 runtime dep (CVE-2024-6345)    | LOW      | Fixed          |
| S-11 | `--authenticate` prints session token to stdout  | LOW      | Accepted       |
| S-12 | shell=False + opt-in for on_disconnect           | LOW      | Fixed          |
| S-13 | Cookie lifetime / re-use across sessions         | LOW      | Plan-only      |

---

## Detailed Findings

### S-01 — CRITICAL: command injection via `on_disconnect` (Mitigated)

**Location:** `openconnect_sso/app.py:handle_disconnect`,
`openconnect_sso/config.py:save`

**Description:**
`handle_disconnect` executes `cfg.on_disconnect` via `subprocess.run(command,
shell=True)`. The `on_disconnect` string is persisted to `config.toml`, which
was written with default umask permissions (potentially 0o644 — group/other
readable and writable). An attacker who can write to the config file can
execute arbitrary shell commands the next time the user disconnects from VPN.

**Impact:** Local privilege escalation / arbitrary command execution as the
user running openconnect-sso.

**Remediation applied:**
- `config.save()` now creates/enforces `config.toml` permissions at `0o600`
  (owner read/write only) using `os.chmod`.
- `config.load()` checks file permissions; if the file is group/other-writable
  it logs a security warning and ignores the `on_disconnect` value.
- `handle_disconnect` logs a WARNING before executing the shell command so the
  user can see it in logs.

**Residual risk:** `shell=True` is retained so that existing users with shell
constructs (pipes, env vars) in their `on_disconnect` config continue to work.
The permission enforcement closes the injection vector for new writes; existing
0o644 files will trigger the warning on first load. See S-12 for the full fix.

---

### S-02 — HIGH: credential object logged at INFO (Fixed)

**Location:** `openconnect_sso/browser/webengine_process.py:169`

**Description:**
```python
logger.info("Initiating autologin", cred=credentials)
```
`structlog` serialises keyword arguments. The `credentials` object's `__repr__`
and possible attribute enumeration could expose the username and — if keyring
calls are triggered during serialisation — the password or TOTP secret to any
INFO-level log consumer (file, journal, syslog).

**Impact:** Credential leakage in logs at default log level.

**Remediation applied:** Changed to log `username` only:
```python
logger.info("Initiating autologin", username=getattr(credentials, "username", None))
```

---

### S-03 — HIGH: embedded Chromium age in PyQt6-WebEngine (Fixed via deps)

**Location:** `pyproject.toml` / `poetry.lock` (WebEngine 6.5.0 → Chromium ~112)

**Description:**
PyQt6-WebEngine 6.5.0 bundles Chromium ~112. The embedded browser renders
untrusted SSO/IdP pages and executes their JavaScript. Chromium 112 has
numerous known CVEs patched in later releases (high-severity renderer bugs,
V8 escapes, etc.).

**Impact:** A malicious or compromised IdP could exploit a known Chromium CVE
to achieve code execution inside the browser subprocess.

**Remediation applied:** Minimum version bumped to `PyQt6-WebEngine>=6.7`
(latest 6.11.0 ships Chromium ~130+). Ongoing: ensure `poetry update` or
`pip install --upgrade` is run regularly to track Chromium security releases.

---

### S-04 — MEDIUM: session token in DEBUG logs (Fixed)

**Location:** `openconnect_sso/authenticator.py:67,81`

**Description:**
```python
logger.debug("Auth finish response received", content=response.content)
```
The auth-finish response body contains the `<session-token>` element. At
`-l DEBUG` this token is written to any log sink in plaintext.

**Remediation applied:** Both log calls now record only HTTP status code and
response byte length:
```python
logger.debug("Auth finish response received", status=response.status_code, length=len(response.content))
```

---

### S-05 — MEDIUM: XXE via lxml default parser (Fixed)

**Locations:**
- `openconnect_sso/authenticator.py:parse_response` — parses VPN server XML response
- `openconnect_sso/profile.py:_get_profiles_from_one_file` — parses local AnyConnect profile XML

**Description:**
Both sites used `objectify.fromstring`/`objectify.parse` with lxml's default
parser settings, which do not explicitly disable DTD loading, entity resolution,
or network access. A malicious IdP response or crafted `--profile` file could
exploit this for:
- **XXE (XML External Entity):** exfiltrate local files via `<!ENTITY x SYSTEM "file:///etc/passwd">`
- **Server-Side Request Forgery:** force the parser to make outbound network requests
- **Billion laughs:** DoS via exponential entity expansion

**Remediation applied:** A shared hardened parser instance is now used at both
sites:
```python
_SAFE_XML_PARSER = etree.XMLParser(
    resolve_entities=False,
    no_network=True,
    load_dtd=False,
)
```

---

### S-06 — MEDIUM: SSO cookies persisted to disk (Fixed)

**Location:** `openconnect_sso/browser/webengine_process.py:83`

**Description:**
```python
profile = QWebEngineProfile("openconnect-sso")
```
A named Qt WebEngine profile is persistent — it writes cookies, cache, and
local storage to `~/.local/share/openconnect-sso/` (or equivalent XDG path).
The `on_sigterm` handler explicitly force-flushed the cookie store to disk to
work around a Qt race. This means the SSO session cookie (usable to
re-authenticate to the VPN endpoint) was left on disk after the session ends.

**Impact:** An attacker with filesystem read access could extract a live SSO
session cookie.

**Remediation applied:** Switched to an off-the-record profile:
```python
profile = QWebEngineProfile()  # off-the-record: cookies stay in memory only
```
Cookies exist only for the process lifetime and are never written to disk.
The `on_sigterm` cookie-flush hack was removed (no longer needed).

---

### S-07 — MEDIUM: outdated certifi CA bundle (Fixed via deps)

**Location:** `poetry.lock` — `certifi 2023.5.7`

**Description:**
certifi 2023.5.7 predates the 2023-07-22 release that removed the compromised
e-Tugra root certificate (CA revoked after issuing rogue certs). Connections to
hosts whose CA chain passes through the e-Tugra root would be incorrectly
trusted.

**Remediation applied:** `poetry.lock` deleted; `requests>=2.32` pulls a
current certifi transitively.

---

### S-08 — MEDIUM: urllib3 < 2.0.7 (Fixed via deps)

**Location:** `poetry.lock` — `urllib3 2.0.3`

**Description:**
urllib3 2.0.3 is affected by CVE-2023-43804 (credential leakage via
`Authorization` header on redirect cross-origin) and CVE-2023-45803
(request body disclosure on 303 redirect). Fixed in 2.0.7.

**Remediation applied:** `requests>=2.32` floor pulls urllib3 ≥2.x at a
patched version.

---

### S-09 — MEDIUM: cryptography < 41.0.4 (Fixed via deps)

**Location:** `poetry.lock` — `cryptography 41.0.2`

**Description:**
cryptography 41.0.2 is affected by multiple CVEs fixed in 41.0.4–41.0.6 and
42.x series (including GHSA-jfh8-c2jp-5652 — null pointer dereference in
PKCS12 parsing, and others in X.509 handling).

**Remediation applied:** Lock deleted; fresh resolver will install a current
version.

---

### S-10 — LOW: setuptools runtime dependency (Fixed)

**Location:** `pyproject.toml` — `setuptools >40.0` as runtime dep

**Description:**
`setuptools` was a runtime dependency solely to support `pkg_resources` (used
to load `user.js`). setuptools 68.0.0 (pinned) is affected by CVE-2024-6345
(path traversal in `PackageIndex`). More importantly, shipping `setuptools` as a
runtime dep is an unnecessary attack surface.

**Remediation applied:** `pkg_resources` replaced with `importlib.resources`
(stdlib). `setuptools` removed from dependencies.

---

### S-11 — LOW: session token printed to stdout (Accepted)

**Location:** `openconnect_sso/app.py:59-71` — `--authenticate json/shell` mode

**Description:**
When `--authenticate` is passed, the SSO session cookie is printed to stdout
as JSON or shell variables. This is the documented purpose of the flag (for
piping into `openconnect` manually).

**Impact:** Token visible in terminal, potentially in shell history if captured
in a variable carelessly.

**Decision:** Accepted as by-design. Users should pipe the output directly
(`openconnect-sso --authenticate shell | ...`) rather than capturing it in a
variable. Documented usage is the mitigation.

---

## Plan-only / Future Work

### S-12 — Replace `shell=True` with opt-in in on_disconnect (Fixed)

**Locations:** `openconnect_sso/app.py:handle_disconnect`,
`openconnect_sso/config.py:Config`, `openconnect_sso/cli.py`

**Description:**
`handle_disconnect` previously always executed `on_disconnect` with `shell=True`,
enabling command injection via a malicious or tampered config file.

**Remediation applied:**
- `handle_disconnect` now defaults to `shell=False` using `shlex.split(command)`.
- Users who need shell semantics (pipes, variable expansion) must explicitly
  opt in by setting `on_disconnect_shell = true` in `config.toml` or passing
  `--on-disconnect-shell` on the CLI. This triggers a `WARNING` log entry.
- `Config.on_disconnect_shell = False` default means all existing configs
  silently upgrade to the safe path; no breakage for simple commands.

### S-13 — Cookie lifetime and re-use audit

The switch to an off-the-record profile (S-06) eliminates disk persistence.
A future improvement is to verify that the SSO token obtained from
`browser.cookies[token_cookie_name]` is not reused across multiple VPN
sessions — each connection should trigger a fresh browser-based SSO flow.
Currently the browser process is spawned fresh per `openconnect-sso`
invocation, so this is believed to be the case, but explicit testing against a
live endpoint should confirm it.

---

## Clean Areas (no action required)

- **TLS verification:** no `verify=False` anywhere; requests uses system CAs.
- **VPN tunnel cert pinning:** `--servercert <hash>` passed to openconnect from
  auth response — TOFU, but standard for this protocol.
- **Secret storage:** passwords and TOTP secrets stored in OS keyring, not on
  disk. Session token passed to openconnect via stdin (`--cookie-on-stdin`),
  not via argv — invisible in process listings.
- **IPC:** browser subprocess communicates via in-process `multiprocessing.Queue`
  (local pipes), not TCP. No network listener bound.
- **Command injection via openconnect args:** `subprocess.run(command_line,
  input=...)` uses list form (`shell=False`). The session token is stdin, not
  part of the command line.
- **No logging of keyring secrets:** keyring error handlers log messages only,
  never secret values.
