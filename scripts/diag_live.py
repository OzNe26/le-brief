import json, os, asyncio, time, websockets
key = os.environ["GEMINI_API_KEY"].strip()
URL = "wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent?key=" + key
P = ("Tu es analyste. Pour chacun de ces 12 actifs : Bitcoin, Ethereum, Solana, XRP, CAC 40, S&P 500, Nasdaq, Nvidia, Apple, Tesla, Or, Euro/dollar, "
     "écris un avis de 3 phrases en français. Réponds UNIQUEMENT en JSON : {\"avis\":[{\"actif\":\"...\",\"texte\":\"...\",\"tendance\":\"hausse|baisse|neutre\"}]}")
async def test(name, extra):
    t0 = time.time()
    try:
        async with websockets.connect(URL, max_size=None, open_timeout=20) as ws:
            setup = {"model": name, "generationConfig": {"responseModalities": ["AUDIO"], **extra}, "outputAudioTranscription": {},
                     "systemInstruction": {"parts": [{"text": "Tu réponds uniquement par le JSON demandé, sans rien lire à voix haute d'autre."}]}}
            await ws.send(json.dumps({"setup": setup})); await asyncio.wait_for(ws.recv(), 20)
            await ws.send(json.dumps({"clientContent": {"turns": [{"role": "user", "parts": [{"text": P}]}], "turnComplete": True}}))
            txt = ""
            while True:
                msg = json.loads(await asyncio.wait_for(ws.recv(), 120))
                sc = msg.get("serverContent", {})
                if "outputTranscription" in sc: txt += sc["outputTranscription"].get("text", "")
                if sc.get("turnComplete"): break
        try:
            import re; d = json.loads(re.search(r"\{.*\}", txt, re.S).group(0)); ok = len(d["avis"])
        except Exception as e: ok = f"JSON invalide {e}"
        print(f"{name}: {time.time()-t0:.0f}s, {len(txt)} caractères, avis={ok}\n  {txt[:300]!r}")
    except Exception as e:
        print(f"{name}: ECHEC après {time.time()-t0:.0f}s {str(e)[:200]}")
async def main():
    await test("models/gemini-3.1-flash-live-preview", {})
    await test("models/gemini-3.8-live", {})
asyncio.run(main())
