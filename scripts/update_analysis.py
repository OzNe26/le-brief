#!/usr/bin/env python3
"""Analyse automatique quotidienne de 10 actifs (crypto + actions US) -> analysis.json.
Cours : Binance (miroir public data-api.binance.vision) pour la crypto, Yahoo Finance puis Stooq pour les actions.
Indicateurs calculés ici (moyennes mobiles, RSI, volatilité, supports/résistances), verdict par règles,
texte rédigé par règles. Si GitHub Models est disponible (jeton GITHUB_TOKEN), une IA reformule le texte.
Bibliothèque standard uniquement. Ce n'est pas un conseil en investissement."""
import csv, io, json, math, os, re, statistics, time, urllib.error, urllib.request
from datetime import datetime, timezone

ROOT = __file__.rsplit("/scripts/", 1)[0]
UA = {"User-Agent": "Mozilla/5.0 (compatible; LeBriefBot/1.0; +https://ozne26.github.io/le-brief/)"}

ASSETS = [
    {"id": "BTC", "name": "Bitcoin", "type": "crypto", "pair": "BTCUSDT", "cg": "bitcoin", "kw": ["bitcoin", "btc"]},
    {"id": "ETH", "name": "Ethereum", "type": "crypto", "pair": "ETHUSDT", "cg": "ethereum", "kw": ["ethereum", "ether ", " eth"]},
    {"id": "SOL", "name": "Solana", "type": "crypto", "pair": "SOLUSDT", "cg": "solana", "kw": ["solana", " sol "]},
    {"id": "XRP", "name": "XRP", "type": "crypto", "pair": "XRPUSDT", "cg": "ripple", "kw": ["xrp", "ripple"]},
    {"id": "BNB", "name": "BNB", "type": "crypto", "pair": "BNBUSDT", "cg": "binancecoin", "kw": ["bnb", "binance"]},
    {"id": "NVDA", "name": "Nvidia", "type": "action", "yahoo": "NVDA", "stooq": "nvda.us", "kw": ["nvidia", "nvda"]},
    {"id": "AAPL", "name": "Apple", "type": "action", "yahoo": "AAPL", "stooq": "aapl.us", "kw": ["apple", "aapl", "iphone"]},
    {"id": "TSLA", "name": "Tesla", "type": "action", "yahoo": "TSLA", "stooq": "tsla.us", "kw": ["tesla", "tsla", "musk"]},
    {"id": "MSFT", "name": "Microsoft", "type": "action", "yahoo": "MSFT", "stooq": "msft.us", "kw": ["microsoft", "msft"]},
    {"id": "AMZN", "name": "Amazon", "type": "action", "yahoo": "AMZN", "stooq": "amzn.us", "kw": ["amazon", "amzn", "aws"]},
]

def get(url, headers=None, data=None, timeout=25):
    req = urllib.request.Request(url, headers={**UA, **(headers or {})}, data=data)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()

# ---------------- Cours ----------------
def crypto_closes(a):
    errs = []
    for host in ("https://data-api.binance.vision", "https://api.binance.com"):
        try:
            k = json.loads(get(f"{host}/api/v3/klines?symbol={a['pair']}&interval=1d&limit=260"))
            closes = [float(x[4]) for x in k]
            highs = [float(x[2]) for x in k]
            lows = [float(x[3]) for x in k]
            last = json.loads(get(f"{host}/api/v3/ticker/price?symbol={a['pair']}"))
            closes[-1] = float(last["price"])  # bougie du jour = prix actuel
            return closes, highs, lows, "Binance"
        except Exception as e:
            errs.append(f"{host}: {e}")
    j = json.loads(get(f"https://api.coingecko.com/api/v3/coins/{a['cg']}/market_chart?vs_currency=usd&days=260&interval=daily"))
    closes = [p[1] for p in j["prices"]]
    return closes, closes, closes, "CoinGecko"

def stock_closes(a):
    try:
        j = json.loads(get(f"https://query1.finance.yahoo.com/v8/finance/chart/{a['yahoo']}?range=1y&interval=1d"))
        r = j["chart"]["result"][0]
        q = r["indicators"]["quote"][0]
        rows = [(c, h, l) for c, h, l in zip(q["close"], q["high"], q["low"]) if c is not None and h is not None and l is not None]
        price = r.get("meta", {}).get("regularMarketPrice")
        closes, highs, lows = [x[0] for x in rows], [x[1] for x in rows], [x[2] for x in rows]
        if price: closes[-1] = float(price)
        return closes, highs, lows, "Yahoo Finance"
    except Exception:
        txt = get(f"https://stooq.com/q/d/l/?s={a['stooq']}&i=d").decode()
        rows = list(csv.DictReader(io.StringIO(txt)))[-260:]
        return [float(r["Close"]) for r in rows], [float(r["High"]) for r in rows], [float(r["Low"]) for r in rows], "Stooq"

