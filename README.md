# openconnect-sso

Wrapper script for OpenConnect supporting Azure AD (SAMLv2) authentication
to Cisco SSL-VPNs

[![Tests Status
](https://github.com/SergiiKhrystenko/openconnect-sso/workflows/Tests/badge.svg?branch=master&event=push)](https://github.com/SergiiKhrystenko/openconnect-sso/actions?query=workflow%3ATests+branch%3Amaster+event%3Apush)

## Installation

### Using pip/pipx

Requires **Python 3.12 or newer** on **Linux**.

> **Note:** This is a maintained fork. Install directly from GitHub — the PyPI
> package is the unmaintained upstream version.

Install via pipx (recommended for isolated installs):

```shell
pipx install git+https://github.com/SergiiKhrystenko/openconnect-sso.git
```

Or via pip into a virtualenv of your choice:

```shell
pip install git+https://github.com/SergiiKhrystenko/openconnect-sso.git
```

### Windows *(EXPERIMENTAL)*

Install with [pip/pipx](#using-pippipx) and be sure that you have `sudo` and `openconnect`
executable commands in your PATH.

## Usage

If you want to save credentials and get them automatically
injected in the web browser:

```shell
$ openconnect-sso --server vpn.server.com/group --user user@domain.com
Password (user@domain.com):
[info     ] Authenticating to VPN endpoint ...
```

User credentials are automatically saved to the users login keyring (if
available).

If you already have Cisco AnyConnect set-up, then `--server` argument is
optional. Also, the last used `--server` address is saved between sessions so
there is no need to always type in the same arguments:

```shell
$ openconnect-sso
[info     ] Authenticating to VPN endpoint ...
```

Configuration is saved in `$XDG_CONFIG_HOME/openconnect-sso/config.toml`. On
typical Linux installations it is located under
`$HOME/.config/openconnect-sso/config.toml`

For CISCO-VPN and TOTP the following seems to work by tuning the config.toml
and removing the default "submit"-action to the following:

```
[[auto_fill_rules."https://*"]]
selector = "input[data-report-event=Signin_Submit]"
action = "click"

[[auto_fill_rules."https://*"]]
selector = "input[type=tel]"
fill = "totp"
```

### Adding custom `openconnect` arguments

Sometimes you need to add custom `openconnect` arguments. One situation can be if you get similar error messages:

```shell
Failed to read from SSL socket: The transmitted packet is too large (EMSGSIZE).
Failed to recv DPD request (-5)
```

or:

```shell
Detected MTU of 1370 bytes (was 1406)
```

Generally, you can add `openconnect` arguments after the `--` separator. This is called _"positional arguments"_. The
solution of the previous errors is setting `--base-mtu` e.g.:

```shell
openconnect-sso --server vpn.server.com/group --user user@domain.com -- --base-mtu=1370
#                                                          separator ^^|^^^^^^^^^^^^^^^ openconnect args
```

## Development

Requires Python 3.12 or newer. Set up a virtual environment and install in editable mode:

```shell
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[test]"
```

Run tests (Qt WebEngine requires a display; `xvfb-run` provides one on headless systems):

```shell
xvfb-run -a pytest
```

Or use the included `Makefile`. Type `make help` to see available targets.
