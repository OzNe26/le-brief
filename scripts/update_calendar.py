#!/usr/bin/env python3
"""Calendrier des marchés -> calendar.json : résultats des grandes entreprises (Nasdaq), agenda macro de la semaine
(Forex Factory : Fed, BCE, emploi, inflation…), dates des banques centrales, et déblocages de tokens crypto si dispo.
Bibliothèque standard uniquement."""
import json, sys, time, urllib.request
from datetime import datetime, timezone, timedelta

sys.path.insert(0, __file__.rsplit("/", 1)[0])
ROOT = __file__.rsplit("/scripts/", 1)[0]
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36",
      "Accept": "application/json, text/plain, */*"}
NOW = datetime.now(timezone.utc)
DAYS = 14

# Entreprises suivies en priorité (en plus de toutes celles > 150 Md$ de capitalisation)
FOLLOW = {"AAPL": "Apple", "MSFT": "Microsoft", "NVDA": "Nvidia", "AMZN": "Amazon", "GOOGL": "Alphabet (Google)", "GOOG": "Alphabet (Google)",
          "META": "Meta", "TSLA": "Tesla", "AVGO": "Broadcom", "AMD": "AMD", "INTC": "Intel", "NFLX": "Netflix", "PLTR": "Palantir",
          "COIN": "Coinbase", "MSTR": "Strategy (MicroStrategy)", "UBER": "Uber", "ORCL": "Oracle", "CRM": "Salesforce", "ADBE": "Adobe",
          "JPM": "JPMorgan", "V": "Visa", "MA": "Mastercard", "KO": "Coca-Cola", "PEP": "PepsiCo", "DIS": "Disney", "MCD": "McDonald's",
          "NKE": "Nike", "WMT": "Walmart", "HOOD": "Robinhood", "SPOT": "Spotify", "TSM": "TSMC", "BABA": "Alibaba", "ASML": "ASML",
          "SAP": "SAP", "NVO": "Novo Nordisk", "ARM": "Arm", "SHOP": "Shopify", "PYPL": "PayPal", "ABNB": "Airbnb", "SNOW": "Snowflake",
          "MARA": "MARA Holdings", "RIOT": "Riot Platforms", "CRCL": "Circle"}

# Banques centrales (décisions de taux, heure de Paris) — calendriers officiels publiés à l'avance
CENTRAL = [
    ("2026-12-09T20:00:00+01:00", "Décision de taux de la Fed", "Réserve fédérale américaine · conférence de presse 30 min après"),
    ("2026-12-17T14:15:00+01:00", "Décision de taux de la BCE", "Banque centrale européenne · conférence de presse à 14h45"),
    ("2027-02-04T14:15:00+01:00", "Décision de taux de la BCE", "Banque centrale européenne · conférence de presse à 14h45"),
    ("2027-03-18T14:15:00+01:00", "Décision de taux de la BCE", "Banque centrale européenne · conférence de presse à 14h45"),
    ("2027-04-29T14:15:00+02:00", "Décision de taux de la BCE", "Banque centrale européenne · conférence de presse à 14h45"),
]

