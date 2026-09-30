#!/usr/bin/env python3
"""Offline: `update` exits 6 when api.lovdata.no rejects the machine
(HTTP 403/405, as it does Anthropic's cloud), 1 on other errors, and keeps
using existing local data if there is any.
Run: python tests/lovdata-api/test_blocked.py
"""

import io
import os
import sys
import tempfile
import urllib.error
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

os.environ["LOVDATA_DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "plugins" / "lovdata-api" / "skills" / "lovdata-api" / "scripts"))
import lovdata  # noqa: E402

failures = 0


def check(name, got, want):
    global failures
    if got == want:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name}: got {got!r}, want {want!r}")
        failures += 1


def update_with(exc):
    def boom(api_key=None):
        raise exc
    lovdata.get_package_list = boom
    err = io.StringIO()
    code = None
    with redirect_stderr(err), redirect_stdout(io.StringIO()):
        try:
            lovdata.cmd_update(None, {})
        except SystemExit as e:
            code = e.code
    return code, err.getvalue()


print("update without local data")
code, err = update_with(urllib.error.HTTPError("u", 405, "Request stopped by Varnish IPS", {}, None))
check("405 -> exit 6", code, 6)
check("says BLOKKERT", "BLOKKERT" in err, True)
code, _ = update_with(urllib.error.HTTPError("u", 403, "Forbidden", {}, None))
check("403 -> exit 6", code, 6)
code, err = update_with(urllib.error.URLError("getaddrinfo failed"))
check("network error -> exit 1", code, 1)
check("no BLOKKERT on a network error", "BLOKKERT" in err, False)

print("update with local data from an earlier run")
lovdata.INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
lovdata.INDEX_FILE.write_text("{}", encoding="utf-8")
code, err = update_with(urllib.error.HTTPError("u", 405, "Varnish", {}, None))
check("keeps going (no exit)", code, None)
check("warns the data may be stale", "ADVARSEL" in err, True)

print(f"{failures} failure(s)" if failures else "all ok")
sys.exit(1 if failures else 0)
