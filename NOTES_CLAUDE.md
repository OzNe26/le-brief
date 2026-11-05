# Notes de travail (pour Claude) — Le Brief Invest

Site : https://ozne26.github.io/le-brief/ · dépôt OzNe26/le-brief (branche main, GitHub Pages). Tout le front est dans `index.html`.

## Robots (GitHub Actions, auteur des commits : le-brief-bot)
| Workflow | Fréquence (UTC) | Script | Fichier produit |
|---|---|---|---|
| news.yml — Fil d'actus | boucle ~50 min, toutes les 5 min (relais via cron */15) | update_news.py + alerts.py | news_live.json, alerts_state.json |
| analysis.yml — Analyse + panel de 4 IA | 5:50 et 21:40 | update_analysis.py, avis_ia.py | analysis.json |
| essentiel.yml — L'essentiel par l'IA | 6:10, 10:40, 15:10, 19:40 | update_essentiel.py | dans les données des onglets |
| prices.yml — Cours du portefeuille | :07 et :37 | update_prices.py | prices.json |
| calendar.yml — Calendrier | 5:20, 11:20, 17:20, 21:50 | update_calendar.py | calendar.json |
| audio.yml — Radios + podcasts | toutes les 3 h | update_audio.py (sources : audio_sources.json) | audio.json |
| insiders.yml — Élus US + grands investisseurs | 6:40 et 18:40 | update_insiders.py (Bargo + Dataroma) | insiders.json |
| health.yml — Surveillance | :17 et :47 | health.py (alerte push à l'admin seulement) | health_state.json |

## Secrets GitHub (noms seulement)
GEMINI_API_KEY, MISTRAL_API_KEY, GROQ_API_KEY, ALERT_SECRET (Web Push / VAPID dérivé), BARGO_API_KEY (facultatif, absent). Supabase : seulement URL + clé publishable dans le code.

## IA
- `scripts/gemini.py` : 1er choix **Gemini 3.1 Flash Live** (`gemini-3.1-flash-live-preview`, Live API WebSocket, quota gratuit sans limite de requêtes/min).
  Le modèle ne répond qu'en AUDIO : on lit `outputAudioTranscription` (≈5 s pour 4 000 caractères, JSON valide). Il faut `pip install websockets` dans le workflow.
  Secours : API REST `gemini-flash-latest` puis `gemini-flash-lite-latest`.
- Panel (avis_ia.py) : Gemini (prudent), Mistral ministral-14b (technique), GPT-OSS via Groq (macro), Qwen via Groq (contrarian).
- Le site affiche le nom du modèle (fonction `modelLabel` dans index.html).

## Décisions
- Pas d'actus en anglais, pas d'actus sport (is_french, is_sport dans update_news.py).
- Pas de tâche planifiée Claude. Pas de connexion Google directe (GIS) : flux OAuth Supabase classique.
- Mode clair : fond blanc (#fff), bouton ☀️/🌙, suit l'appareil par défaut. Logo orange fixe ; « Invest » orange sur l'accueil.
- Bandeau TradingView en mode "regular" (une ligne) sur toutes les tailles d'écran ; plus de graphiques latéraux.
- Alertes panne réservées à l'admin (ADMIN_IDS dans index.html et health.py).

## Problèmes connus
- SEC EDGAR bloque les IP de GitHub Actions (403) → Dataroma pour les 13F. Burry, Druckenmiller, Cathie Wood absents.
- DefiLlama (déblocages de tokens) payant (402).
- Bankless (podcast anglais) : demandé à Enzo s'il faut le retirer, pas de réponse.
