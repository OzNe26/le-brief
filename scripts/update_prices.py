#!/usr/bin/env python3
"""Cours pour « Mon portefeuille » -> prices.json (toutes les 30 min).
Crypto : CoinGecko (top 200 par capitalisation, en euros). Actions et ETF : Yahoo Finance.
Tout est converti en euros. Bibliothèque standard uniquement."""
import json, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

ROOT = __file__.rsplit("/scripts/", 1)[0]
UA = {"User-Agent": "Mozilla/5.0 (compatible; LeBriefBot/1.0; +https://ozne26.github.io/le-brief/)", "Accept": "application/json"}

# (ticker Yahoo, nom affiché, type)
STOCKS = [
    # CAC 40
    ("AC.PA", "Accor", "action"), ("AI.PA", "Air Liquide", "action"), ("AIR.PA", "Airbus", "action"), ("MT.AS", "ArcelorMittal", "action"),
    ("CS.PA", "AXA", "action"), ("BNP.PA", "BNP Paribas", "action"), ("EN.PA", "Bouygues", "action"), ("CAP.PA", "Capgemini", "action"),
    ("CA.PA", "Carrefour", "action"), ("ACA.PA", "Crédit Agricole", "action"), ("BN.PA", "Danone", "action"), ("DSY.PA", "Dassault Systèmes", "action"),
    ("EDEN.PA", "Edenred", "action"), ("ENGI.PA", "Engie", "action"), ("EL.PA", "EssilorLuxottica", "action"), ("ERF.PA", "Eurofins Scientific", "action"),
    ("RMS.PA", "Hermès", "action"), ("KER.PA", "Kering", "action"), ("OR.PA", "L'Oréal", "action"), ("LR.PA", "Legrand", "action"),
    ("MC.PA", "LVMH", "action"), ("ML.PA", "Michelin", "action"), ("ORA.PA", "Orange", "action"), ("RI.PA", "Pernod Ricard", "action"),
    ("PUB.PA", "Publicis", "action"), ("RNO.PA", "Renault", "action"), ("SAF.PA", "Safran", "action"), ("SGO.PA", "Saint-Gobain", "action"),
    ("SAN.PA", "Sanofi", "action"), ("SU.PA", "Schneider Electric", "action"), ("GLE.PA", "Société Générale", "action"), ("STLAP.PA", "Stellantis", "action"),
    ("STMPA.PA", "STMicroelectronics", "action"), ("TEP.PA", "Teleperformance", "action"), ("HO.PA", "Thales", "action"), ("TTE.PA", "TotalEnergies", "action"),
    ("URW.PA", "Unibail-Rodamco-Westfield", "action"), ("VIE.PA", "Veolia", "action"), ("DG.PA", "Vinci", "action"), ("VIV.PA", "Vivendi", "action"),
    # Autres françaises et européennes suivies
    ("BOL.PA", "Bolloré", "action"), ("FDJU.PA", "FDJ United", "action"), ("UBI.PA", "Ubisoft", "action"), ("SOI.PA", "Soitec", "action"),
    ("AM.PA", "Dassault Aviation", "action"), ("ASML.AS", "ASML", "action"), ("SAP.DE", "SAP", "action"), ("NOVO-B.CO", "Novo Nordisk", "action"),
    # États-Unis
    ("AAPL", "Apple", "action"), ("MSFT", "Microsoft", "action"), ("NVDA", "Nvidia", "action"), ("AMZN", "Amazon", "action"),
    ("GOOGL", "Alphabet (Google)", "action"), ("META", "Meta", "action"), ("TSLA", "Tesla", "action"), ("BRK-B", "Berkshire Hathaway", "action"),
    ("AVGO", "Broadcom", "action"), ("AMD", "AMD", "action"), ("INTC", "Intel", "action"), ("NFLX", "Netflix", "action"),
    ("PLTR", "Palantir", "action"), ("COIN", "Coinbase", "action"), ("MSTR", "Strategy (MicroStrategy)", "action"), ("UBER", "Uber", "action"),
    ("ORCL", "Oracle", "action"), ("CRM", "Salesforce", "action"), ("ADBE", "Adobe", "action"), ("JPM", "JPMorgan", "action"),
    ("V", "Visa", "action"), ("MA", "Mastercard", "action"), ("KO", "Coca-Cola", "action"), ("PEP", "PepsiCo", "action"),
    ("DIS", "Disney", "action"), ("MCD", "McDonald's", "action"), ("NKE", "Nike", "action"), ("WMT", "Walmart", "action"),
    ("HOOD", "Robinhood", "action"), ("SPOT", "Spotify", "action"), ("TSM", "TSMC", "action"), ("BABA", "Alibaba", "action"),
    # ETF courants (PEA / compte-titres)
    ("CW8.PA", "Amundi MSCI World (CW8)", "etf"), ("WPEA.PA", "iShares MSCI World PEA (WPEA)", "etf"), ("DCAM.PA", "Amundi PEA Monde (DCAM)", "etf"),
    ("ESE.PA", "BNP Paribas Easy S&P 500 (ESE)", "etf"), ("PE500.PA", "Amundi PEA S&P 500 (PE500)", "etf"), ("PSP5.PA", "Amundi PEA S&P 500 ESG (PSP5)", "etf"),
    ("PUST.PA", "Amundi PEA Nasdaq-100 (PUST)", "etf"), ("PAEEM.PA", "Amundi PEA Émergents (PAEEM)", "etf"), ("C40.PA", "Amundi CAC 40 (C40)", "etf"),
    ("IWDA.AS", "iShares Core MSCI World (IWDA)", "etf"), ("VWCE.DE", "Vanguard FTSE All-World (VWCE)", "etf"), ("SXR8.DE", "iShares Core S&P 500 (SXR8)", "etf"),
    ("EQQQ.DE", "Invesco Nasdaq-100 (EQQQ)", "etf"),
]


