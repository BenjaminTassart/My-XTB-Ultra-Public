# My XTB Ultra : plan d’action et outils

Guide pratique : **quoi faire, dans quel ordre, avec quel outil.** Coche les cases au fur et à mesure.

> Les offres gratuites (quotas, couverture, conditions) changent souvent. Tout ce qui est marqué **(à vérifier)** doit être contrôlé sur le site de l’outil au moment de s’inscrire.

---

## 1. Le projet en 10 lignes

- **Usage :** outil perso, un seul utilisateur, pas de comptes. Suivi et analyse uniquement (pas d’ordres).
- **Support :** application web installable (PWA), utilisable sur téléphone et PC.
- **Budget :** zéro euro.
- **Écrans :** Accueil (favoris + actus), Recherche (secteur, filtres prêts à l’emploi, 50 résultats par page), Fiche action, Portefeuille virtuel, Paramètres.
- **Données :** monde entier, prix différés de 15 min, affichage en euro avec conversion en dollar.
- **Résultats d’entreprises :** chiffres et évolution, comparaison au consensus, résumé IA généré uniquement au clic.
- **Design :** noir et ébène, liseré blanc fin sur l’élément sélectionné, barre en bas sur téléphone et à gauche sur PC.
- **Quota :** message clair quand la limite de l’API gratuite est atteinte.
- **Ordre de construction :** accueil + fiche action + favoris d’abord, le reste ensuite.

---

## 2. Boîte à outils

| Besoin | Outil proposé | Coût | Pourquoi |
|---|---|---|---|
| Écrire le code | **Claude Code** (ou Claude dans le chat) | selon ton abonnement | Tu as dit que tout le code serait fait par IA |
| Stocker le code | **GitHub** | gratuit | Render se branche dessus et redéploie à chaque mise à jour |
| Interface (front) | **React + Vite**, hébergée comme « Static Site » sur **Render** | gratuit | Un seul code pour téléphone et PC, installable en PWA |
| Serveur (back) | **Python + FastAPI**, hébergé comme « Web Service » sur **Render** | gratuit (mise en veille acceptée) | Garde les clés d’API secrètes, gère le cache et le quota |
| Base de données | **Supabase** ou **Neon** (PostgreSQL) | gratuit **(à vérifier)** | Les bases gratuites de Render sont limitées dans le temps, un service externe est plus sûr |
| Données financières | Une API officielle gratuite : **Financial Modeling Prep**, **Finnhub**, **Twelve Data**, **Alpha Vantage** ou **EODHD** | gratuit à quota limité **(à vérifier)** | À comparer à l’étape 0 |
| Résumés IA | Une API d’IA avec offre gratuite, par exemple **Google Gemini API** | gratuit **(à vérifier)** | Utilisée seulement au clic, avec cache |
| Tâches planifiées | **GitHub Actions** (tâches programmées) ou **cron-job.org** | gratuit | Précalcul nocturne, vérification des alertes, réveil du serveur |
| Notifications | **Web Push** (bibliothèque Python `pywebpush`) | gratuit | Fonctionne dans une PWA |
| Graphiques | **Lightweight Charts** (TradingView) ou **Recharts** | gratuit | Chandeliers et courbes |
| Logos d’entreprises | Souvent fournis par l’API de données, sinon un service de logos gratuit | à définir **(à vérifier)** | Pour la liste ligne par ligne |

---

## 3. Étape 0 : Préparer le terrain et tester les données

**Objectif :** savoir ce que les API gratuites peuvent vraiment fournir avant d’écrire l’interface. C’est l’étape qui décide de la faisabilité du « monde entier ».

**À faire**
- [ ] Créer un compte **GitHub** et un dépôt vide `my-xtb-ultra`.
- [ ] Créer un compte **Render** (connexion avec GitHub).
- [ ] Créer un compte **Supabase** (ou Neon) et un projet vide.
- [ ] Ouvrir un compte gratuit chez 2 ou 3 fournisseurs de données et récupérer les clés d’API.
- [ ] Pour chaque fournisseur, tester avec un petit script (demande-le à l’IA) :
  - prix d’une action américaine, européenne (Paris) et asiatique ;
  - PER, PEG, capitalisation, dividende, marge, dette/EBITDA, ROE ;
  - résultats trimestriels et annuels ;
  - consensus des analystes (beat / miss) ;
  - liste d’entreprises par secteur et pays ;
  - logo et actualités ;
  - nombre d’appels autorisés par jour ou par minute.
