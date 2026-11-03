#!/usr/bin/env python3
"""Robot « L'essentiel » : à partir du fil en direct (news_live.json), l'IA Gemini écrit le résumé de chaque
onglet, choisit les infos à retenir et repère les signaux faibles. Les titres, sources et liens viennent
toujours du fil réel : l'IA ne fait que choisir et reformuler, elle n'invente aucun lien."""
import json, sys, time
from datetime import datetime, timezone, timedelta

sys.path.insert(0, __file__.rsplit("/", 1)[0])
import gemini

ROOT = __file__.rsplit("/scripts/", 1)[0]
NOW = datetime.now(timezone.utc)
PARIS = timezone(timedelta(hours=1))  # assez précis pour l'affichage « 2 nov. »
MOIS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]
TABS = {
    "general": "toute l'actualité (France, monde, tech, culture), jamais le sport, pas seulement l'investissement",
    "crypto": "les cryptomonnaies (Bitcoin, Ethereum, altcoins, régulation, plateformes)",
    "actions": "la Bourse et les actions (CAC 40, Wall Street, résultats d'entreprises, macroéconomie)",
    "immo": "l'immobilier en France (taux de crédit, prix, SCPI, fiscalité, marché)",
}
CATS = ["France", "Monde", "Tech", "Culture", "Économie"]


def fr_date(ts):
    try: d = datetime.fromisoformat(ts).astimezone(PARIS)
    except Exception: d = NOW.astimezone(PARIS)
    return f"{d.day} {MOIS[d.month - 1]}"


def pct(v):
    return ("+" if v >= 0 else "−") + f"{abs(v):.2f}".replace(".", ",") + " %"


def money(v):
    s = f"{v:,.0f}" if v >= 100 else f"{v:,.2f}"
    return "≈ " + s.replace(",", " ").replace(".", ",") + " $"


def chiffres_from_analysis(tab, analysis):
    want = {"crypto": ["BTC", "ETH", "SOL", "XRP"], "actions": ["NVDA", "AAPL", "MSFT", "TSLA"]}.get(tab)
    if not want or not analysis: return []
    by = {a["id"]: a for a in analysis.get("assets", [])}
    out = []
    for i in want:
        a = by.get(i)
        if not a: continue
        ch = a["data"]["ch"].get("1j")
        if ch is None: continue
        out.append({"label": f"{a['name']} ({i})", "valeur": money(a["data"]["price"]),
                    "variation": pct(ch) + (" (24 h)" if tab == "crypto" else " (séance)"),
                    "sens": "hausse" if ch > 0.15 else "baisse" if ch < -0.15 else "flat"})
    return out


def pick_items(tab, live):
    """Infos des 14 dernières heures (sinon 24 h), 70 max, pour le prompt."""
    items = live.get("tabs", {}).get(tab, [])
    for h in (14, 24):
        sel = [i for i in items if NOW - datetime.fromisoformat(i["ts"]) <= timedelta(hours=h)]
        if len(sel) >= 15: break
    return sel[:70]