def get_json(url, tries=2):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=25) as r:
                return json.loads(r.read())
        except Exception:
            if i == tries - 1: raise
            time.sleep(2)


def yahoo(sym):
    j = get_json(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=5d&interval=1d")
    m = j["chart"]["result"][0]["meta"]
    p, prev = m.get("regularMarketPrice"), m.get("chartPreviousClose") or m.get("previousClose")
    cur = m.get("currency") or "EUR"
    if cur == "GBp": p, prev, cur = (p or 0) / 100, (prev or 0) / 100, "GBP"
    return p, prev, cur


def main():
    out = {"updatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"), "fx": {"EUR": 1.0}, "assets": [], "errors": []}
    # Taux de change -> euro
    for c, sym in (("USD", "EURUSD=X"), ("GBP", "EURGBP=X"), ("DKK", "EURDKK=X"), ("CHF", "EURCHF=X")):
        try:
            p, _, _ = yahoo(sym)
            if p: out["fx"][c] = p  # 1 EUR = p devise
        except Exception as e:
            out["errors"].append(f"{sym} : {str(e)[:80]}")
    # Crypto (top 200, en euros)
    try:
        rows = []
        for page in (1, 2):
            rows += get_json("https://api.coingecko.com/api/v3/coins/markets?vs_currency=eur&order=market_cap_desc"
                             f"&per_page=100&page={page}&price_change_percentage=24h")
            time.sleep(3)
        seen = set()
        for r in rows:
            if not r.get("current_price") or r["symbol"].lower() in seen: continue
            seen.add(r["symbol"].lower())
            out["assets"].append({"k": "c:" + r["id"], "s": r["symbol"].upper(), "n": r["name"], "t": "crypto",
                                  "p": r["current_price"], "ch": r.get("price_change_percentage_24h"),
                                  "img": (r.get("image") or "").replace("/large/", "/small/")})
    except Exception as e:
        out["errors"].append(f"CoinGecko : {str(e)[:120]}")
    # Actions et ETF
    def one(row):
        sym, name, typ = row
        try:
            p, prev, cur = yahoo(sym)
            rate = out["fx"].get(cur)
            if not p or not rate: raise ValueError(f"cours ou devise {cur} manquants")
            return {"k": "s:" + sym, "s": sym.split(".")[0], "n": name, "t": typ, "p": round(p / rate, 4),
                    "ch": round((p / prev - 1) * 100, 2) if prev else None, "cur": cur, "pn": p}
        except Exception as e:
            return {"err": f"{sym} : {str(e)[:80]}"}
    with ThreadPoolExecutor(max_workers=8) as ex:
        for r in ex.map(one, STOCKS):
            if "err" in r: out["errors"].append(r["err"])
            else: out["assets"].append(r)
    nb = len(out["assets"])
    if nb < 50:
        print(f"Trop peu de cours ({nb}), on garde l'ancien fichier. {out['errors'][:5]}"); return
    json.dump(out, open(f"{ROOT}/prices.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print(f"{nb} cours ({sum(a['t']=='crypto' for a in out['assets'])} crypto), erreurs : {out['errors'][:10]}")


if __name__ == "__main__":
    main()
