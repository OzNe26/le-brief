#!/usr/bin/env python3
"""Élus américains et grands investisseurs -> insiders.json (une à deux fois par jour).
- Congrès américain : déclarations officielles STOCK Act (House Clerk + Senate eFD), via l'API gratuite Bargo
  (attribution obligatoire, affichée sur le site). Les déclarations arrivent jusqu'à 45 jours après le trade.
- Grands investisseurs : portefeuilles déclarés chaque trimestre à la SEC (formulaire 13F), via Dataroma.
Ce sont des déclarations légales et publiques, pas des preuves de quoi que ce soit. Bibliothèque standard uniquement."""
import html, json, os, re, time, urllib.parse, urllib.request
from datetime import datetime, timezone, timedelta

ROOT = __file__.rsplit("/scripts/", 1)[0]
NOW = datetime.now(timezone.utc)
UA = {"User-Agent": "Mozilla/5.0 (compatible; LeBriefInvest/1.0; +https://ozne26.github.io/le-brief/)", "Accept": "application/json, text/html"}
BARGO = "https://www.bargo.ai/free-apis/congress/v1"
KEEP_DAYS = 120

# Élus très suivis pour leurs transactions (des deux partis) : leurs trades sont mis en avant
FAMOUS = {"nancy-pelosi": "Nancy Pelosi", "rohit-khanna": "Ro Khanna", "marjorie-taylor-greene": "Marjorie Taylor Greene",
          "josh-gottheimer": "Josh Gottheimer", "daniel-crenshaw": "Dan Crenshaw", "michael-mccaul": "Michael McCaul",
          "tommy-tuberville": "Tommy Tuberville", "markwayne-mullin": "Markwayne Mullin", "ron-wyden": "Ron Wyden",
          "debbie-wasserman-schultz": "Debbie Wasserman Schultz", "kevin-hern": "Kevin Hern", "rick-scott": "Rick Scott",
          "dave-mccormick": "Dave McCormick", "shelley-moore-capito": "Shelley Moore Capito", "john-boozman": "John Boozman",
          "jared-moskowitz": "Jared Moskowitz", "byron-donalds": "Byron Donalds", "gilbert-cisneros": "Gil Cisneros"}

# Grands investisseurs (code Dataroma, nom affiché)
INVESTORS = [("BRK", "Warren Buffett", "Berkshire Hathaway"), ("psc", "Bill Ackman", "Pershing Square"),
             ("ic", "Carl Icahn", "Icahn Capital"), ("AM", "David Tepper", "Appaloosa"), ("BAUPOST", "Seth Klarman", "Baupost Group"),
             ("oc", "Howard Marks", "Oaktree Capital"), ("TGM", "Chase Coleman", "Tiger Global"), ("GFT", "Bill & Melinda Gates", "Fondation Gates"),
             ("PI", "Mohnish Pabrai", "Pabrai Investments"), ("LMM", "Bill Miller", "Miller Value Partners"), ("GLRE", "David Einhorn", "Greenlight Capital"),
             ("tp", "Daniel Loeb", "Third Point"), ("TF", "Nelson Peltz", "Trian"), ("HC", "Li Lu", "Himalaya Capital"),
             ("FS", "Terry Smith", "Fundsmith"), ("vg", "Andreas Halvorsen", "Viking Global"), ("FFH", "Prem Watsa", "Fairfax Financial"),
             ("LPC", "Stephen Mandel", "Lone Pine Capital")]


def get(url, tries=2, headers=None):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={**UA, **(headers or {})}), timeout=30) as r:
                return r.read()
        except Exception:
            if i == tries - 1: raise
            time.sleep(3)


def bargo(path, **params):
    key = os.environ.get("BARGO_API_KEY", "").strip()
    q = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    return json.loads(get(f"{BARGO}/{path}?{q}", headers={"X-Api-Key": key} if key else None))


TYPES = {"purchase": "achat", "buy": "achat", "sale": "vente", "sale_full": "vente", "sale_partial": "vente partielle",
         "partial_sale": "vente partielle", "exchange": "échange"}


