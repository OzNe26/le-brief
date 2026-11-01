#!/usr/bin/env python3
"""Génère audio.json : radios en direct (via radio-browser.info) + derniers épisodes de podcasts (via iTunes + flux RSS).
Uniquement la bibliothèque standard de Python. Lancé par .github/workflows/audio.yml."""
import json, re, sys, time, urllib.parse, urllib.request, xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

ROOT = __file__.rsplit("/scripts/", 1)[0]
UA = {"User-Agent": "LeBrief/1.0 (+https://ozne26.github.io/le-brief/)"}
RB_HOSTS = ["de1.api.radio-browser.info", "nl1.api.radio-browser.info", "at1.api.radio-browser.info", "fi1.api.radio-browser.info"]
ITUNES = "http://www.itunes.com/dtds/podcast-1.0.dtd"

def get(url, timeout=25):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()

def get_json(url):
    return json.loads(get(url).decode("utf-8", "replace"))

def rb(path):
    last = None
    for h in RB_HOSTS:
        try:
            return get_json(f"https://{h}{path}")
        except Exception as e:
            last = e
    raise last

def find_radio(src):
    if src.get("url"):  # flux connu et fiable, défini à la main
        return {"label": src["label"], "cat": src.get("cat", ""), "name": src["label"], "url": src["url"],
                "logo": src.get("logo", ""), "homepage": src.get("homepage", ""), "codec": "", "bitrate": 0, "uuid": ""}
    q = urllib.parse.urlencode({"name": src["q"], "countrycode": src.get("cc", ""), "order": "votes",
                                "reverse": "true", "hidebroken": "true", "limit": "25"})
    cands = []
    for i, st in enumerate(rb(f"/json/stations/search?{q}")):
        url = (st.get("url_resolved") or st.get("url") or "").strip()
        if not url.startswith("https://"):
            continue  # le site est en https : un flux http ne pourrait pas être lu
        name = (st.get("name") or "").strip()
        score = i
        if name.lower() == src["q"].lower() or name.lower() == src["label"].lower():
            score -= 100  # nom exact en priorité
        if ".m3u8" in url.lower():
            score += 50   # HLS : lisible seulement via hls.js, on préfère un flux direct
        cands.append((score, st, url))
    if not cands:
        return None
    _, st, url = sorted(cands, key=lambda c: c[0])[0]
    return {"label": src["label"], "cat": src.get("cat", ""), "name": st.get("name", "").strip(),
            "url": url, "logo": st.get("favicon", "") if (st.get("favicon") or "").startswith("https://") else "",
            "homepage": st.get("homepage", ""), "codec": st.get("codec", ""), "bitrate": st.get("bitrate", 0),
            "uuid": st.get("stationuuid", "")}

def clean(t, n=400):
    t = re.sub(r"<[^>]+>", " ", t or "")
    t = re.sub(r"\s+", " ", t).strip()
    return t[:n] + ("…" if len(t) > n else "")

def iso(d):
    try:
        return parsedate_to_datetime(d).astimezone(timezone.utc).isoformat()
    except Exception:
        return ""

def find_podcast(src):
    q = urllib.parse.urlencode({"term": src["q"], "media": "podcast", "country": "FR", "limit": "5"})
    res = get_json(f"https://itunes.apple.com/search?{q}").get("results", [])
    res = [r for r in res if r.get("feedUrl")]
    max_age = src.get("maxAgeDays", 60)
    for p in res[:5]:
        try:
            out = parse_show(p, src)
        except Exception:
            continue
        if out["episodes"] and out["episodes"][0]["date"]:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(out["episodes"][0]["date"])).days
            if age <= max_age:
                return out  # podcast encore actif
    return None

def parse_show(p, src):
    root = ET.fromstring(get(p["feedUrl"], timeout=40))
    ch = root.find("channel")
    eps = []
    for it in ch.findall("item"):
        enc = it.find("enclosure")
        if enc is None or not (enc.get("url") or "").startswith("http"):
            continue
        dur = it.findtext(f"{{{ITUNES}}}duration") or ""
        eps.append({"title": clean(it.findtext("title"), 200), "date": iso(it.findtext("pubDate") or ""),
                    "audio": enc.get("url").replace("http://", "https://", 1), "duration": dur.strip(),
                    "desc": clean(it.findtext("description") or it.findtext(f"{{{ITUNES}}}summary"), 260)})
        if len(eps) >= 6:
            break
    return {"name": p.get("collectionName", ""), "author": p.get("artistName", ""), "cat": src.get("cat", ""),
            "image": p.get("artworkUrl600") or p.get("artworkUrl100") or "", "apple": p.get("collectionViewUrl", ""),
            "feed": p["feedUrl"], "query": src["q"], "episodes": eps}

def main():
    sources = json.load(open(f"{ROOT}/scripts/audio_sources.json", encoding="utf-8"))
    out = {"updatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"), "radios": [], "podcasts": [], "errors": []}
    for s in sources["radios"]:
        try:
            r = find_radio(s)
            if r: out["radios"].append(r)
            else: out["errors"].append(f"radio introuvable en https : {s['label']}")
        except Exception as e:
            out["errors"].append(f"radio {s['label']} : {e}")
        time.sleep(0.3)
    for s in sources["podcasts"]:
        try:
            p = find_podcast(s)
            if p and p["episodes"]: out["podcasts"].append(p)
            else: out["errors"].append(f"podcast introuvable : {s['q']}")
        except Exception as e:
            out["errors"].append(f"podcast {s['q']} : {e}")
        time.sleep(0.3)
    json.dump(out, open(f"{ROOT}/audio.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{len(out['radios'])} radios, {len(out['podcasts'])} podcasts, {len(out['errors'])} erreurs")
    for e in out["errors"]: print(" -", e)

if __name__ == "__main__":
    main()
