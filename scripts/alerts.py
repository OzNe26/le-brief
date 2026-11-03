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


VAPID = None
try:
    import vapid as _v
    from pywebpush import webpush, WebPushException
    from py_vapid import Vapid
except Exception:
    _v = None


def rpc(name, payload):
    return json.loads(post(f"{SB_URL}/rest/v1/rpc/{name}", payload, {"apikey": SB_KEY, "Authorization": f"Bearer {SB_KEY}"}) or b"null")


class Sender:
    """Envoie une alerte sur tous les appareils d'un membre (notifications du site) et sur ntfy s'il l'utilise."""
    def __init__(self, sub, secret):
        self.topic = sub.get("topic") if re.fullmatch(r"[A-Za-z0-9_-]{16,64}", sub.get("topic") or "") else None
        self.endpoints = [e for e in (sub.get("endpoints") or []) if isinstance(e, dict) and (e.get("endpoint") or "").startswith("https://")]
        self.secret = secret
        self.count = 0

    def ok(self): return bool(self.topic or self.endpoints)

    def __call__(self, title, message, click=SITE, tags=None, prio=3):
        global VAPID
        if self.topic:
            try:
                post("https://ntfy.sh/", {"topic": self.topic, "title": title[:120], "message": message[:900], "click": click,
                                          "tags": tags or [], "priority": prio, "icon": SITE + "img/icon-192.png"})
            except Exception as e: print("ntfy :", str(e)[:100])
        if self.endpoints and _v:
            if VAPID is None:
                VAPID = Vapid(private_key=_v.private_key(self.secret))
            data = json.dumps({"title": title[:120], "body": message[:600], "url": click, "tag": (tags or ["lebrief"])[0]}, ensure_ascii=False)
            for e in list(self.endpoints):
                try:
                    webpush({"endpoint": e["endpoint"], "keys": {"p256dh": e["p256dh"], "auth": e["auth"]}}, data,
                            vapid_private_key=VAPID, vapid_claims={"sub": "https://ozne26.github.io"}, ttl=6 * 3600, timeout=15)
                except WebPushException as ex:
                    code = getattr(getattr(ex, "response", None), "status_code", 0)
                    if code in (404, 410):  # appareil désabonné : on le retire
                        try: rpc("robot_remove_push", {"p_secret": self.secret, "p_endpoint": e["endpoint"]})
                        except Exception: pass
                        self.endpoints.remove(e)
                    else: print("push :", code, str(ex)[:100])
                except Exception as ex: print("push :", str(ex)[:100])
        self.count += 1