def build_prompt(tab, items, with_niche):
    lst = "\n".join(f"[{k}] {i['titre']} — {i.get('resume','')[:220]} ({i['source']}, {fr_date(i['ts'])})"
                    for k, i in enumerate(items))
    niche = (
        "\n- \"niche\" : 3 à 5 SIGNAUX FAIBLES choisis dans la liste : des infos peu relayées mais utiles pour un "
        "investisseur (petite valeur qui bouge, déblocage de tokens, changement de taux, mesure fiscale, rachat, "
        "flux d'ETF, donnée de marché précise…). Évite les gros titres déjà évidents. Pour chacun : "
        "{\"n\": numéro, \"resume\": \"le fait en 1 phrase\", \"pourquoi\": \"en quoi c'est utile : quel actif ou secteur, "
        "quoi surveiller (1 à 2 phrases)\", \"impact\": \"hausse|baisse|flat\"}."
    ) if with_niche else ""
    cat = (f" Ajoute \"categorie\" parmi {CATS}." if tab == "general" else
           " Ajoute \"impact\" : \"hausse\", \"baisse\" ou \"flat\" pour le marché concerné.")
    return (
        f"Tu écris pour « Le Brief Invest », un site d'actus en français pour de jeunes investisseurs particuliers. "
        f"Rubrique : {TABS[tab]}. Voici les infos des dernières heures, numérotées :\n\n{lst}\n\n"
        "Réponds en JSON strict avec :\n"
        "- \"resume\" : l'essentiel de la rubrique aujourd'hui en 3 phrases maximum, en langage simple et neutre. "
        "Uniquement des faits présents dans la liste.\n"
        "- \"items\" : les 6 infos les plus importantes à retenir, des plus importantes aux moins importantes, sans doublon "
        "de sujet. Pour chacune : {\"n\": numéro, \"resume\": \"1 à 2 phrases reformulées avec tes mots\"}." + cat + niche +
        "\nRègles : n'invente aucun fait ni aucun chiffre absent de la liste ; reformule, ne recopie pas ; ton neutre sur la "
        "politique ; aucun conseil d'achat ou de vente. Les numéros doivent exister dans la liste et ne pas se répéter entre "
        "\"items\" et \"niche\"."
    )


def card(src, extra):
    return {"titre": src["titre"], "resume": (extra.get("resume") or src.get("resume") or "").strip()[:400],
            "source": src["source"], "url": src["url"], "date": fr_date(src["ts"])}


def main():
    if not gemini.has_key():
        print("Pas de clé GEMINI_API_KEY dans les secrets GitHub : rien à faire."); return
    live = json.load(open(f"{ROOT}/news_live.json", encoding="utf-8"))
    try: analysis = json.load(open(f"{ROOT}/analysis.json", encoding="utf-8"))
    except Exception: analysis = None
    try: data = json.load(open(f"{ROOT}/data.json", encoding="utf-8"))
    except Exception: data = {}
    changed = False
    for tab in TABS:
        items = pick_items(tab, live)
        if len(items) < 6:
            print(f"{tab} : trop peu d'infos ({len(items)}), on garde l'ancien."); continue
        with_niche = tab != "general"
        try:
            res, model = gemini.ask_json(build_prompt(tab, items, with_niche))
        except Exception as e:
            print(f"{tab} : échec IA → on garde l'ancien. {e}"); continue
        used, its, niche = set(), [], []
        for x in res.get("items") or []:
            n = x.get("n") if isinstance(x, dict) else None
            if not isinstance(n, int) or not 0 <= n < len(items) or n in used: continue
            used.add(n); c = card(items[n], x)
            if tab == "general":
                c["impact"] = "flat"; c["categorie"] = x.get("categorie") if x.get("categorie") in CATS else (items[n].get("categorie") or "France")
            else:
                c["impact"] = x.get("impact") if x.get("impact") in ("hausse", "baisse", "flat") else "flat"
            its.append(c)
        for x in (res.get("niche") or []) if with_niche else []:
            n = x.get("n") if isinstance(x, dict) else None
            if not isinstance(n, int) or not 0 <= n < len(items) or n in used or not x.get("pourquoi"): continue
            used.add(n); c = card(items[n], x)
            c["pourquoi"] = str(x["pourquoi"]).strip()[:400]
            c["impact"] = x.get("impact") if x.get("impact") in ("hausse", "baisse", "flat") else "flat"
            niche.append(c)
        resume = str(res.get("resume") or "").strip()
        if len(resume) < 40 or len(its) < 3:
            print(f"{tab} : réponse IA incomplète → on garde l'ancien."); continue
        new = {"updatedAt": NOW.isoformat(timespec="seconds"), "resume": resume[:700],
               "chiffres": chiffres_from_analysis(tab, analysis), "items": its, "par": "ia", "modele": model}
        if with_niche: new["niche"] = niche[:5]
        data[tab] = new; changed = True
        print(f"{tab} : OK ({model}) · {len(its)} à retenir · {len(niche)} signaux faibles")
        time.sleep(6)
    if changed:
        json.dump(data, open(f"{ROOT}/data.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
