#!/usr/bin/env python3
"""Fil d'actus en direct : lit des flux RSS/Atom et écrit news_live.json. Bibliothèque standard uniquement."""
import html, json, re, sys, urllib.request, xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

ROOT = __file__.rsplit("/scripts/", 1)[0]
UA = {"User-Agent": "Mozilla/5.0 (compatible; LeBriefBot/1.0; +https://ozne26.github.io/le-brief/)",
      "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, */*;q=0.8"}
NOW = datetime.now(timezone.utc)
MAX_AGE = timedelta(hours=24)   # on garde toute la journée (24 h glissantes)
PER_TAB = 400
PER_SOURCE = 60
NS = {"media": "http://search.yahoo.com/mrss/", "atom": "http://www.w3.org/2005/Atom",
      "content": "http://purl.org/rss/1.0/modules/content/", "dc": "http://purl.org/dc/elements/1.1/"}

def fetch(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()

def clean(t, n=300):
    t = html.unescape(re.sub(r"<[^>]+>", " ", html.unescape(t or "")))
    t = re.sub(r"\s+", " ", t).strip()
    return (t[:n].rsplit(" ", 1)[0] + "…") if len(t) > n else t

def pdate(s):
    s = (s or "").strip()
    if not s: return None
    try:
        d = parsedate_to_datetime(s)
    except Exception:
        try:
            d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            return None
    if d.tzinfo is None: d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)

def first_img(el):
    for tag in ("media:content", "media:thumbnail"):
        for m in el.findall(tag, NS):
            u = m.get("url", "")
            if u.startswith("http") and (m.get("medium") in (None, "image") or re.search(r"\.(jpe?g|png|webp)", u, re.I)):
                return u
    enc = el.find("enclosure")
    if enc is not None and (enc.get("type") or "").startswith("image") and (enc.get("url") or "").startswith("http"):
        return enc.get("url")
    m = re.search(r'<img[^>]+src="(https?://[^"]+)"', (el.findtext("description") or "") + (el.findtext("content:encoded", namespaces=NS) or ""))
    return m.group(1) if m else ""

def parse(raw, src):
    root = ET.fromstring(raw)
    out = []
    items = root.findall(".//item") or root.findall(".//atom:entry", NS)
    for it in items:
        title = clean(it.findtext("title") or it.findtext("atom:title", namespaces=NS), 220)
        link = (it.findtext("link") or "").strip()
        if not link:
            l = it.find("atom:link", NS)
            link = l.get("href", "") if l is not None else ""
        d = pdate(it.findtext("pubDate") or it.findtext("dc:date", namespaces=NS) or it.findtext("atom:updated", namespaces=NS) or it.findtext("atom:published", namespaces=NS))
        if not title or not link.startswith("http") or d is None: continue
        if d > NOW + timedelta(minutes=10) or NOW - d > MAX_AGE: continue
        source = src["name"]
        if "news.google.com" in src["url"]:
            s_el = it.find("source")
            if s_el is not None and (s_el.text or "").strip():
                source = s_el.text.strip()
            title = re.sub(r"\s+-\s+[^-]{2,60}$", "", title)  # retire « - Nom du média » ajouté par Google
            summary = ""
        else:
            summary = clean(it.findtext("description") or it.findtext("atom:summary", namespaces=NS) or it.findtext("content:encoded", namespaces=NS), 300)
            if summary.lower().startswith(title.lower()[:40]): summary = summary[len(title):].strip(" .:-—")
        out.append({"titre": title, "resume": summary, "url": link, "source": source, "ts": d.isoformat(timespec="seconds"),
                    "img": first_img(it), "categorie": src.get("cat", ""), "via": src["name"]})
    return out

def norm(t):
    t = re.sub(r"[^a-z0-9àâäéèêëîïôöùûüç ]", "", t.lower())
    return " ".join(t.split()[:10])

def main():
    sources = json.load(open(f"{ROOT}/scripts/news_sources.json", encoding="utf-8"))
    filters = sources.pop("_filters", {})
    block = {b.lower() for b in filters.get("blocklist", [])}
    kws = filters.get("keywords", {})
    report = {}
    jobs = [(tab, s) for tab, lst in sources.items() for s in lst]
    def run(job):
        tab, s = job
        try:
            return tab, s, parse(fetch(s["url"]), s), ""
        except Exception as e:
            return tab, s, [], str(e)[:120]
    with ThreadPoolExecutor(max_workers=12) as ex:
        results = list(ex.map(run, jobs))
    out = {"updatedAt": NOW.isoformat(timespec="seconds"), "tabs": {}, "sources": {}}
    # Les flux RSS ne gardent que leurs derniers articles : on reprend le fil précédent
    # pour ne pas perdre les infos du matin quand on lit le soir.
    try:
        prev = json.load(open(f"{ROOT}/news_live.json", encoding="utf-8")).get("tabs", {})
    except Exception:
        prev = {}
    for tab in sources:
        items, seen = [], set()
        for t, s, its, err in results:
            if t != tab: continue
            report.setdefault(tab, []).append(f"{s['name']}: {len(its)}" + (f" ERREUR {err}" if err else ""))
            out["sources"].setdefault(tab, []).append({"name": s["name"], "count": len(its), "ok": not err})
            for it in its:
                if it["source"].lower() in block: continue
                if not s.get("trusted") and tab in kws:
                    txt = (it["titre"] + " " + it["resume"]).lower()
                    if not any(k in txt for k in kws[tab]): continue
                items.append(it)
        for it in prev.get(tab, []):
            try: d = datetime.fromisoformat(it["ts"])
            except Exception: continue
            if NOW - d > MAX_AGE or it.get("source", "").lower() in block: continue
            it["_old"] = True
            items.append(it)
        items.sort(key=lambda x: x.get("_old", False))  # à titre égal, la version fraîche passe devant
        items.sort(key=lambda x: x["ts"], reverse=True)
        kept, per = [], {}
        for it in items:
            k = norm(it["titre"])
            if k in seen: continue
            if per.get(it["source"], 0) >= PER_SOURCE: continue
            seen.add(k); per[it["source"]] = per.get(it["source"], 0) + 1
            it.pop("_old", None)
            kept.append(it)
            if len(kept) >= PER_TAB: break
        out["tabs"][tab] = kept
    json.dump(out, open(f"{ROOT}/news_live.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    for tab, lines in report.items():
        print(f"== {tab} ({len(out['tabs'][tab])} infos)")
        for l in lines: print("  ", l)

if __name__ == "__main__":
    main()
