#!/usr/bin/env python3
"""Genera las tarjetas pixel art del perfil con datos reales de GitHub.

Uso:
  GH_TOKEN=... python scripts/generate.py            # datos reales (GitHub Actions)
  python scripts/generate.py --mock scripts/mock.json  # vista previa local
"""
import base64, datetime as dt, json, os, random, sys, unicodedata, urllib.request
from html import escape
from pathlib import Path

USER = os.environ.get("PROFILE_USER", "Jerez20")
SHOW_PRIVATE = os.environ.get("SHOW_PRIVATE_REPOS", "false").lower() == "true"
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets"
FONT_B64 = base64.b64encode((OUT / "fonts" / "PressStart2P.woff2").read_bytes()).decode()

# ── Paleta ────────────────────────────────────────────────────────────
# Tomada de la foto de perfil: azul noche, brillo cian de pantalla, lavanda y rubor rosado.
BG, BG2, PANEL = "#091a25", "#0e2432", "#12374a"
LINE, LINE_HI = "#265874", "#317898"
TXT, DIM = "#e6f6fb", "#86b1d1"
CYAN, GOLD, PINK, GREEN, RED = "#acedf9", "#c9b4e6", "#eba3bd", "#7fd6c2", "#eba3bd"
SHADOW = "#06121a"


# ── Datos ─────────────────────────────────────────────────────────────
QUERY = """
query($login:String!){
  user(login:$login){
    login name bio location createdAt
    followers{totalCount}
    repositories(ownerAffiliations:OWNER, first:100, orderBy:{field:PUSHED_AT, direction:DESC}){
      totalCount
      nodes{
        name description isPrivate isFork stargazerCount pushedAt url
        primaryLanguage{name color}
        languages(first:10, orderBy:{field:SIZE, direction:DESC}){edges{size node{name color}}}
      }
    }
    contributionsCollection{
      totalCommitContributions totalPullRequestContributions totalIssueContributions
      restrictedContributionsCount
      contributionCalendar{ totalContributions weeks{ contributionDays{ date contributionCount } } }
    }
  }
}"""


def fetch():
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        sys.exit("Falta GH_TOKEN")
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": USER}}).encode(),
        headers={"Authorization": f"bearer {token}", "User-Agent": "pixel-profile"},
    )
    with urllib.request.urlopen(req) as r:
        data = json.load(r)
    if "errors" in data:
        sys.exit(json.dumps(data["errors"], indent=2))
    return data["data"]["user"]


def scrape_calendar(login):
    """Respaldo: lee el calendario público (incluye privadas si el perfil lo permite)."""
    import re
    req = urllib.request.Request(f"https://github.com/users/{login}/contributions",
                                 headers={"User-Agent": "pixel-profile"})
    try:
        html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "ignore")
    except Exception as e:  # noqa: BLE001
        print("No se pudo leer el calendario público:", e)
        return None
    tips = {}
    for m in re.finditer(r'<tool-tip[^>]*for="([^"]+)"[^>]*>\s*([^<]*)</tool-tip>', html):
        n = re.match(r"\s*(\d[\d,]*)", m.group(2))
        tips[m.group(1)] = int(n.group(1).replace(",", "")) if n else 0
    days = []
    for m in re.finditer(r'<td[^>]*data-date="(\d{4}-\d{2}-\d{2})"[^>]*>', html):
        tag = m.group(0)
        idm = re.search(r'id="([^"]+)"', tag)
        lvl = re.search(r'data-level="(\d)"', tag)
        cnt = tips.get(idm.group(1)) if idm else None
        if cnt is None:
            cnt = int(lvl.group(1)) if lvl else 0
        days.append({"date": m.group(1), "contributionCount": cnt})
    total = re.search(r"([\d,]+)\s+contributions?\s+in the last year", html)
    if not days:
        return None
    return {"days": days, "total": int(total.group(1).replace(",", "")) if total else sum(d["contributionCount"] for d in days)}


