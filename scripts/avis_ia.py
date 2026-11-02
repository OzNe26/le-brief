#!/usr/bin/env python3
"""« Le panel des IA » : 4 IA gratuites donnent chacune leur avis sur les 10 actifs, avec un style d'analyste différent.
Chaque clé est lue dans les secrets GitHub (variables d'environnement), jamais écrite dans le dépôt.
Une IA sans clé ou en panne est simplement ignorée : son dernier avis réussi est conservé."""
import json, os, re, sys, time, urllib.error, urllib.request
from datetime import datetime, timezone

sys.path.insert(0, __file__.rsplit("/", 1)[0])
import gemini

STYLES = {
    "prudent": ("Le prudent", "🛡️",
                "Tu es un investisseur prudent, orienté long terme et gestion du risque. Tu regardes d'abord ce qui peut mal "
                "tourner, la volatilité et la tendance de fond (moyenne 200 jours), et tu te méfies des emballements."),
    "technique": ("Le technicien", "📐",
                  "Tu es un analyste technique orienté court terme (quelques jours à quelques semaines). Tu raisonnes avec le RSI, "
                  "les moyennes 50 et 200 jours, les supports et résistances et le momentum récent."),
    "contrarian": ("Le contrarien", "🔄",
                   "Tu es un investisseur contrarien : tu cherches ce que le marché exagère ou ignore. Tu regardes si la peur ou "
                   "l'euphorie semblent excessives (RSI extrême, chute ou hausse brutale) et tu donnes l'argument opposé au consensus, "
                   "sans jamais être certain."),
    "macro": ("Le stratège", "🌍",
              "Tu es un stratège qui relie les marchés à l'actualité : régulation, résultats d'entreprises, taux, élections, "
              "piratages, flux des ETF. Tu expliques comment les actus du moment peuvent peser sur chaque actif."),
}

# Chaque IA reçoit un style différent. type "gemini" ou "openai" (API compatible OpenAI).
PANEL = [
    {"id": "gemini", "nom": "Gemini", "editeur": "Google", "style": "prudent", "type": "gemini", "env": "GEMINI_API_KEY"},
    {"id": "mistral", "nom": "Mistral", "editeur": "Mistral AI", "style": "technique", "type": "openai", "env": "MISTRAL_API_KEY",
     "url": "https://api.mistral.ai/v1/chat/completions", "models": ["ministral-14b-latest", "ministral-8b-latest"]},
    {"id": "gptoss", "nom": "GPT-OSS", "editeur": "OpenAI, via Groq", "style": "macro", "type": "openai", "env": "GROQ_API_KEY",
     "url": "https://api.groq.com/openai/v1/chat/completions", "models": ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]},
    {"id": "qwen", "nom": "Qwen", "editeur": "Alibaba, via Groq", "style": "contrarian", "type": "openai", "env": "GROQ_API_KEY",
     "url": "https://api.groq.com/openai/v1/chat/completions", "models": ["qwen/qwen3.8-27b", "openai/gpt-oss-20b"]},
]


def openai_json(ia, prompt, temperature=0.6):
    key = os.environ.get(ia["env"], "").strip()
    errs = []
    for model in ia["models"]:
        for attempt in range(2):
            body = json.dumps({"model": model, "temperature": temperature, "max_tokens": 4000,
                               "response_format": {"type": "json_object"},
                               "messages": [{"role": "system", "content": "Tu réponds uniquement en JSON valide, en français."},
                                            {"role": "user", "content": prompt}]}).encode()
            req = urllib.request.Request(ia["url"], data=body, method="POST", headers={
                "Authorization": f"Bearer {key}", "Content-Type": "application/json", "User-Agent": "le-brief-invest"})
            try:
                with urllib.request.urlopen(req, timeout=150) as r:
                    data = json.loads(r.read())
                txt = data["choices"][0]["message"]["content"] or ""
                txt = re.sub(r"<think>.*?</think>", "", txt, flags=re.S)
                m = re.search(r"\{.*\}", txt, re.S)
                return json.loads(m.group(0) if m else txt), model
            except urllib.error.HTTPError as e:
                try: detail = e.read().decode("utf-8", "replace")[:150]
                except Exception: detail = ""
                errs.append(f"{model} HTTP {e.code} {detail}")
                if e.code == 429 and attempt == 0:
                    time.sleep(30); continue
                break
            except Exception as e:
                errs.append(f"{model} {str(e)[:120]}")
                break
    raise RuntimeError(" | ".join(errs)[-600:])