# ---------------- Indicateurs ----------------
def sma(v, n): return sum(v[-n:]) / n if len(v) >= n else None
def pct(a, b): return (a / b - 1) * 100 if b else None

def rsi(v, n=14):
    if len(v) <= n: return None
    gains, losses = [], []
    for i in range(1, len(v)):
        d = v[i] - v[i - 1]
        gains.append(max(d, 0)); losses.append(max(-d, 0))
    ag = sum(gains[:n]) / n; al = sum(losses[:n]) / n
    for g, l in zip(gains[n:], losses[n:]):
        ag = (ag * (n - 1) + g) / n; al = (al * (n - 1) + l) / n
    return 100.0 if al == 0 else 100 - 100 / (1 + ag / al)

def analyse(a, closes, highs, lows):
    p = closes[-1]
    m20, m50, m200 = sma(closes, 20), sma(closes, 50), sma(closes, 200)
    r = rsi(closes)
    rets = [math.log(closes[i] / closes[i - 1]) for i in range(max(1, len(closes) - 30), len(closes)) if closes[i - 1] > 0]
    ann = 365 if a["type"] == "crypto" else 252
    vol = statistics.pstdev(rets) * math.sqrt(ann) * 100 if len(rets) > 5 else None
    sup = min(lows[-20:]); res = max(highs[-20:])
    hi52, lo52 = max(highs[-252:]), min(lows[-252:])
    ch = {"1j": pct(p, closes[-2]), "7j": pct(p, closes[-8]) if len(closes) > 8 else None,
          "30j": pct(p, closes[-31]) if len(closes) > 31 else None, "1an": pct(p, closes[-253]) if len(closes) > 253 else None}
    score, why = 0, []
    if m50:
        if p > m50: score += 1; why.append("au-dessus de sa moyenne 50 jours")
        else: score -= 1; why.append("sous sa moyenne 50 jours")
    if m200:
        if p > m200: score += 1; why.append("au-dessus de sa moyenne 200 jours (tendance de fond positive)")
        else: score -= 1; why.append("sous sa moyenne 200 jours (tendance de fond négative)")
    if m50 and m200:
        score += 1 if m50 > m200 else -1
    if ch["30j"] is not None:
        if ch["30j"] > 8: score += 1
        elif ch["30j"] < -8: score -= 1
    if r is not None:
        if r > 72: score -= 1; why.append(f"RSI élevé ({r:.0f}) : zone de surachat, risque de respiration")
        elif r < 30: score += 1; why.append(f"RSI bas ({r:.0f}) : zone de survente, rebond technique possible")
    verdict = "Haussier" if score >= 2 else "Baissier" if score <= -2 else "Neutre"
    return {"price": p, "ch": ch, "sma20": m20, "sma50": m50, "sma200": m200, "rsi": r, "vol": vol,
            "support": sup, "resistance": res, "hi52": hi52, "lo52": lo52, "score": max(-5, min(5, score)),
            "verdict": verdict, "why": why, "spark": [round(x, 6) for x in closes[-30:]]}

def fmt(v):
    if v is None: return "?"
    if v >= 1000: return f"{v:,.0f}".replace(",", " ")
    if v >= 10: return f"{v:,.2f}".replace(",", " ").replace(".", ",")
    return f"{v:.4f}".replace(".", ",")

def sgn(v): return "?" if v is None else (f"+{v:.1f}" if v >= 0 else f"{v:.1f}").replace(".", ",") + " %"

def rule_text(a, x, news):
    t = []
    trend = {"Haussier": "La tendance technique est plutôt positive", "Baissier": "La tendance technique est plutôt négative",
             "Neutre": "Le signal technique est mitigé"}[x["verdict"]]
    t.append(f"{trend} : {a['name']} évolue {', '.join(x['why'][:2]) or 'sans signal net'}.")
    t.append(f"Sur 7 jours le cours fait {sgn(x['ch']['7j'])} et sur 30 jours {sgn(x['ch']['30j'])}.")
    t.append(f"À surveiller : le support autour de {fmt(x['support'])} $ et la résistance vers {fmt(x['resistance'])} $ (plus bas et plus haut des 20 dernières séances).")
    if len(x["why"]) > 2: t.append(x["why"][2][0].upper() + x["why"][2][1:] + ".")
    if news: t.append(f"Côté actu : « {news[0]['titre']} » ({news[0]['source']}).")
    return " ".join(t)

