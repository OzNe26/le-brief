#!/usr/bin/env python3
"""Robot d'alertes : envoie une notification ntfy (appli gratuite) quand un mot de la liste à surveiller d'un membre
sort dans les actus, ou quand un de ses actifs bouge fort sur 24 h. Tourne dans la boucle du fil en direct.
Les réglages viennent de Supabase via une fonction protégée par le secret ALERT_SECRET (secret GitHub).
L'état (alertes déjà envoyées) est stocké anonymisé (empreintes) dans alerts_state.json."""
import hashlib, json, os, re, unicodedata, urllib.request
from datetime import datetime, timezone, timedelta

ROOT = __file__.rsplit("/scripts/", 1)[0]
SB_URL = "https://rxuhvllidrjifyporkao.supabase.co"
SB_KEY = "sb_publishable_N42bTU1DF11LH9mC7K6QYQ_POOJ2ZK2"   # clé publique du site (pas un secret)
SITE = "https://ozne26.github.io/le-brief/"
NOW = datetime.now(timezone.utc)
TODAY = (NOW + timedelta(hours=1)).strftime("%Y-%m-%d")  # jour à Paris (à 1 h près)
MAX_PER_RUN = 5


def h(x): return hashlib.sha256(x.encode()).hexdigest()[:16]


def norm(t):
    t = unicodedata.normalize("NFD", t or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", t)


def post(url, data, headers=None):
    req = urllib.request.Request(url, data=json.dumps(data).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **(headers or {})})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()


def notify(topic, title, message, click=SITE, tags=None, prio=3):
    post("https://ntfy.sh/", {"topic": topic, "title": title[:120], "message": message[:900], "click": click,
                              "tags": tags or [], "priority": prio, "icon": SITE + "img/icon-192.png"})


def main():
    secret = os.environ.get("ALERT_SECRET", "").strip()
    if not secret:
        print("Alertes : pas de secret ALERT_SECRET, rien à faire."); return
    try:
        subs = json.loads(post(f"{SB_URL}/rest/v1/rpc/robot_alert_subs", {"p_secret": secret},
                               {"apikey": SB_KEY, "Authorization": f"Bearer {SB_KEY}"}))
    except Exception as e:
        print("Alertes : lecture des réglages impossible :", str(e)[:150]); return
    try: state = json.load(open(f"{ROOT}/alerts_state.json"))
    except Exception: state = {}
    live = json.load(open(f"{ROOT}/news_live.json", encoding="utf-8"))
    try: prices = {a["k"]: a for a in json.load(open(f"{ROOT}/prices.json"))["assets"]}
    except Exception: prices = {}
    items, seen_url = [], set()
    for tab, lst in live.get("tabs", {}).items():
        for it in lst:
            if it["url"] in seen_url: continue
            seen_url.add(it["url"])
            try: age = NOW - datetime.fromisoformat(it["ts"])
            except Exception: continue
            if age <= timedelta(hours=3): items.append(it)
    sent_total = 0
    active = set()
    for sub in subs:
        topic = sub.get("topic") or ""
        if not re.fullmatch(r"[A-Za-z0-9_-]{16,64}", topic): continue
        key = h(topic); active.add(key)
        st = state.setdefault(key, {"sent": [], "px": {}, "new": True})
        sent = set(st.get("sent", []))
        # --- actus
        kws = [k.strip() for k in (sub.get("keywords") or []) if k and len(k.strip()) >= 2][:40]
        pats = [(k, re.compile(r"(?<![a-z0-9])" + re.escape(norm(k)) + r"(?![a-z0-9])")) for k in kws]
        hits = []
        if sub.get("news", True) and pats:
            for it in items:
                ih = h(it["url"])
                if ih in sent: continue
                txt = norm(it["titre"] + " " + it.get("resume", ""))
                k = next((k for k, p in pats if p.search(txt)), None)
                if k: hits.append((k, it, ih))
        # --- cours
        moves = []
        pct = float(sub.get("pct") or 5)
        for k in (sub.get("assets") or [])[:60]:
            a = prices.get(k)
            if not a or a.get("ch") is None or abs(a["ch"]) < pct: continue
            tag = f"{TODAY}:{'+' if a['ch'] > 0 else '-'}"
            if st["px"].get(k) == tag: continue
            moves.append((k, a, tag))
        try:
            if st.get("new"):
                # première fois : on ne renvoie pas les anciennes infos, juste un message de bienvenue
                notify(topic, "✅ Alertes Le Brief activées",
                       "Tu recevras ici les infos qui parlent de ta liste à surveiller et les gros mouvements de tes actifs.", tags=["white_check_mark"])
                sent |= {ih for _, _, ih in hits}
                for k, a, tag in moves: st["px"][k] = tag
                st["new"] = False; sent_total += 1
            else:
                for k, a, tag in moves[:MAX_PER_RUN]:
                    up = a["ch"] > 0
                    p = f"{a['p']:,.2f}".replace(",", " ").replace(".", ",") if a["p"] < 100 else f"{a['p']:,.0f}".replace(",", " ")
                    notify(topic, f"{'📈' if up else '📉'} {a['n']} {'+' if up else '−'}{abs(a['ch']):.1f} % sur 24 h".replace(".", ","),
                           f"{a['n']} ({a['s']}) cote environ {p} €. Ton seuil d'alerte : ±{pct:g} %.",
                           click=SITE + "#espace", tags=["chart_with_upwards_trend" if up else "chart_with_downwards_trend"], prio=4)
                    st["px"][k] = tag; sent_total += 1
                if len(hits) > MAX_PER_RUN:
                    words = sorted({k for k, _, _ in hits})
                    notify(topic, f"🔔 {len(hits)} nouvelles infos sur ta liste",
                           "Mots trouvés : " + ", ".join(words[:8]) + "\n\n" + "\n".join("• " + it["titre"][:110] for _, it, _ in hits[:6]),
                           click=SITE + "#espace", tags=["bell"])
                    sent |= {ih for _, _, ih in hits}; sent_total += 1
                else:
                    for k, it, ih in hits:
                        notify(topic, f"🔔 {k} · {it['source']}", it["titre"] + ("\n\n" + it["resume"][:280] if it.get("resume") else ""),
                               click=it["url"], tags=["bell"])
                        sent.add(ih); sent_total += 1
        except Exception as e:
            print("Alertes : envoi impossible pour un membre :", str(e)[:120])
        st["sent"] = list(sent)[-400:]
        st["px"] = {k: v for k, v in st["px"].items() if v.startswith(TODAY)}
    # on oublie les membres qui ont coupé leurs alertes
    state = {k: v for k, v in state.items() if k in active}
    json.dump(state, open(f"{ROOT}/alerts_state.json", "w"), separators=(",", ":"))
    print(f"Alertes : {len(subs)} membre(s), {sent_total} notification(s) envoyée(s)")


if __name__ == "__main__":
    main()
