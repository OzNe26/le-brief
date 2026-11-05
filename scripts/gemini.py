#!/usr/bin/env python3
"""Petit client pour l'IA gratuite Gemini (Google AI Studio). Bibliothèque standard uniquement.
La clé est lue dans la variable d'environnement GEMINI_API_KEY (secret GitHub), jamais écrite dans le dépôt."""
import json, os, re, time, urllib.error, urllib.request

# 1er choix : Gemini 3.1 Flash Live (Live API, quota gratuit sans limite de requêtes par minute).
# Le modèle ne sait répondre qu'en audio : on lit sa transcription texte (rapide : ~5 s pour 4 000 caractères).
LIVE_MODELS = ["gemini-3.1-flash-live-preview"]
LIVE_URL = "wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"
# Secours (API classique) : « -latest » suit toujours la version actuelle.
MODELS = ["gemini-flash-latest", "gemini-flash-lite-latest"]
URL = "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent"


def has_key():
    return bool(os.environ.get("GEMINI_API_KEY", "").strip())


def _parse(txt):
    txt = re.sub(r"```(?:json)?", "", txt)
    m = re.search(r"\{.*\}", txt, re.S)
    return json.loads(m.group(0) if m else txt)


def _live(model, key, prompt, temperature):
    """Une question à un modèle Live (WebSocket). Renvoie le texte de la réponse."""
    import asyncio
    import websockets  # installé par le workflow (pip install websockets)

    async def go():
        async with websockets.connect(f"{LIVE_URL}?key={key}", max_size=None, open_timeout=20) as ws:
            await ws.send(json.dumps({"setup": {
                "model": f"models/{model}",
                "generationConfig": {"responseModalities": ["AUDIO"], "temperature": temperature},
                "outputAudioTranscription": {},
                "systemInstruction": {"parts": [{"text": "Tu réponds uniquement par le JSON demandé, en français, sans aucun texte autour."}]}}}))
            await asyncio.wait_for(ws.recv(), 30)
            await ws.send(json.dumps({"clientContent": {"turns": [{"role": "user", "parts": [{"text": prompt}]}], "turnComplete": True}}))
            txt = ""
            while True:
                msg = json.loads(await asyncio.wait_for(ws.recv(), 150))
                sc = msg.get("serverContent", {})
                if "outputTranscription" in sc: txt += sc["outputTranscription"].get("text", "")
                if sc.get("turnComplete"): break
            return txt
    return asyncio.run(asyncio.wait_for(go(), 300))


def ask_json(prompt, temperature=0.4, max_tokens=8192):
    """Envoie le prompt et renvoie (objet JSON, modèle utilisé). Lève RuntimeError si tout échoue."""
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("pas de clé GEMINI_API_KEY")
    errs = []
    for model in LIVE_MODELS:
        for attempt in (1, 2):
            try:
                out = _parse(_live(model, key, prompt, temperature))
                if errs: print("  (IA) essais précédents :", " | ".join(errs)[:400])
                return out, model
            except ImportError:
                errs.append("Live : module websockets absent"); break
            except Exception as e:
                errs.append(f"{model} essai {attempt} : {str(e)[:120]}")
                time.sleep(5)
    body = json.dumps({
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens,
                             "responseMimeType": "application/json"},
    }).encode()
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
                out = _parse(txt)
                if errs: print("  (IA) essais précédents :", " | ".join(errs)[:400])
                return out, model
            except urllib.error.HTTPError as e:
                try: detail = json.loads(e.read()).get("error", {}).get("message", "")[:120]
                except Exception: detail = ""
                errs.append(f"{model} HTTP {e.code} {detail}")
            except Exception as e:
                errs.append(f"{model} {str(e)[:120]}")
    raise RuntimeError(" | ".join(errs)[-900:])
