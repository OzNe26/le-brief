#!/usr/bin/env python3
"""Surveillance des robots : si une partie du site ne se met plus à jour, une notification part vers les membres qui
l'ont demandé (case « Prévenir si le site ne se met plus à jour » dans Mon espace). Une seule alerte par panne,
un rappel toutes les 6 h si ça dure, et un message quand c'est réparé."""
import json, os, sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, __file__.rsplit("/", 1)[0])
import alerts

ROOT = __file__.rsplit("/scripts/", 1)[0]
NOW = datetime.now(timezone.utc)
SITE = alerts.SITE
ADMIN_IDS = {"4e08bbf0-78fc-4dd5-984c-2144202bbae0"}  # seul l'admin du site reçoit les alertes de panne
# (fichier, nom affiché, retard toléré en heures, robot GitHub)
CHECKS = [
    ("news_live.json", "Le fil d'actus en direct", 0.75, "Fil d'actus en direct"),
    ("prices.json", "Les cours du portefeuille", 3, "Cours pour le portefeuille"),
    ("data.json", "L'essentiel (résumés IA)", 13, "L'essentiel (résumés par l'IA)"),
    ("analysis.json", "L'analyse des marchés", 18, "Analyse quotidienne des marchés"),
    ("calendar.json", "Le calendrier des marchés", 15, "Calendrier des marchés"),
    ("audio.json", "Les podcasts", 7, "Mise à jour audio (radios + podcasts)"),
]


def updated(path):
    d = json.load(open(f"{ROOT}/{path}", encoding="utf-8"))
    if "updatedAt" in d: return datetime.fromisoformat(d["updatedAt"])
    ts = [datetime.fromisoformat(v["updatedAt"]) for v in d.values() if isinstance(v, dict) and v.get("updatedAt")]
    return max(ts) if ts else None


def ago(td):
    m = int(td.total_seconds() // 60)
    return f"{m} min" if m < 120 else f"{m // 60} h"


def main():
    try: state = json.load(open(f"{ROOT}/health_state.json"))
    except Exception: state = {}
    down, fixed = [], []
    for f, name, hours, robot in CHECKS:
        try: t = updated(f)
        except Exception: t = None
        late = (NOW - t) if t else timedelta(days=99)
        bad = late > timedelta(hours=hours)
        st = state.get(f, {})
        if bad:
            last = datetime.fromisoformat(st["alerted"]) if st.get("alerted") else None
            if not last or NOW - last > timedelta(hours=6):
                down.append((f, name, late, robot)); state[f] = {"alerted": NOW.isoformat(timespec="seconds"), "down": True}
            print(f"EN RETARD : {name} (dernière mise à jour il y a {ago(late)})")
        else:
            if st.get("down"): fixed.append(name)
            state[f] = {}
            print(f"ok : {name} (il y a {ago(late)})")
    if down or fixed:
        secret = os.environ.get("ALERT_SECRET", "").strip()
        subs = []
        if secret:
            try: subs = [s for s in alerts.rpc("robot_alert_targets", {"p_secret": secret}) if "sys:health" in (s.get("assets") or []) and s.get("user_id") in ADMIN_IDS]
            except Exception as e: print("Lecture des abonnés impossible :", str(e)[:120])
        for s in subs:
            send = alerts.Sender(s, secret)
            if not send.ok(): continue
            if down:
                lines = [f"• {n} : pas de mise à jour depuis {ago(l)} (robot « {r} »)" for _, n, l, r in down]
                send("⚠️ Le Brief : un robot ne met plus le site à jour", "\n".join(lines) + "\n\nVa voir l'onglet Actions de ton dépôt GitHub, ou demande à Claude.",
                     click="https://github.com/OzNe26/le-brief/actions", tags=["warning"], prio=4)
            if fixed:
                send("✅ Le Brief : c'est réparé", "De nouveau à jour : " + ", ".join(fixed) + ".", click=SITE, tags=["white_check_mark"])
        print(f"{len(down)} panne(s), {len(fixed)} réparation(s), {len(subs)} personne(s) prévenue(s)")
    json.dump(state, open(f"{ROOT}/health_state.json", "w"), indent=0)


if __name__ == "__main__":
    main()
