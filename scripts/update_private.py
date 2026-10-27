#!/usr/bin/env python3
"""Recalcula scripts/private_snapshot.json a partir de los repos privados.

Solo guarda totales (cantidad de repos, commits por día y bytes por lenguaje):
nunca nombres de repos ni código.

Uso: python scripts/update_private.py REPO1 REPO2 ...
Necesita `gh` con acceso de lectura a esos repos.
"""
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

OWNER = "Jerez20"
TZ_OFFSET = dt.timedelta(hours=-4)  # Santo Domingo
OUT = Path(__file__).with_name("private_snapshot.json")


def api(path, paginate=False):
    cmd = ["gh", "api"] + (["--paginate"] if paginate else []) + [path]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        print(f"  aviso: {path} -> {r.stderr.strip()[:120]}", file=sys.stderr)
        return None
    if paginate:
        return [x for page in json.loads("[" + r.stdout.replace("][", "],[") + "]") for x in page]
    return json.loads(r.stdout)


def main(repos):
    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=365)).strftime("%Y-%m-%dT%H:%M:%SZ")
    langs, days, commits, count, failed = {}, {}, 0, 0, []
    for r in repos:
        meta = api(f"repos/{OWNER}/{r}")
        if not meta:
            failed.append(r)
            continue
        if not meta.get("private") or meta.get("fork"):
            continue
        count += 1
        for k, v in (api(f"repos/{OWNER}/{r}/languages") or {}).items():
            langs[k] = langs.get(k, 0) + v
        cs = api(f"repos/{OWNER}/{r}/commits?author={OWNER}&since={since}&per_page=100", True) or []
        for c in cs:
            when = dt.datetime.fromisoformat(c["commit"]["author"]["date"].replace("Z", "+00:00")) + TZ_OFFSET
            day = when.date().isoformat()
            days[day] = days.get(day, 0) + 1
        commits += len(cs)
    if failed and count == 0:
        sys.exit(f"No se pudo leer ningún repo: {failed}")
    snap = {
        "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "private_repos": count,
        "private_commits": commits,
        "languages": dict(sorted(langs.items(), key=lambda kv: -kv[1])),
        "days": dict(sorted(days.items())),
    }
    old = json.loads(OUT.read_text()) if OUT.exists() else {}
    changed = {k: v for k, v in snap.items() if k != "generated"} != {k: v for k, v in old.items() if k != "generated"}
    if changed:
        OUT.write_text(json.dumps(snap, indent=1) + "\n")
    print(json.dumps({"cambio": changed, "repos": count, "commits": commits, "fallidos": failed}))


if __name__ == "__main__":
    main(sys.argv[1:])