def summarize(u):
    repos = u["repositories"]["nodes"]
    own = sorted([r for r in repos if not r["isFork"]], key=lambda r: r["pushedAt"] or "", reverse=True)
    langs = {}
    for r in own:
        for e in r["languages"]["edges"]:
            n = e["node"]["name"]
            langs.setdefault(n, [0, e["node"]["color"] or DIM])
            langs[n][0] += e["size"]
    total = sum(v[0] for v in langs.values()) or 1
    top = sorted(langs.items(), key=lambda kv: -kv[1][0])[:6]

    days = [d for w in u["contributionsCollection"]["contributionCalendar"]["weeks"] for d in w["contributionDays"]]
    cc = u["contributionsCollection"]
    year_total = cc["contributionCalendar"]["totalContributions"]
    if year_total == 0:
        cal = scrape_calendar(u["login"])
        if cal:
            days, year_total = cal["days"], cal["total"]
            print(f"Calendario público: {year_total} contribuciones")
    days.sort(key=lambda d: d["date"])
    longest = run = 0
    for d in days:
        run = run + 1 if d["contributionCount"] else 0
        longest = max(longest, run)
    cur = 0
    for i, d in enumerate(reversed(days)):
        if d["contributionCount"]:
            cur += 1
        elif i == 0:
            continue  # hoy todavía puede sumar
        else:
            break
    last_active = next((d["date"] for d in reversed(days) if d["contributionCount"]), None)

    created = dt.datetime.fromisoformat(u["createdAt"].replace("Z", "+00:00"))
    years = (dt.datetime.now(dt.timezone.utc) - created).days / 365.25

    return {
        "login": u["login"],
        "name": u["name"] or u["login"],
        "location": u["location"] or "",
        "since": created.year,
        "years": years,
        "followers": u["followers"]["totalCount"],
        "repos": u["repositories"]["totalCount"],
        "stars": sum(r["stargazerCount"] for r in own),
        "commits": cc["totalCommitContributions"] or year_total - cc["totalPullRequestContributions"] - cc["totalIssueContributions"],
        "prs": cc["totalPullRequestContributions"],
        "issues": cc["totalIssueContributions"],
        "private": cc["restrictedContributionsCount"],
        "year_total": year_total,
        "streak": cur,
        "longest": longest,
        "last_active": last_active,
        "langs": [(n, v[1], v[0] / total) for n, (v) in top],
        "quests": [
            {
                "name": r["name"],
                "desc": r["description"] or "",
                "lang": (r["primaryLanguage"] or {}).get("name", ""),
                "color": (r["primaryLanguage"] or {}).get("color") or DIM,
                "stars": r["stargazerCount"],
                "pushed": r["pushedAt"][:10],
                "private": r["isPrivate"],
            }
            for r in [r for r in own if (SHOW_PRIVATE or not r["isPrivate"]) and r["name"].lower() != USER.lower()][:4]
        ],
        "updated": dt.datetime.now(dt.timezone(dt.timedelta(hours=-4))).strftime("%d/%m/%Y %H:%M"),
    }


# ── Helpers SVG ───────────────────────────────────────────────────────
def svg(w, h, body, title):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
        f'shape-rendering="crispEdges" role="img" aria-label="{escape(title)}">'
        f"<style>@font-face{{font-family:P;src:url(data:font/woff2;base64,{FONT_B64}) format('woff2')}}"
        f"text{{font-family:P,monospace;fill:{TXT}}}</style>{body}</svg>"
    )


def rect(x, y, w, h, c, extra=""):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{c}"{extra}/>'


def plain(s):
    """La fuente no trae mayúsculas acentuadas: las quitamos solo en textos en mayúsculas."""
    s = str(s)
    if s.upper() != s:
        return s
    return "".join(ch for ch in unicodedata.normalize("NFD", s) if unicodedata.category(ch) != "Mn")


def text(x, y, s, size=10, c=TXT, anchor="start", extra=""):
    s = plain(s)
    return f'<text x="{x}" y="{y}" font-size="{size}" fill="{c}" text-anchor="{anchor}"{extra}>{escape(str(s))}</text>'


def fit(s, chars):
    return s if len(s) <= chars else s[: chars - 2] + ".."


def frame(w, h, title, icon_color=GOLD):
    """Marco estilo ventana de RPG con esquinas recortadas."""
    b = rect(0, 0, w, h, BG)
    b += rect(4, 0, w - 8, 4, LINE) + rect(4, h - 4, w - 8, 4, LINE)
    b += rect(0, 4, 4, h - 8, LINE) + rect(w - 4, 4, 4, h - 8, LINE)
    b += rect(4, 4, w - 8, 4, LINE_HI)  # brillo superior
    b += rect(8, 12, w - 16, 26, BG2)
    b += rect(16, 21, 8, 8, icon_color)
    b += text(32, 30, title, 10, GOLD)
    return b