- [ ] Remplir un tableau de comparaison : ce qui est inclus gratuitement et ce qui est payant.
- [ ] Décider du ou des fournisseurs retenus et noter ce qu’on abandonne (par exemple : couverture mondiale limitée, consensus indisponible).

**Outils :** Claude (pour écrire les scripts de test), un terminal ou un notebook Python.

**C’est fini quand :** tu as un tableau clair « fonctionnalité → fournisseur → gratuit oui/non » et un choix validé.

---

## 4. Étape 1 : Version minimale (accueil + fiche action + favoris)

**Objectif :** une application déployée en ligne que tu ouvres sur ton téléphone et ton PC, avec les bases.

**À faire**
- [ ] Demander à l’IA de créer la structure du projet : dossier `frontend` (React + Vite) et dossier `backend` (FastAPI).
- [ ] Mettre en place le **design** : fond noir, ébène, liseré blanc fin sur l’élément sélectionné.
- [ ] Construire la **barre de navigation** : en bas sur téléphone, à gauche sur PC (Accueil, Recherche, Portefeuille, Paramètres).
- [ ] Créer la **fiche action** : prix, indicateurs essentiels (PER, PEG, P/B, dividende, capitalisation, marge nette, dette/EBITDA, ROE).
- [ ] Créer les **favoris** (ajout et retrait d’une action) stockés dans la base de données.
- [ ] Créer la **page d’accueil** : liste des favoris avec leur prix, et section actualités.
- [ ] Créer le **cache** dans la base : chaque donnée récupérée est gardée un certain temps avant d’être redemandée.
- [ ] Créer le **compteur de quota** et le message « Limite atteinte » côté interface.
- [ ] Ajouter un **code d’accès** simple (sans comptes) pour protéger l’application.
- [ ] Rendre l’application **installable** (PWA : manifeste et icône).
- [ ] **Déployer** : back et front sur Render, variables secrètes (clés d’API, connexion à la base) saisies dans Render, jamais dans le code.

**Outils :** Claude Code, React + Vite, FastAPI, Supabase/Neon, Render, GitHub.

**C’est fini quand :** tu ouvres l’adresse sur ton téléphone, tu ajoutes Apple ou LVMH en favori, tu les retrouves sur l’accueil sur ton PC, et le message de quota s’affiche si tu simules une limite atteinte.

---

## 5. Étape 2 : Graphiques et devises

**À faire**
- [ ] Ajouter sur la fiche action : courbe de prix et chandeliers (périodes 1J, 1M, 1A, 5A).
- [ ] Ajouter en options à cocher : moyennes mobiles et RSI.
- [ ] Afficher les prix en **euro** par défaut, avec un bouton pour basculer en **dollar** (taux de change mis en cache).

**Outils :** Lightweight Charts ou Recharts, API de données pour l’historique et les taux de change.

**C’est fini quand :** tu changes de période, actives le RSI, et passes de l’euro au dollar sans erreur.

---

## 6. Étape 3 : Portefeuille virtuel

**À faire**
- [ ] Créer la page Portefeuille : ajouter une position (action, quantité, prix d’entrée), la modifier, la supprimer.
- [ ] Afficher la **valeur totale** du portefeuille (en euro, avec option dollar).
- [ ] Créer les **alertes de prix** (seuil haut ou bas par action).
- [ ] Mettre en place la **vérification des alertes** par une tâche planifiée (le serveur gratuit s’endort, donc une tâche externe est nécessaire).
- [ ] Envoyer les **notifications push** (sur iPhone, la PWA doit être installée sur l’écran d’accueil).
- [ ] Option : afficher la performance depuis l’achat (bonus).

**Outils :** Supabase/Neon, GitHub Actions ou cron-job.org, `pywebpush`.