FR = {  # traductions des intitulés Forex Factory les plus courants
    "Non-Farm Employment Change": "Emploi américain (NFP)", "Unemployment Rate": "Taux de chômage", "Average Hourly Earnings m/m": "Salaires horaires",
    "CPI m/m": "Inflation (CPI) sur un mois", "CPI y/y": "Inflation (CPI) sur un an", "Core CPI m/m": "Inflation sous-jacente (CPI)",
    "PPI m/m": "Prix à la production (PPI)", "Core PPI m/m": "Prix à la production sous-jacents", "Federal Funds Rate": "Décision de taux de la Fed",
    "FOMC Statement": "Communiqué de la Fed", "FOMC Press Conference": "Conférence de presse de la Fed", "FOMC Meeting Minutes": "Compte rendu de la Fed",
    "Fed Chair Powell Speaks": "Discours du président de la Fed", "Main Refinancing Rate": "Décision de taux de la BCE", "Monetary Policy Statement": "Communiqué de politique monétaire",
    "ECB Press Conference": "Conférence de presse de la BCE", "ECB President Lagarde Speaks": "Discours de Christine Lagarde (BCE)",
    "Advance GDP q/q": "PIB américain (1re estimation)", "Prelim GDP q/q": "PIB (estimation préliminaire)", "Final GDP q/q": "PIB (estimation finale)",
    "Core PCE Price Index m/m": "Inflation PCE sous-jacente", "Retail Sales m/m": "Ventes au détail", "Core Retail Sales m/m": "Ventes au détail hors auto",
    "ISM Manufacturing PMI": "Indice ISM manufacturier", "ISM Services PMI": "Indice ISM des services", "JOLTS Job Openings": "Offres d'emploi (JOLTS)",
    "ADP Non-Farm Employment Change": "Emploi privé ADP", "Unemployment Claims": "Inscriptions hebdomadaires au chômage", "Congressional Elections": "Élections de mi-mandat américaines",
    "Flash Manufacturing PMI": "PMI manufacturier (flash)", "Flash Services PMI": "PMI des services (flash)", "German Flash Manufacturing PMI": "PMI manufacturier allemand (flash)",
    "CPI Flash Estimate y/y": "Inflation zone euro (estimation flash)", "Core CPI Flash Estimate y/y": "Inflation sous-jacente zone euro (flash)",
    "Prelim UoM Consumer Sentiment": "Moral des consommateurs (Michigan)", "CB Consumer Confidence": "Confiance des consommateurs",
    "Treasury Currency Report": "Rapport du Trésor sur les devises", "Empire State Manufacturing Index": "Indice manufacturier Empire State",
}
COUNTRY = {"USD": "🇺🇸 États-Unis", "EUR": "🇪🇺 Zone euro"}


def get_json(url, timeout=25):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return json.loads(r.read())


def cap(s):
    try: return float(str(s).replace("$", "").replace(",", ""))
    except Exception: return 0.0


import re
def clean_name(n):
    n = re.sub(r",?\s+(Inc\.?|Incorporated|Corporation|Corp\.?|Ltd\.?|Limited|PLC|plc|N\.V\.|S\.A\.|AG|SE|Holdings?|Group|Co\.?|Ord|Ordinary Shares|ADR|Class [A-C])\b\.?", "", n)
    n = re.sub(r"\s+", " ", n).strip(" ,")
    return n.title() if n.isupper() and len(n) > 4 else n

def earnings(out):
    seen = set()
    for i in range(DAYS):
        d = (NOW + timedelta(days=i)).date()
        if d.weekday() >= 5: continue
        try:
            rows = (get_json(f"https://api.nasdaq.com/api/calendar/earnings?date={d.isoformat()}").get("data") or {}).get("rows") or []
        except Exception as e:
            out["errors"].append(f"Nasdaq {d} : {str(e)[:80]}"); continue
        for r in rows:
            sym = (r.get("symbol") or "").upper()
            mc = cap(r.get("marketCap"))
            if not sym or (sym not in FOLLOW and mc < 150e9) or (sym, d) in seen: continue
            seen.add((sym, d))
            when = {"time-pre-market": "avant l'ouverture de Wall Street", "time-after-hours": "après la clôture de Wall Street"}.get(r.get("time"), "")
            hour = {"time-pre-market": "13:00", "time-after-hours": "22:05"}.get(r.get("time"), "12:00")
            name = FOLLOW.get(sym) or clean_name(r.get("name") or sym)
            if (name, d) in seen: continue
            seen.add((name, d))
            imp = 3 if sym in ("AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA") else 2
            q = r.get("fiscalQuarterEnding") or ""
            out["events"].append({"d": f"{d.isoformat()}T{hour}:00+01:00", "allday": not when, "cat": "resultats",
                                  "title": ("Résultats d'" if name[:1].upper() in "AEIOUYH" else "Résultats de ") + name, "sub": " · ".join(x for x in [sym, when, f"trimestre clos {q}" if q else ""] if x),
                                  "imp": imp, "tick": sym})
        time.sleep(0.6)


