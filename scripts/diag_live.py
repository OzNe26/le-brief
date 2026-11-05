import json, os, urllib.request, asyncio
key = os.environ["GEMINI_API_KEY"].strip()
ms = json.loads(urllib.request.urlopen(urllib.request.Request("https://generativelanguage.googleapis.com/v1beta/models?pageSize=200", headers={"x-goog-api-key": key})).read())["models"]
live = [m for m in ms if "bidiGenerateContent" in m.get("supportedGenerationMethods", []) or "live" in m["name"]]
for m in live: print(m["name"], m.get("displayName"), m.get("supportedGenerationMethods"))
import websockets
URL = "wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent?key=" + key
async def test(name, modality):
    try:
        async with websockets.connect(URL, max_size=None, open_timeout=20) as ws:
            setup = {"model": name, "generationConfig": {"responseModalities": [modality]}}
            if modality == "AUDIO": setup["outputAudioTranscription"] = {}
            await ws.send(json.dumps({"setup": setup}))
            print(" setup:", (await asyncio.wait_for(ws.recv(), 20))[:120])
            await ws.send(json.dumps({"clientContent": {"turns": [{"role": "user", "parts": [{"text": 'Réponds en JSON {"ok":true,"mot":"<un mot français>"}'}]}], "turnComplete": True}}))
            txt = ""
            while True:
                msg = json.loads(await asyncio.wait_for(ws.recv(), 60))
                sc = msg.get("serverContent", {})
                for p in sc.get("modelTurn", {}).get("parts", []):
                    if "text" in p: txt += p["text"]
                if "outputTranscription" in sc: txt += sc["outputTranscription"].get("text", "")
                if sc.get("turnComplete"): break
            print(" OK", name, modality, repr(txt[:200]))
    except Exception as e:
        print(" ECHEC", name, modality, str(e)[:200])
async def main():
    for m in live:
        for mod in ("TEXT", "AUDIO"):
            await test(m["name"], mod)
asyncio.run(main())
