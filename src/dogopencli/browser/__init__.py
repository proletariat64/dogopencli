"""Dedicated-Chrome lifecycle: CDP, authentication probe, locks, login.

Ported from DI at baseline commit 8eb163c6d140554ca167bd50349a85ca224ac342
(``src/diexporter/browser_cdp.py``, ``src/di_common/durable.py`` lock
primitives, ``src/diauth/browser.py``, ``src/diauth/coordination.py``,
``src/diauth/login.py`` and ``scripts/launch_di_chrome.sh``) so dogopencli
runs standalone without an installed DI. Adapted to the payment application
entry, dogopencli configuration, profile, locks and CDP port 9222; DI business
error codes are never used as the payment authentication verdict.
"""