def macro(out):
    try:
        rows = get_json("https://nfs.faireconomy.media/ff_calendar_thisweek.json")
    except Exception as e:
        out["errors"].append(f"Agenda macro : {str(e)[:80]}"); return
    for r in rows:
        c, imp = r.get("country"), r.get("impact")
        if c not in COUNTRY or imp not in ("High", "Medium"): continue
        if imp == "Medium" and c != "USD": continue
        title = r.get("title") or ""
        fr = FR.get(title)
        if imp == "Medium" and not fr: continue  # on garde seulement les « moyens » qu'on sait traduire
        try: d = datetime.fromisoformat(r["date"])
        except Exception: continue
        bits = [COUNTRY[c]]
        if r.get("forecast"): bits.append(f"prévu {r['forecast']}")
        if r.get("previous"): bits.append(f"précédent {r['previous']}")
        out["events"].append({"d": d.isoformat(), "allday": False, "cat": "macro", "title": fr or title, "sub": " · ".join(bits),
                              "imp": 3 if imp == "High" else 2})


def central(out):
    have = {(e["title"], e["d"][:10]) for e in out["events"]}
    for d, t, sub in CENTRAL:
        if datetime.fromisoformat(d) < NOW - timedelta(hours=6): continue
        if (t, d[:10]) in have: continue
        out["events"].append({"d": d, "allday": False, "cat": "banques", "title": t, "sub": sub, "imp": 3})


def unlocks(out):
    """Déblocages de tokens (DefiLlama, gratuit) : on garde les gros, dans les 14 jours."""
    try:
        data = get_json("https://api.llama.fi/emissions", timeout=40)
    except Exception as e:
        out["errors"].append(f"Déblocages de tokens : {str(e)[:80]}"); return
    lim = (NOW + timedelta(days=DAYS)).timestamp()
    for p in data if isinstance(data, list) else []:
        mcap = p.get("mcap") or 0
        for ev in p.get("events") or []:
            t = ev.get("timestamp") or 0
            if not (NOW.timestamp() < t < lim): continue
            tok = ev.get("noOfTokens") or []
            n = sum(x for x in tok if isinstance(x, (int, float))) if isinstance(tok, list) else (tok or 0)
            price = p.get("price") or 0
            val = n * price
            if val < 20e6: continue
            pct = f" · ≈ {val/mcap*100:.1f} % de la capitalisation" if mcap else ""
            out["events"].append({"d": datetime.fromtimestamp(t, timezone.utc).isoformat(), "allday": False, "cat": "crypto",
                                  "title": f"Déblocage de tokens {p.get('name') or p.get('token') or ''}".strip(),
                                  "sub": f"≈ {val/1e6:,.0f} M$ libérés{pct}".replace(",", " "), "imp": 3 if val > 100e6 else 2})


def main():
    out = {"updatedAt": NOW.isoformat(timespec="seconds"), "events": [], "errors": []}
    earnings(out); macro(out); central(out)  # unlocks(out) : l'API gratuite de DefiLlama est devenue payante
    lo, hi = NOW - timedelta(hours=12), NOW + timedelta(days=60)
    out["events"] = sorted([e for e in out["events"] if lo <= datetime.fromisoformat(e["d"]) <= hi], key=lambda e: e["d"])
    if len(out["events"]) < 3:
        print("Trop peu d'événements, on garde l'ancien calendrier.", out["errors"][:5]); return
    json.dump(out, open(f"{ROOT}/calendar.json", "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    cats = {}
    for e in out["events"]: cats[e["cat"]] = cats.get(e["cat"], 0) + 1
    print(f"{len(out['events'])} événements {cats}, erreurs : {out['errors'][:6]}")


if __name__ == "__main__":
    main()