# ---------------- Actus liées ----------------
def related_news(a):
    try:
        live = json.load(open(f"{ROOT}/news_live.json", encoding="utf-8"))
    except Exception:
        return []
    tabs = ["crypto"] if a["type"] == "crypto" else ["actions", "general"]
    out, seen = [], set()
    for tab in tabs:
        for it in live.get("tabs", {}).get(tab, []):
            txt = " " + (it["titre"] + " " + it.get("resume", "")).lower() + " "
            if any(k in txt for k in a["kw"]) and it["url"] not in seen:
                seen.add(it["url"]); out.append({"titre": it["titre"], "source": it["source"], "url": it["url"], "ts": it["ts"]})
    return out[:4]

# ---------------- IA (facultatif, GitHub Models) ----------------
def ai_rewrite(items):
    tok = os.environ.get("GITHUB_TOKEN")
    if not tok: return None, "pas de jeton"
    brief = [{"actif": f"{i['name']} ({i['id']})", "prix": i["data"]["price"], "variations_%": i["data"]["ch"],
              "moyenne50": i["data"]["sma50"], "moyenne200": i["data"]["sma200"], "rsi": i["data"]["rsi"],
              "volatilite_annualisee_%": i["data"]["vol"], "support": i["data"]["support"], "resistance": i["data"]["resistance"],
              "verdict_regles": i["data"]["verdict"], "actus": [n["titre"] for n in i["news"]]} for i in items]
    prompt = ("Tu es un analyste de marché prudent qui écrit en français simple pour de jeunes investisseurs particuliers. "
              "Pour CHAQUE actif ci-dessous, écris 3 à 4 phrases d'analyse à partir UNIQUEMENT des données fournies (tendance, momentum, niveaux à surveiller, "
              "et lien éventuel avec les actus listées). Garde le verdict fourni. N'invente aucun chiffre ni aucune info. "
              "Pas de conseil d'achat ou de vente, pas d'objectif de prix. Réponds en JSON strict : {\"ID\": \"texte\", ...} avec les identifiants entre parenthèses.\n\n"
              + json.dumps(brief, ensure_ascii=False))
    errs = []
    for url, model in (("https://models.github.ai/inference/chat/completions", "openai/gpt-4o-mini"),
                       ("https://models.inference.ai.azure.com/chat/completions", "gpt-4o-mini")):
        body = json.dumps({"model": model, "temperature": 0.3, "messages": [{"role": "user", "content": prompt}]}).encode()
        req = urllib.request.Request(url, data=body, method="POST", headers={
            "Authorization": f"Bearer {tok}", "Content-Type": "application/json",
            "Accept": "application/vnd.github+json", "User-Agent": "le-brief-analysis", "X-GitHub-Api-Version": "2022-11-28"})
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                raw = resp.read(); final = resp.geturl()
            r = json.loads(raw)
            txt = r["choices"][0]["message"]["content"] or ""
            m = re.search(r"\{.*\}", txt, re.S)
            return json.loads(m.group(0) if m else txt), f"ok ({model})"
        except urllib.error.HTTPError as e:
            try: detail = e.read().decode("utf-8", "replace")[:160]
            except Exception: detail = ""
            errs.append(f"{url.split('/')[2]} HTTP {e.code} {detail}")
        except Exception as e:
            errs.append(f"{url.split('/')[2]} {str(e)[:120]} {locals().get('final','')}")
    return None, " | ".join(errs)

def main():
    out = {"updatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"), "assets": [], "errors": [], "method": "règles"}
    for a in ASSETS:
        try:
            closes, highs, lows, src = crypto_closes(a) if a["type"] == "crypto" else stock_closes(a)
            x = analyse(a, closes, highs, lows)
            news = related_news(a)
            out["assets"].append({"id": a["id"], "name": a["name"], "type": a["type"], "source": src, "data": x, "news": news,
                                  "text": rule_text(a, x, news)})
        except Exception as e:
            out["errors"].append(f"{a['id']} : {str(e)[:160]}")
        time.sleep(0.4)
    ai, status = ai_rewrite(out["assets"])
    out["ai"] = status
    if ai:
        for it in out["assets"]:
            t = ai.get(it["id"]) or ai.get(f"{it['name']} ({it['id']})")
            if isinstance(t, str) and len(t) > 60: it["text"] = t.strip(); it["textBy"] = "ia"
        out["method"] = "règles + IA"
    up = sum(1 for i in out["assets"] if i["data"]["verdict"] == "Haussier")
    down = sum(1 for i in out["assets"] if i["data"]["verdict"] == "Baissier")
    out["mood"] = {"haussier": up, "baissier": down, "neutre": len(out["assets"]) - up - down}
    json.dump(out, open(f"{ROOT}/analysis.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{len(out['assets'])} actifs, IA : {status}, erreurs : {out['errors']}")
    for i in out["assets"]:
        d = i["data"]; print(f" {i['id']:5} {fmt(d['price']):>10} 30j {sgn(d['ch']['30j']):>9} RSI {d['rsi'] or 0:4.0f} -> {d['verdict']} ({i['source']})")

if __name__ == "__main__":
    main()