def congress(prev):
    out, errs = {"trades": [], "members": []}, []
    key = bool(os.environ.get("BARGO_API_KEY", "").strip())
    try:
        rows = bargo("trades", limit=200 if key else 80).get("trades", [])
    except Exception as e:
        rows = []; errs.append(f"Bargo trades : {str(e)[:100]}")
    for slug in (["nancy-pelosi"] if not key else list(FAMOUS)[:8]):  # quota gratuit limité : Pelosi en priorité
        try:
            rows += bargo("trades", member=slug, limit=10).get("trades", [])
            time.sleep(1)
        except Exception as e:
            errs.append(f"Bargo {slug} : {str(e)[:80]}")
    seen, trades = set(), []
    for t in rows + (prev.get("trades") or []):
        k = (t.get("member_slug") or t.get("slug"), t.get("ticker"), t.get("transaction_date") or t.get("tdate"), t.get("type"), t.get("amount_range") or t.get("amount"))
        if k in seen: continue
        seen.add(k)
        if "slug" in t:  # déjà au format du site (fichier précédent)
            trades.append(t); continue
        trades.append({"slug": t.get("member_slug"), "who": t.get("member"), "chamber": t.get("chamber"), "state": t.get("state"),
                       "ticker": (t.get("ticker") or "").upper(), "asset": (t.get("asset") or "")[:90],
                       "type": TYPES.get((t.get("type") or "").lower(), (t.get("type") or "").replace("_", " ")),
                       "amount": t.get("amount_range"), "lo": t.get("amount_low"), "hi": t.get("amount_high"),
                       "tdate": t.get("transaction_date"), "ddate": t.get("disclosure_date"),
                       "perf": t.get("perf_pct"), "famous": t.get("member_slug") in FAMOUS})
    lim = (NOW - timedelta(days=KEEP_DAYS)).date().isoformat()
    trades = [t for t in trades if (t.get("ddate") or t.get("tdate") or "") >= lim]
    trades.sort(key=lambda t: (t.get("ddate") or "", t.get("tdate") or ""), reverse=True)
    out["trades"] = trades[:400]
    try:
        out["members"] = [{"slug": m["member_slug"], "who": m["member"], "chamber": m.get("chamber"), "state": m.get("state"),
                           "trades": m.get("trades"), "buys": m.get("buys"), "sells": m.get("sells"), "last": m.get("last_trade")}
                          for m in bargo("members", limit=12).get("members", [])]
    except Exception as e:
        out["members"] = prev.get("members") or []; errs.append(f"Bargo members : {str(e)[:80]}")
    return out, errs


ACT = [(r"^Buy", "nouvelle position"), (r"^Add\s*([\d.]+)%", "renforce +{} %"), (r"^Reduce\s*([\d.]+)%", "allège −{} %"), (r"^Sell", "vend tout")]


def fr_act(a):
    a = (a or "").strip()
    for pat, txt in ACT:
        m = re.match(pat, a, re.I)
        if m:
            if m.groups():
                v = float(m.group(1)); return txt.format(f"{v:.0f}" if v >= 10 else f"{v:.1f}".replace(".", ","))
            return txt
    return ""


def clean(s): return html.unescape(re.sub(r"<[^>]+>", " ", s or "")).strip()


def investor(code, name, fund):
    s = get(f"https://www.dataroma.com/m/holdings.php?m={urllib.parse.quote(code)}").decode("utf-8", "ignore")
    date = re.search(r"Portfolio date:\s*<span>([^<]+)</span>", s)
    val = re.search(r"Portfolio value:\s*<span>\$?([\d,]+)</span>", s)
    period = re.search(r"Period:\s*<span>([^<]+)</span>", s)
    body = s[s.find('id="grid"'):]
    body = body[:body.find("</table>")]
    rows = []
    for tr in re.findall(r"<tr>(.*?)</tr>", body, re.S):
        tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
        sym = re.search(r"stock\.php\?sym=([A-Za-z0-9.\-]+)", tr)
        if not sym or len(tds) < 7: continue
        nm = re.search(r"<span>\s*-\s*([^<]+)</span>", tr)
        try: pct = float(clean(tds[2]))
        except Exception: pct = None
        v = re.sub(r"[^\d]", "", clean(tds[6]))
        rows.append({"t": sym.group(1).upper(), "n": html.unescape(nm.group(1)).strip() if nm else "", "pct": pct,
                     "act": fr_act(clean(tds[3])), "val": int(v) if v else None})
    if not rows: raise ValueError("tableau introuvable")
    rows.sort(key=lambda r: r["pct"] or 0, reverse=True)
    pd = None
    if date:
        try: pd = datetime.strptime(date.group(1).strip(), "%d %b %Y").date().isoformat()
        except Exception: pd = date.group(1).strip()
    return {"code": code, "name": name, "fund": fund, "date": pd, "value": int(val.group(1).replace(",", "")) if val else None,
            "count": len(rows), "top": rows[:12], "moves": [r for r in rows if r["act"]][:15]}


def main():
    try: prev = json.load(open(f"{ROOT}/insiders.json", encoding="utf-8"))
    except Exception: prev = {}
    out = {"updatedAt": NOW.isoformat(timespec="seconds"), "errors": []}
    c, errs = congress(prev.get("congress") or {})
    out["congress"] = c; out["errors"] += errs
    invs, old = [], {i["code"]: i for i in (prev.get("investors") or [])}
    for code, name, fund in INVESTORS:
        try: invs.append(investor(code, name, fund))
        except Exception as e:
            out["errors"].append(f"Dataroma {code} : {str(e)[:80]}")
            if code in old: invs.append(old[code])
        time.sleep(1.5)
    out["investors"] = invs
    if not c["trades"] and not invs:
        print("Rien récupéré, on garde l'ancien fichier.", out["errors"][:5]); return
    json.dump(out, open(f"{ROOT}/insiders.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print(f"{len(c['trades'])} trades d'élus ({sum(t['famous'] for t in c['trades'])} d'élus très suivis), {len(invs)} investisseurs, erreurs : {out['errors'][:6]}")


if __name__ == "__main__":
    main()
