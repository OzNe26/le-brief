#!/usr/bin/env python3
"""Petit client pour l'IA gratuite Gemini (Google AI Studio). Bibliothèque standard uniquement.
La clé est lue dans la variable d'environnement GEMINI_API_KEY (secret GitHub), jamais écrite dans le dépôt."""
import json, os, re, time, urllib.error, urllib.request

# « -latest » suit toujours la version actuelle (les anciens noms comme gemini-2.5-flash sont retirés).
MODELS = ["gemini-flash-latest", "gemini-flash-lite-latest"]
URL = "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent"


def has_key():
    return bool(os.environ.get("GEMINI_API_KEY", "").strip())


def ask_json(prompt, temperature=0.4, max_tokens=8192):
    """Envoie le prompt et renvoie (objet JSON, modèle utilisé). Lève RuntimeError si tout échoue."""
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("pas de clé GEMINI_API_KEY")
    body = json.dumps({
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens,
                             "responseMimeType": "application/json"},
    }).encode()
    errs = []
    # 1er passage rapide : si un modèle est saturé, on passe tout de suite au suivant.
    # 2e passage : on réessaie après une petite attente (les pics de demande sont passagers).
    for wait in (0, 25):
        for model in MODELS:
            if wait: time.sleep(wait)
            req = urllib.request.Request(URL.format(model), data=body, method="POST", headers={
                "Content-Type": "application/json", "x-goog-api-key": key})
            try:
                with urllib.request.urlopen(req, timeout=180) as r:
                    data = json.loads(r.read())
                parts = data["candidates"][0]["content"]["parts"]
                txt = "".join(p.get("text", "") for p in parts if not p.get("thought"))
                m = re.search(r"\{.*\}", txt, re.S)
                out = json.loads(m.group(0) if m else txt)
                if errs: print("  (IA) essais précédents :", " | ".join(errs)[:400])
                return out, model
            except urllib.error.HTTPError as e:
                try: detail = json.loads(e.read()).get("error", {}).get("message", "")[:120]
                except Exception: detail = ""
                errs.append(f"{model} HTTP {e.code} {detail}")
            except Exception as e:
                errs.append(f"{model} {str(e)[:120]}")
    raise RuntimeError(" | ".join(errs)[-900:])
