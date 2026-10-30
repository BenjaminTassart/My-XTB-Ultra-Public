# My XTB Ultra : étapes 1 à 6

Application web installable (PWA) pour suivre des actions : **accueil** (favoris + actus), **fiche action**
(prix + indicateurs + graphique), **favoris**, navigation (barre en bas sur téléphone, à gauche sur PC), cache,
compteur de quota, code d'accès. Le portefeuille et les alertes sont disponibles ; les filtres de recherche sont disponibles en phase 5.

## Étape 3 : portefeuille et alertes

Positions modifiables, valorisation EUR/USD, alertes haut/bas et notifications Web Push.
Suivre [le guide de configuration et de validation](ETAPE_3.md) pour activer les notifications et la vérification automatique. Sans configuration, le portefeuille et les vérifications manuelles restent utilisables.

## Nouveautés de l'étape 2 (à mettre en ligne par-dessus l'étape 1)

- **Graphique** sur chaque fiche : courbe ou chandeliers, périodes 1M, 3M, 6M, 1A, 5A, survol (ou doigt) pour lire
  la date et les prix, moyennes mobiles 50 / 200 jours et RSI 14 en options à cocher. Les indicateurs sont calculés
  dans le navigateur : ils ne consomment aucun appel d'API. Une seule requête d'historique par titre toutes les 12 h.
- **Devise** : affichage en **euro par défaut**, bouton € / $ sur l'accueil et sur la fiche (choix retenu sur
  l'appareil). Taux de la Banque centrale européenne via Frankfurter (gratuit, sans clé, aucun quota à surveiller).
  Les prix, variations, plus hauts/bas et capitalisation sont convertis au taux du jour.
- **Corrections** : les actus ne montrent plus que des articles récents (7 jours, ou 2 jours sans favori) ; la devise
  des titres hors États-Unis est déduite du suffixe (`.PA` = euro…) pour ne plus afficher un « $ » par erreur.
- Aucune nouvelle variable d'environnement ni nouvelle dépendance : il suffit de remplacer les fichiers et de pousser
  sur GitHub, Render redéploie tout seul.
- Limites : pas d'intraday en gratuit (cours journaliers seulement) ; pas d'historique pour les bourses hors
  États-Unis ; sur 5 ans, une bougie par semaine.

```
my-xtb-ultra/
├─ backend/    serveur Python (FastAPI) : API, cache, quota, base de données
├─ frontend/   interface React (Vite) : écrans, design noir/ébène
├─ Dockerfile  construit l'interface puis lance le serveur (un seul service Render)
└─ render.yaml description du service Render
```

## 1. Ce qu'il faut savoir avant de commencer (résultats de l'étape 0)

- **Titres américains** (AAPL, MSFT…) : prix, profil, logo et indicateurs complets via Financial Modeling Prep.
- **Autres bourses** : l'offre gratuite FMP ne les couvre pas. Pour les suffixes `.PA`, `.L`, `.DE`, `.TO`, l'app
  affiche **le prix seul** via Alpha Vantage (25 appels par jour). Les autres bourses affichent un message clair.
