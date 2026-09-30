#!/usr/bin/env python3
"""Offline test for pack_for_local.sh: both modes, end to end, with a fake
skill and a file:// URL standing in for raw.githubusercontent.com.
Run: python shared/local-route/test_pack.py   (needs bash, sha256sum, base64, tar)
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACK = HERE / "pack_for_local.sh"
failures = 0


def check(name, cond, detail=""):
    global failures
    print(f"  {'ok  ' if cond else 'FAIL'} {name}" + ("" if cond else f": {detail}"))
    failures += not cond


def bash(cmd, env=None, cwd=None):
    # Via stdin: a 64 KB chunk exceeds the Windows command-line limit.
    return subprocess.run(["bash"], input=cmd, capture_output=True, text=True,
                          env=env, cwd=cwd)


def posix(p: Path) -> str:
    """A path bash on this OS understands (Git Bash on Windows needs /c/...)."""
    s = str(p)
    if os.name == "nt":
        out = subprocess.run(["cygpath", "-u", s], capture_output=True, text=True)
        if out.returncode == 0:
            return out.stdout.strip()
    return s


tmp = Path(tempfile.mkdtemp())
try:
    # Fake repo layout: <repo>/plugins/demo/skills/demo/{SKILL.md,scripts/...}
    repo = tmp / "repo"
    skill = repo / "plugins" / "demo" / "skills" / "demo"
    (skill / "scripts" / "browser").mkdir(parents=True)
    (skill / "SKILL.md").write_text("demo\n")
    (skill / "scripts" / "a.py").write_bytes(b"print('a')\n")
    (skill / "scripts" / "run.sh").write_bytes(b"echo run\n")
    (skill / "scripts" / "browser" / "x.js").write_bytes(b"// browser only\n")
    home = tmp / "home"
    home.mkdir()
    env = {**os.environ, "HOME": posix(home), "CLT_RAW_BASE": repo.as_uri()}

    print("github mode")
    out = bash(f'bash "{posix(PACK)}" "{posix(skill)}"', env=env)
    check("pack exits 0", out.returncode == 0, out.stderr)
    cmd = out.stdout
    check("browser helper not in manifest", "browser/x.js" not in cmd)
    res = bash(cmd, env=env)
    check("local side exits 0", res.returncode == 0, res.stdout + res.stderr)
    ready = [l for l in res.stdout.splitlines() if l.startswith("READY ")]
    check("prints READY <dir>", len(ready) == 1, res.stdout)
    runs = list((home / ".clt").glob("demo-*"))
    check("one run dir under $HOME/.clt", len(runs) == 1, runs)
    if runs:
        r = runs[0]
        check("files copied", (r / "scripts" / "a.py").read_bytes() == b"print('a')\n")
        check(".ready written", (r / ".ready").exists())

    print("github mode, repo moved on (hash mismatch)")
    out = bash(f'bash "{posix(PACK)}" "{posix(skill)}"', env=env)
    (skill / "scripts" / "a.py").write_bytes(b"print('changed upstream')\n")
    res = bash(out.stdout, env=env)
    check("exit 3", res.returncode == 3, res.returncode)
    check("names the file", "scripts/a.py" in res.stdout, res.stdout)

    print("bundle mode")
    shutil.rmtree(home / ".clt")
    out = bash(f'bash "{posix(PACK)}" --bundle "{posix(skill)}"', env=env)
    check("pack exits 0", out.returncode == 0, out.stderr)
    cmds = [l for l in out.stdout.splitlines() if l and not l.startswith("#")]
    check("one command for a small bundle", len(cmds) == 1, len(cmds))
    res = bash("\n".join(cmds), env=env)
    check("local side exits 0", res.returncode == 0, res.stdout + res.stderr)
    runs = list((home / ".clt").glob("demo-*"))
    if runs:
        r = runs[0]
        check("files extracted", (r / "scripts" / "a.py").read_bytes() == b"print('changed upstream')\n")
        check("browser helper left out", not (r / "scripts" / "browser").exists())
        check("no leftovers", not (r / "b.b64").exists() and not (r / "b.tgz").exists())

    print("bundle mode, chunked")
    shutil.rmtree(home / ".clt")
    (skill / "scripts" / "big.bin").write_bytes(os.urandom(120_000))  # incompressible
    out = bash(f'bash "{posix(PACK)}" --bundle "{posix(skill)}"', env=env)
    cmds = [l for l in out.stdout.splitlines() if l and not l.startswith("#")]
    check("split into several commands", len(cmds) >= 3, len(cmds))
    for c in cmds:  # separate shells, as separate device_bash calls would be
        res = bash(c, env=env)
    check("last chunk verifies and extracts", res.returncode == 0 and "READY" in res.stdout,
          res.stdout + res.stderr)

    print("bundle mode, over the hard limit")
    (skill / "scripts" / "huge.bin").write_bytes(os.urandom(800_000))
    out = bash(f'bash "{posix(PACK)}" --bundle "{posix(skill)}"', env=env)
    check("refuses with exit 4", out.returncode == 4, out.returncode)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print(f"{failures} failure(s)" if failures else "all ok")
sys.exit(1 if failures else 0)