**C’est fini quand :** tu reçois une notification sur ton téléphone quand un seuil est franchi.

---

## 7. Étape 4 : Analyse des résultats

**À faire**
- [ ] Afficher les chiffres trimestriels et annuels (chiffre d’affaires, bénéfice) avec leur évolution.
- [ ] Afficher la comparaison au **consensus** (beat / miss) si l’API retenue le fournit.
- [ ] Ajouter le bouton **« Générer le résumé IA »** : au clic, l’IA compare la dernière publication à la précédente et indique **ce qui change et ce qui ne change pas** dans la vision de l’entreprise.
- [ ] **Mettre le résumé en cache** pour ne jamais le regénérer deux fois pour la même publication.
- [ ] Gérer le cas « quota IA atteint » avec un message clair.

**Outils :** API de données (résultats, consensus), API d’IA gratuite, base de données pour le cache.

**C’est fini quand :** un clic produit un résumé lisible, et un second clic sur la même publication l’affiche instantanément sans nouvel appel.

---

## 8. Étape 5 : Recherche et filtres prêts à l’emploi

**À faire**
- [ ] Créer l’écran de choix du **secteur**, puis la liste ligne par ligne (logo + nom).
- [ ] Définir les **filtres prêts à l’emploi** (value, croissance, dividendes), combinés avec la **zone géographique** et le **secteur**, à partir des indicateurs retenus.
- [ ] Trier par **capitalisation**, afficher **50 résultats** (moins si le chargement dépasse 10 secondes), et charger les **50 suivants** quand on arrive en bas de la liste.
- [ ] Mettre en place un **précalcul nocturne** : une tâche planifiée récupère et stocke les ratios d’une liste d’entreprises pour que la recherche ne consomme presque aucun appel d’API en direct.

**Outils :** GitHub Actions ou cron-job.org, base de données, API de données.

**C’est fini quand :** un filtre s’affiche en moins de 10 secondes et la liste continue en défilant.

---

## 9. Étape 6 : Paramètres et finitions

**À faire**
- [ ] Paramètres : thème, notifications, gestion des données (exporter ou effacer favoris et portefeuille).
- [ ] Vérifier la compatibilité sur ton téléphone et ton PC.
- [ ] Ajuster le design (espacements, animations, liseré).
- [ ] Faire une sauvegarde de la base de données.

**C’est fini quand :** tu utilises l’app au quotidien sans accroc.

---

## 10. Points de vigilance

1. **Couverture mondiale gratuite :** les API gratuites sont souvent limitées aux États-Unis ou à quelques marchés. L’étape 0 sert à le savoir avant de construire. Si besoin, on réduit l’ambition (par exemple États-Unis + Europe).
2. **Quota :** tout passe par le serveur et le cache. Ne jamais appeler l’API directement depuis l’interface.
3. **Clés secrètes :** ne jamais les écrire dans le code ni les publier sur GitHub. Elles se saisissent dans les variables d’environnement de Render.
4. **Mise en veille du serveur :** le premier chargement peut prendre quelques dizaines de secondes. Les tâches planifiées peuvent aussi réveiller le serveur.
5. **Portefeuille sans comptes :** le code d’accès protège l’adresse publique. Ne le partage pas.
6. **Responsabilité :** l’application informe mais ne remplace pas un conseil financier.

---

## 11. Comment travailler avec l’IA

- Avance **étape par étape** : une étape terminée et testée avant de passer à la suivante.
- Donne à l’IA ce document au début de chaque session, avec la mention de l’étape en cours.
- À chaque demande, précise : **ce que tu veux, sur quel écran, et comment tu testeras que ça marche.**
- Fais commiter le code sur GitHub après chaque étape réussie, pour pouvoir revenir en arrière.
- Quand une erreur apparaît, copie le message complet et donne-le à l’IA.

---

## 12. Prochaine action

**Commencer l’étape 0 :** créer les comptes (GitHub, Render, Supabase) et tester les API de données. Je peux t’aider à chercher les offres gratuites actuelles et à écrire les scripts de test.