def main():
    secret = os.environ.get("ALERT_SECRET", "").strip()
    if not secret:
        print("Alertes : pas de secret ALERT_SECRET, rien à faire."); return
    try:
        subs = rpc("robot_alert_targets", {"p_secret": secret})
    except Exception:
        try: subs = rpc("robot_alert_subs", {"p_secret": secret})  # ancienne version (ntfy seul)
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
    try: ins = json.load(open(f"{ROOT}/insiders.json", encoding="utf-8"))
    except Exception: ins = {}
    lim = (NOW - timedelta(days=4)).date().isoformat()
    ins_trades = [t for t in (ins.get("congress") or {}).get("trades", []) if (t.get("ddate") or "") >= lim]
    ins_funds = [i for i in ins.get("investors", []) if i.get("date")]
    sent_total = 0
    active = set()
    for sub in subs:
        notify = Sender(sub, secret)
        if not notify.ok() or not sub.get("user_id"): continue
        key = h("u:" + sub["user_id"]); active.add(key)
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
        # --- élus et grands investisseurs (option « ins:trades »)
        ins_hits = []
        if "ins:trades" in (sub.get("assets") or []):
            mine = {k[2:].upper() for k in (sub.get("assets") or []) if k.startswith("s:")}
            seen_ins = set(st.get("ins") or [])
            first = "ins" not in st
            for t in ins_trades:
                if not (t.get("famous") or (t.get("ticker") or "") in mine): continue
                ih = h("t:%s|%s|%s|%s|%s" % (t.get("slug"), t.get("ticker"), t.get("tdate"), t.get("type"), t.get("amount")))
                if ih not in seen_ins: ins_hits.append(("t", t, ih))
            for f in ins_funds:
                ih = h("f:%s|%s" % (f["code"], f["date"]))
                if ih not in seen_ins: ins_hits.append(("f", f, ih))
            if first:  # on n'envoie pas l'historique quand on vient d'activer l'option
                seen_ins |= {ih for _, _, ih in ins_hits}; ins_hits = []
            st["ins"] = list(seen_ins)[-600:]
        try:
            if ins_hits and not st.get("new"):
                seen_ins = set(st["ins"])
                trades = [x for x in ins_hits if x[0] == "t"]
                if len(trades) > 3:
                    notify(f"🏛 {len(trades)} nouveaux trades d'élus déclarés",
                           "\n".join(f"• {t['who']} : {t['type']} {t['ticker'] or t['asset'][:30]} ({t.get('amount') or '?'})" for _, t, _ in trades[:6]),
                           click=SITE + "#elus", tags=["classical_building"])
                else:
                    for _, t, _ in trades:
                        notify(f"🏛 {t['who']} : {t['type']} {t['ticker'] or ''}".strip(),
                               f"{t['asset'][:80]}\nMontant déclaré : {t.get('amount') or '?'} · trade du {t.get('tdate')}, déclaré le {t.get('ddate')}.",
                               click=SITE + "#elus", tags=["classical_building"])
                funds = [x for x in ins_hits if x[0] == "f"][:3]
                for _, f, _ in funds:
                    mv = ", ".join(f"{m['t']} ({m['act']})" for m in (f.get("moves") or [])[:4])
                    notify(f"💼 {f['name']} a publié son portefeuille",
                           f"{f['fund']}, positions au {f['date']}." + (f" Mouvements : {mv}." if mv else ""),
                           click=SITE + "#elus", tags=["briefcase"])
                st["ins"] = list(seen_ins | {ih for _, _, ih in trades + funds})[-600:]
            if st.get("new"):
                # première fois : on ne renvoie pas les anciennes infos, juste un message de bienvenue
                notify("✅ Alertes Le Brief activées",
                       "Tu recevras ici les infos qui parlent de ta liste à surveiller et les gros mouvements de tes actifs.", tags=["white_check_mark"])
                sent |= {ih for _, _, ih in hits}
                for k, a, tag in moves: st["px"][k] = tag
                st["new"] = False
            else:
                for k, a, tag in moves[:MAX_PER_RUN]:
                    up = a["ch"] > 0
                    p = f"{a['p']:,.2f}".replace(",", " ").replace(".", ",") if a["p"] < 100 else f"{a['p']:,.0f}".replace(",", " ")
                    notify(f"{'📈' if up else '📉'} {a['n']} {'+' if up else '−'}{abs(a['ch']):.1f} % sur 24 h".replace(".", ","),
                           f"{a['n']} ({a['s']}) cote environ {p} €. Ton seuil d'alerte : ±{pct:g} %.",
                           click=SITE + "#espace", tags=["chart_with_upwards_trend" if up else "chart_with_downwards_trend"], prio=4)
                    st["px"][k] = tag
                if len(hits) > MAX_PER_RUN:
                    words = sorted({k for k, _, _ in hits})
                    notify(f"🔔 {len(hits)} nouvelles infos sur ta liste",
                           "Mots trouvés : " + ", ".join(words[:8]) + "\n\n" + "\n".join("• " + it["titre"][:110] for _, it, _ in hits[:6]),
                           click=SITE + "#espace", tags=["bell"])
                    sent |= {ih for _, _, ih in hits}
                else:
                    for k, it, ih in hits:
                        notify(f"🔔 {k} · {it['source']}", it["titre"] + ("\n\n" + it["resume"][:280] if it.get("resume") else ""),
                               click=it["url"], tags=["bell"])
                        sent.add(ih)
        except Exception as e:
            print("Alertes : envoi impossible pour un membre :", str(e)[:120])
        sent_total += notify.count
        st["sent"] = list(sent)[-400:]
        st["px"] = {k: v for k, v in st["px"].items() if v.startswith(TODAY)}
    # on oublie les membres qui ont coupé leurs alertes
    state = {k: v for k, v in state.items() if k in active}
    json.dump(state, open(f"{ROOT}/alerts_state.json", "w"), separators=(",", ":"))
    print(f"Alertes : {len(subs)} membre(s), {sent_total} notification(s) envoyée(s)")


if __name__ == "__main__":
    main()