def bar(x, y, w, frac, c, segs=None):
    """Barra segmentada estilo HP."""
    segs = segs or max(1, w // 8)
    sw = w / segs
    out = rect(x - 2, y - 2, w + 4, 12, LINE)
    out += rect(x, y, w, 8, BG)
    on = round(segs * max(0.0, min(1.0, frac)))
    for i in range(on):
        out += rect(round(x + i * sw), y, max(1, round(sw) - 2), 8, c)
        out += rect(round(x + i * sw), y, max(1, round(sw) - 2), 2, "#ffffff", ' opacity="0.25"')
    return out


# ── Héroe: caballo negro de ajedrez ───────────────────────────────────
KNIGHT = [
    ".........XX.........",
    "........XXX..X......",
    ".......XXXXXXXX.....",
    "......XXXXXXXXXX....",
    ".....XXXXXXXXXXXX...",
    "....XXXEXXXXXXXXXX..",
    "...XXXXXXXXXXXXXXXX.",
    "..XXXXXXXXXXXXXXXXX.",
    ".XXXXXXXXXXXXXXXXXX.",
    "XXXXXXXXXXXXXXXXXXXX",
    "XNXXXXXXXXXXXXXXXXXX",
    ".XXXXX..XXXXXXXXXXXX",
    "..XX....XXXXXXXXXXXX",
    ".......XXXXXXXXXXXX.",
    "......XXXXXXXXXXXXX.",
    ".....XXXXXXXXXXXXX..",
    ".....XXXXXXXXXXXXX..",
    "....XXXXXXXXXXXXXX..",
    "...BBBBBBBBBBBBBBBB.",
    "...XXXXXXXXXXXXXXXX.",
    "..XXXXXXXXXXXXXXXXXX",
    ".BBBBBBBBBBBBBBBBBBB",
    ".XXXXXXXXXXXXXXXXXXX",
]
# Pieza negra con luz de pantalla: cuerpo casi negro, borde cian a la izquierda y arriba, sombra lavanda a la derecha.
PIECE, PIECE_MID, RIM, RIM_SOFT, BACK = "#141d27", "#1d2a38", CYAN, "#5fa9c4", "#3b3550"


def knight(x, y, s):
    rows = KNIGHT
    h, w = len(rows), len(rows[0])
    get = lambda i, j: 0 <= j < h and 0 <= i < w and rows[j][i] in "XBEN"
    out = ""
    for j, r in enumerate(rows):
        for i, c in enumerate(r):
            if c == ".":
                continue
            if c == "E":
                col = RIM
            elif not get(i - 1, j) or not get(i, j - 1):
                col = RIM
            elif c == "N":
                col = SHADOW
            elif not get(i + 1, j):
                col = BACK
            elif c == "B":
                col = PIECE_MID
            else:
                col = PIECE
            out += rect(x + i * s, y + j * s, s, s, col)
    # crin: muescas en la espalda
    for j in (3, 5, 7, 9, 11):
        mi = max(i for i, c in enumerate(rows[j]) if c != ".")
        out += rect(x + (mi - 1) * s, y + j * s, s, s, RIM_SOFT)
    sparkles = ""
    for i, (dx, dy, c) in enumerate([(-3, 4, CYAN), (21, 2, GOLD), (22, 12, PINK), (-3, 16, GOLD), (11, -3, CYAN)]):
        sx, sy = x + dx * s, y + dy * s
        star = rect(sx + s // 2 - 2, sy, 4, s * 2, c) + rect(sx - s // 2, sy + s - 2, s * 2, 4, c)
        sparkles += (f'<g opacity="0">{star}<animate attributeName="opacity" values="0;1;0" dur="2s" '
                     f'begin="{i * .4:.1f}s" repeatCount="indefinite"/></g>')
    shadow = rect(x, y + (h - 1) * s + s, w * s, s // 2, SHADOW, ' opacity=".6"')
    return shadow, out, sparkles


def banner(d):
    random.seed(20)
    S, W, H = 8, 105, 32
    o = []
    bands = ["#091a25", "#0e2432", "#102a39", "#12374a", "#204259", "#1f5274", "#265874", "#317898"]
    for i, c in enumerate(bands):
        o.append(rect(0, i * 3 * S, W * S, (H - i * 3) * S, c))
    for _ in range(45):
        x, y = random.randrange(W), random.randrange(0, 16)
        sz = S if random.random() < .4 else S // 2
        o.append(f'<rect x="{x*S}" y="{y*S}" width="{sz}" height="{sz}" fill="{CYAN}">'
                 f'<animate attributeName="opacity" values="1;.15;1" dur="{random.uniform(1.5,4):.1f}s" '
                 f'begin="{random.uniform(0,3):.1f}s" repeatCount="indefinite"/></rect>')
    # luna con halo
    moon = ["..XXXX..", ".XXXXXX.", "XXXXXXXX", "XXXXXXXX", "XXXXXXXX", "XXXXXXXX", ".XXXXXX.", "..XXXX.."]
    for j, r in enumerate(moon):
        for i, c in enumerate(r):
            if c == "X":
                o.append(rect((90 + i) * S, (3 + j) * S, S, S, "#e6f6fb" if (i * 3 + j) % 7 else "#acedf9"))
    for cx, cy, dur in [(10, 6, 60), (55, 10, 80)]:
        cl = rect(cx * S, cy * S, 10 * S, S, "#3f5d7e") + rect((cx + 2) * S, (cy - 1) * S, 5 * S, S, "#3f5d7e")
        o.append(f'<g opacity="0.7">{cl}<animateTransform attributeName="transform" type="translate" '
                 f'values="0 0;{W*S} 0;0 0" dur="{dur}s" repeatCount="indefinite"/></g>')

    def mountains(base, peaks, col, shade):
        h = [0] * W
        for cx, ph, sl in peaks:
            for x in range(W):
                h[x] = max(h[x], ph - abs(x - cx) // sl)
        for x in range(W):
            if h[x] > 0:
                o.append(rect(x * S, (base - h[x]) * S, S, h[x] * S, col))
                o.append(rect(x * S, (base - h[x]) * S, S, S, shade))
    mountains(26, [(8, 9, 1), (30, 11, 2), (52, 8, 1), (74, 12, 2), (98, 9, 1)], "#12374a", "#204259")
    mountains(28, [(0, 7, 1), (20, 8, 2), (45, 10, 2), (66, 7, 1), (90, 9, 2)], "#0e2432", "#1f5274")
    # suelo de tablero de ajedrez
    for row in range(28, 32):
        for col in range(0, W, 2):
            light = ((col // 2) + row) % 2 == 0
            o.append(rect(col * S, row * S, 2 * S, S, "#86b1d1" if light else "#204259"))
    o.append(rect(0, 28 * S, W * S, 2, CYAN, ' opacity=".6"'))
    glow, body, sparkles = knight(9 * S, 5 * S, 8)
    o.append(glow)
    o.append(f'<g>{body}<animateTransform attributeName="transform" type="translate" '
             f'values="0 0;0 -3;0 0" dur="2s" repeatCount="indefinite"/></g>')
    o.append(sparkles)
    # títulos
    o.append(rect(37 * S - 8, 10 * S - 4, 52 * S, 14 * S, SHADOW, ' opacity="0.6"'))
    o.append(rect(37 * S - 8, 10 * S - 4, 52 * S, 2, CYAN, ' opacity=".5"'))
    o.append(text(39 * S, 14 * S + 4, d["name"].upper()[:18], 28, SHADOW))
    o.append(text(39 * S - 3, 14 * S + 1, d["name"].upper()[:18], 28, GOLD))
    o.append(text(39 * S, 17 * S + 6, "BACKEND · GAME DEV", 12, CYAN))
    loc = d["location"] or "República Dominicana"
    pin = "".join(rect(39 * S + i * 2, 19 * S - 2 + j * 2, 2, 2, PINK) for j, r in enumerate(
        [".XXX.", "XX.XX", "XXXXX", ".XXX.", "..X.."]) for i, c in enumerate(r) if c == "X")
    o.append(pin + text(39 * S + 18, 19 * S + 8, fit(loc, 28), 10, TXT))
    arrow = "".join(rect(39 * S + i * 2, 22 * S - 6 + j * 2, 2, 2, TXT) for j, r in enumerate(
        ["X...", "XX..", "XXX.", "XX..", "X..."]) for i, c in enumerate(r) if c == "X")
    o.append(f'<g>{arrow}{text(39 * S + 16, 22 * S + 4, "PRESS START", 10, TXT)}'
             f'<animate attributeName="opacity" values="1;1;0;0" keyTimes="0;.5;.5;1" dur="1s" repeatCount="indefinite"/></g>')
    return svg(W * S, H * S, "".join(o), f"Banner de {d['name']}")


def stats_card(d):
    w, h = 416, 280
    lvl = 1 + int(d["years"] * 2 + d["year_total"] / 100)
    xp = (d["year_total"] % 100) / 100
    b = frame(w, h, "PLAYER STATS")
    b += text(24, 62, f"@{d['login']}", 10, CYAN) + text(w - 24, 62, f"LV {lvl}", 12, GOLD, "end")
    b += text(24, 84, "EXP", 8, DIM) + bar(64, 77, w - 88, xp, GREEN)
    rows = [
        ("CONTRIB. 12 MESES", d["year_total"], CYAN),
        ("COMMITS", d["commits"], GOLD),
        ("PULL REQ.", d["prs"], PINK),
        ("ISSUES", d["issues"], GREEN),
        ("REPOS", d["repos"], CYAN),
        ("ESTRELLAS", d["stars"], GOLD),
        ("SEGUIDORES", d["followers"], PINK),
    ]
    y = 112
    for label, val, c in rows:
        b += rect(24, y - 8, 8, 8, c) + text(40, y, label, 9) + text(w - 24, y, val, 9, c, "end")
        b += rect(40, y + 7, w - 64, 2, BG2)
        y += 20
    b += text(24, h - 16, f"MIEMBRO DESDE {d['since']}", 7, DIM)
    return svg(w, h, b, "Estadísticas")


def langs_card(d):
    w, h = 416, 280
    b = frame(w, h, "INVENTARIO", CYAN)
    y = 72
    for i, (n, c, frac) in enumerate(d["langs"]):
        b += rect(24, y - 12, 26, 26, LINE) + rect(26, y - 10, 22, 22, BG2) + rect(31, y - 5, 12, 12, c)
        b += rect(31, y - 5, 12, 3, "#ffffff", ' opacity="0.3"')
        b += text(60, y - 1, fit(n, 14), 9) + text(w - 24, y - 1, f"{frac*100:.1f}%", 8, DIM, "end")
        b += bar(60, y + 6, w - 84, frac / max(f for _, _, f in d["langs"]), c)
        y += 34
    if not d["langs"]:
        b += text(w / 2, 140, "INVENTARIO VACÍO", 10, DIM, "middle")
    return svg(w, h, b, "Lenguajes más usados")


def quests_card(d):
    w = 840
    h = 62 + 56 * max(1, len(d["quests"])) + 10
    b = frame(w, h, "QUESTS RECIENTES", PINK)
    y = 62
    for q in d["quests"]:
        b += rect(24, y, w - 48, 46, BG2) + rect(24, y, 4, 46, q["color"])
        b += text(40, y + 19, fit(q["name"], 30), 11, GOLD)
        tag = "PRIVADO" if q["private"] else "PÚBLICO"
        b += text(w - 36, y + 19, f"{q['stars']}   {tag}", 8, DIM, "end")
        sx = w - 36 - 8 * (len(f"{q['stars']}   {tag}")) - 12
        b += "".join(rect(sx + i * 2, y + 9 + j * 2, 2, 2, GOLD) for j, r in enumerate(
            ["..X..", "XXXXX", ".XXX.", ".X.X."]) for i, c in enumerate(r) if c == "X")
        desc = q["desc"] or "Sin descripción"
        b += text(40, y + 37, fit(desc, 58), 8, TXT)
        if q["lang"]:
            b += rect(w - 260, y + 30, 8, 8, q["color"]) + text(w - 246, y + 38, fit(q["lang"], 10), 8, TXT)
        b += text(w - 36, y + 38, q["pushed"], 8, CYAN, "end")
        y += 56
    return svg(w, h, b, "Proyectos recientes")


def streak_card(d):
    w, h = 840, 150
    b = frame(w, h, "RACHA DE COMBO", RED)
    cols = [(d["year_total"], "CONTRIB. 12 MESES", CYAN),
            (d["streak"], "RACHA ACTUAL (DÍAS)", GOLD),
            (d["longest"], "MEJOR RACHA", PINK)]
    cw = (w - 48) / 3
    for i, (v, label, c) in enumerate(cols):
        cx = 24 + cw * i + cw / 2
        b += text(cx + 2, 92, v, 26, SHADOW, "middle") + text(cx, 90, v, 26, c, "middle")
        b += text(cx, 116, label, 8, DIM, "middle")
        if i:
            b += rect(24 + cw * i, 58, 4, 70, LINE)
    b += text(w - 24, h - 14, f"ACTUALIZADO {d['updated']}", 7, DIM, "end")
    if d["last_active"]:
        b += text(24, h - 14, f"ÚLTIMA ACTIVIDAD {d['last_active']}", 7, DIM)
    return svg(w, h, b, "Racha de contribuciones")


def main():
    if len(sys.argv) > 2 and sys.argv[1] == "--mock":
        d = json.loads(Path(sys.argv[2]).read_text())
        d.setdefault("updated", dt.datetime.now().strftime("%d/%m/%Y %H:%M"))
    else:
        d = summarize(fetch())
    files = {"banner.svg": banner(d), "stats.svg": stats_card(d), "langs.svg": langs_card(d),
             "quests.svg": quests_card(d), "streak.svg": streak_card(d)}
    for n, s in files.items():
        (OUT / n).write_text(s, encoding="utf-8")
    print(json.dumps({k: v for k, v in d.items() if k not in ("langs", "quests")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