- **Coût en appels FMP** : un nouveau titre consomme 4 appels (prix, profil, 2 jeux d'indicateurs), puis tout vient
  du cache (prix 15 min, indicateurs 24 h, profil 7 jours). Compte ~60 nouveaux titres par jour au maximum.
- Les **actualités** viennent des flux RSS de Google Actualités (gratuit, sans clé, non officiel).

## 2. Lancer en local (pour tester)

Il faut Python 3.11+ et Node 20+.

```bash
cp .env.example .env            # puis remplis FMP_API_KEY (et ALPHAVANTAGE_API_KEY)
# Terminal 1 : serveur
cd backend
pip install -r requirements.txt
export $(grep -v '^#' ../.env | xargs)      # sous Windows PowerShell : définis les variables à la main
python -m uvicorn app.main:app --reload --port 8000
# Terminal 2 : interface
cd frontend
npm install
npm run dev                     # ouvre http://localhost:5173
```

Sans `DATABASE_URL`, une base SQLite locale (`local.db`) est utilisée. Sans `ACCESS_CODE`, pas de code demandé.
Tests du serveur : `pip install -r requirements-dev.txt && python -m pytest tests`.

## 3. Préparer Supabase

1. Dans ton projet Supabase, clique sur **Connect** et copie la chaîne **Session pooler** (pas « Direct
   connection » : elle est en IPv6 et Render ne la joint pas toujours).
2. Remplace `[YOUR-PASSWORD]` par le mot de passe de ta base. Cette chaîne sera la valeur de `DATABASE_URL`.
3. Les tables (`favorites`, `cache`, `usage`) se créent toutes seules au premier démarrage.

## 4. Déployer sur Render

1. Crée un dépôt GitHub et envoie-y ce dossier (`.env` est exclu par le `.gitignore`).
2. Sur Render : **New > Blueprint**, choisis le dépôt (Render lit `render.yaml`). Sinon : **New > Web Service**,
   environnement **Docker**, offre **Free**, *Health Check Path* `/api/health`.
3. Dans **Environment**, renseigne : `DATABASE_URL`, `FMP_API_KEY`, `ALPHAVANTAGE_API_KEY`, `ACCESS_CODE`
   (choisis un code que tu retiendras ; il protège tes données).
4. Lance le déploiement (quelques minutes). Ton adresse sera `https://my-xtb-ultra.onrender.com` (ou proche).

Après quelques minutes d'inactivité, le serveur gratuit s'endort : la première ouverture peut prendre jusqu'à
une minute. L'écran « Le serveur ne répond pas » propose alors de réessayer.

## 5. Installer sur le téléphone

- **Android (Chrome)** : menu ⋮ > *Installer l'application*.
- **iPhone (Safari)** : bouton Partager > *Sur l'écran d'accueil*.

## 6. Vérifier que tout marche (critère de fin de l'étape 1)

1. Ouvre l'adresse, saisis ton code d'accès.
2. Onglet **Recherche** : ouvre `AAPL`, vérifie le prix et les indicateurs, appuie sur l'étoile.
3. Onglet **Accueil** : Apple apparaît dans les favoris ; ouvre la même adresse sur ton PC : mêmes favoris.
4. Onglet **Paramètres** : le compteur d'appels FMP a augmenté.
5. Essaie `MC.PA` : le prix s'affiche avec un message indiquant que le reste n'est pas gratuit.

## 7. Points à vérifier à la première utilisation réelle

Le code a été testé avec de fausses réponses d'API, pas avec tes vraies clés :

- **Noms des champs FMP** : si un indicateur affiche « — » (le PEG par exemple), dis-le-moi avec le titre testé ;
  on ajustera la liste des noms dans `backend/app/providers.py` (`INDICATORS`).
- **Suffixes Alpha Vantage** : `.PA → .PAR` est confirmé par ton test ; `.L`, `.DE`, `.TO` sont à confirmer.
- **Quota** : limites réglables avec `FMP_DAILY_LIMIT` et `ALPHAVANTAGE_DAILY_LIMIT` si ton offre change.

## Validation avant le portefeuille

Suivre [la fiche de validation](VALIDATION_ETAPE_2.md) sur le site en ligne.
Reprise du 27 octobre 2026 : les 11 tests serveur simulés et la compilation de l’interface réussissent. La validation avec les vraies clés reste à faire.

### Correctif quota

Le compteur distingue désormais le nombre local d’appels d’un refus signalé par le fournisseur. Les Paramètres affichent la prochaine remise à zéro locale et un bouton d’actualisation. Les anciens compteurs ne sont pas effacés : leur valeur reste ambiguë jusqu’au changement de journée UTC. Cette correction ne rétablit pas le quota chez Alpha Vantage. Validation : 20 tests simulés réussis et compilation de l’interface réussie.


## Étape 4 : résultats et résumé IA

Dans la fiche action : résultats trimestriels/annuels, évolutions, consensus et résumé Gemini au clic conservé sans expiration. Suivre [le guide étape 4](ETAPE_4.md) pour ajouter GEMINI_API_KEY dans Render et vérifier la version en ligne.


Correctif diagnostic Alpha Vantage : distinction des pauses courtes et des limites quotidiennes, affichage des nouveaux refus avec clés masquées. 32 tests simulés et compilation réussis. Le refus réel du compte reste à identifier ; aucun rétablissement de quota n’est garanti.


## Phase 5 : recherche et filtres

Recherche par secteur, zone du siège et filtres prédéfinis sur une sélection de 55 titres cotés aux États-Unis. Chargement progressif, liste locale triée par capitalisation et pagination de 50 titres. Voir [le guide phase 5](ETAPE_5.md) pour charger le premier lot et activer la planification optionnelle.


## Phase 6 : paramètres et sauvegarde

Thèmes sombre/clair/système, notifications par appareil, export personnel JSON et suppression explicitement confirmée. Scripts de sauvegarde complète et de restauration vers une base vide. Voir [le guide phase 6](ETAPE_6.md). Les vérifications visuelles et la sauvegarde de production restent à effectuer.
