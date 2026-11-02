#!/usr/bin/env python3
"""Petit client pour l'IA gratuite Gemini (Google AI Studio). Bibliothèque standard uniquement.
La clé est lue dans la variable d'environnement GEMINI_API_KEY (secret GitHub), jamais écrite dans le dépôt."""
import json, os, re, time, urllib.error, urllib.request

MODELS = ["gemini-2.5-flash", "gemini-flash-latest", "gemini-2.5-flash-lite", "gemini-flash-lite-latest"]
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
    for model in MODELS:
        for attempt in range(3):
            req = urllib.request.Request(URL.format(model), data=body, method="POST", headers={
                "Content-Type": "application/json", "x-goog-api-key": key})
            try:
                with urllib.request.urlopen(req, timeout=180) as r:
                    data = json.loads(r.read())
                parts = data["candidates"][0]["content"]["parts"]
                txt = "".join(p.get("text", "") for p in parts if not p.get("thought"))
                m = re.search(r"\{.*\}", txt, re.S)
                return json.loads(m.group(0) if m else txt), model
            except urllib.error.HTTPError as e:
                try: detail = e.read().decode("utf-8", "replace")[:200]
                except Exception: detail = ""
                errs.append(f"{model} HTTP {e.code} {detail}")
                if e.code in (429, 500, 503) and attempt < 2:
                    time.sleep(20 * (attempt + 1)); continue
                break  # 400/403/404 : on passe au modèle suivant
            except Exception as e:
                errs.append(f"{model} {str(e)[:150]}")
                if attempt < 1:
                    time.sleep(5); continue
                break
    raise RuntimeError(" | ".join(errs)[-900:])