def build_prompt(style, items):
    brief = [{"id": i["id"], "actif": i["name"], "prix_usd": round(i["data"]["price"], 2 if i["data"]["price"] < 100 else 0),
              "var_%": {k: (round(v, 1) if v is not None else None) for k, v in i["data"]["ch"].items()},
              "mm50": round(i["data"]["sma50"] or 0, 2), "mm200": round(i["data"]["sma200"] or 0, 2),
              "rsi": round(i["data"]["rsi"] or 0), "vol_%": round(i["data"]["vol"] or 0),
              "support": round(i["data"]["support"], 2), "resistance": round(i["data"]["resistance"], 2),
              "actus": [n["titre"][:110] for n in i["news"][:2]]} for i in items]
    nom, _, persona = STYLES[style]
    return (f"{persona}\nTu tiens la rubrique « {nom} » du site français Le Brief Invest, lu par de jeunes investisseurs particuliers. "
            "À partir UNIQUEMENT des données ci-dessous, donne ton opinion personnelle en français simple, fidèle à ton style.\n"
            "Réponds en JSON strict : {\"global\": \"3 à 5 phrases : ta lecture d'ensemble du marché\", "
            "\"assets\": {\"ID\": {\"avis\": \"2 à 3 phrases qui commencent par 'Mon avis : '\", "
            "\"tendance\": \"haussier|neutre|baissier\"}}} avec une entrée pour chaque ID.\n"
            "Règles : n'invente aucun chiffre ni aucune info absente des données ; aucun conseil d'achat ou de vente ; "
            "aucun objectif de prix ; reste nuancé quand le signal est incertain.\n\n"
            + json.dumps(brief, ensure_ascii=False, separators=(",", ":")))


def flat(x):
    """Certaines IA renvoient un dict ou une liste au lieu d'un texte : on remet tout à plat, sans markdown."""
    if isinstance(x, dict): x = " ".join(flat(v) for v in x.values())
    elif isinstance(x, (list, tuple)): x = " ".join(flat(v) for v in x)
    x = re.sub(r"\*\*|__|^#+\s*", "", str(x or ""))
    return re.sub(r"\s+", " ", x).strip()


def clean(res, ids):
    assets = {}
    for k, v in (res.get("assets") or {}).items():
        if k not in ids: continue
        if not isinstance(v, dict): v = {"avis": v}
        t = flat(v.get("avis"))
        s = str(v.get("tendance") or "").lower().strip()
        if len(t) < 40: continue
        assets[k] = {"avis": t[:600], "tendance": s if s in ("haussier", "neutre", "baissier") else "neutre"}
    glob = flat(res.get("global"))
    if len(glob) < 60 or len(assets) < max(1, len(ids) // 2): return None
    return glob[:1200], assets


def run(items, previous=None):
    """Renvoie (liste des avis, journal)."""
    prev = {a.get("id"): a for a in (previous or []) if isinstance(a, dict)}
    ids = {i["id"] for i in items}
    out, log = [], []
    for ia in PANEL:
        if not os.environ.get(ia["env"], "").strip():
            log.append(f"{ia['nom']} : pas de clé {ia['env']}")
            if ia["id"] in prev: out.append(prev[ia["id"]])
            continue
        prompt = build_prompt(ia["style"], items)
        try:
            if ia["type"] == "gemini":
                res, model = gemini.ask_json(prompt, temperature=0.6)
            else:
                res, model = openai_json(ia, prompt)
            ok = clean(res, ids)
            if not ok: raise RuntimeError("réponse incomplète")
            glob, assets = ok
            nom, emoji, _ = STYLES[ia["style"]]
            out.append({"id": ia["id"], "nom": ia["nom"], "editeur": ia["editeur"], "style": nom, "emoji": emoji,
                        "modele": model, "updatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        "global": glob, "assets": assets})
            log.append(f"{ia['nom']} : ok ({model}, {len(assets)} actifs)")
        except Exception as e:
            log.append(f"{ia['nom']} : échec {str(e)[:300]}")
            if ia["id"] in prev: out.append(prev[ia["id"]])
        time.sleep(3)
    return out, log
