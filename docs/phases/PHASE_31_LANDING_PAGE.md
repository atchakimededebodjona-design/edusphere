# Phase 31 — Page d'accueil : contact réel, tarifs, partenaires

- **Demande** : 2026-11-16, « il faut refaire la landing page ».
- **Branche** : `feat/landing-page`, partie de `main` (`465de4e`).
- **Migration** : aucune.

## 1. Décisions (2026-11-16)

| Sujet | Décision |
|---|---|
| Problème | Le design convient ; il manque l'information. Les boutons « Demander une démonstration » ne menaient nulle part. Deux fonctionnalités étaient marquées « à venir », et la page ne montrait ni prix ni programme partenaire. |
| Action principale | **WhatsApp**, avec un message prérempli, et un bouton d'appel. Un seul numéro public, pour les deux : celui choisi par l'exploitant (`lib/landing/contact.ts`). Aucun formulaire. |
| Tarifs | « À partir de » pour 3, 6 et 12 mois, avec l'économie par rapport au trimestre, et un **simulateur** selon l'effectif. Les montants viennent de la **grille active** et restent à jour sans retoucher la page. |
| Sections ajoutées | **Premier trimestre offert** et **Devenir partenaire** (20 % de chaque abonnement payé). |

## 2. Ce qui change

**API.** Nouvelle route publique `GET /api/v1/public/subscription-pricing`, sans authentification et en lecture seule. Elle renvoie :
- la devise ;
- les bornes des tranches et le palier de 250 élèves ;
- les montants de la grille active, au même format que l'écran plateforme (`GridPeriodPrices`).

Elle ne renvoie ni identifiant, ni libellé de grille, ni aucune donnée d'école. Sans grille active, `periods` est vide. La lecture s'appuie sur la politique RLS `read_all` des grilles (migration 0027). La route est limitée à 120 appels par minute et par adresse (`PUBLIC_PRICING_RATE_LIMIT_*`), et sa réponse se met en cache 5 minutes (`Cache-Control`).

**Page d'accueil.**
- Les tarifs sont lus **côté serveur**, avec un délai maximal de 4 s, et la page est régénérée au plus toutes les 5 minutes. Le navigateur n'appelle jamais l'API. Si elle est indisponible, ou s'il n'y a pas de grille active, la section affiche « Tarifs sur demande ».
- Le simulateur (`lib/landing/pricing.mjs`) applique les règles de l'API (`pricing.supplement_for`) : forfait de base jusqu'à 100 élèves, supplément par tranche, palier de 250 élèves au-delà de 1 000, « sur devis » si la grille ne chiffre pas l'effectif.
- **En-tête** : badge « Premier trimestre offert », texte concret, boutons « Écrire sur WhatsApp » et « Voir les tarifs », numéro d'appel.
- **Navigation** : Fonctionnalités, Tarifs, Partenaires, Contact, et le bouton WhatsApp.
- **Fonctionnalités** : seize modules en service, chacun avec une phrase concrète ; plus aucune mention « à venir ».
- **Nouvelles sections** : « Tarifs » (premier trimestre offert, prix, simulateur, paiement par Flooz ou T-Money) et « Devenir partenaire ».
- **Contact et pied de page** : WhatsApp et appel.

## 3. Tests

- `tests/test_public_pricing.py` :
  - montants exacts de la grille activée, bornes des tranches, aucune autre donnée, accès sans authentification ;
  - limite de débit (429), qui nécessite Redis.
- Test de garde `test_only_expected_subscription_and_commission_objects_exist` : la nouvelle route y est ajoutée.
- `lib/landing/pricing.test.mjs` (`pnpm test:config`) : bornes des tranches, paliers au-delà de 1 000 élèves, devis, entrées invalides, économie, format des montants.
- Vérification visuelle sur ordinateur (1366 px) et sur téléphone (390 px, sans débordement horizontal), avec une API de démonstration servant la grille HT du 2026-11-15. Pour 1 300 élèves, le simulateur affiche 150 000 / 285 000 / 540 000 FCFA.
- `next build` : la page `/` est générée avec une régénération toutes les 300 s ; sans API, elle affiche « Tarifs sur demande ».

## 4. Mise en service

Sans migration. L'API et le web redémarrent, quelques secondes. Depuis `/opt/edusphere` :

```sh
git fetch https://github.com/atchakimededebodjona-design/edusphere.git main:refs/remotes/origin/main
git merge --ff-only origin/main
docker tag edusphere-api:latest edusphere-api:avant-landing
docker tag edusphere-web:latest edusphere-web:avant-landing
docker compose build api web > /tmp/build-landing.log 2>&1; echo "construction : code $?"
docker compose up -d api web
```

Vérifications :
- `curl -s https://api.edulinkage.com/api/v1/public/subscription-pricing` renvoie les montants de la grille active.
- Pendant la construction du web, l'ancienne API ne connaît pas encore la route. La page affiche donc « Tarifs sur demande » jusqu'à sa première régénération, au plus 5 minutes après la première visite.
- Ensuite, `https://edulinkage.com/#tarifs` montre 30 000 / 57 000 / 108 000 FCFA, et les boutons WhatsApp ouvrent une conversation avec le bon numéro.

**Retour arrière** : retaguer `avant-landing` en `latest` pour `edusphere-api` et `edusphere-web`, puis `docker compose up -d api web`.

## 5. Journal de mise en production (2026-11-16)

Déploiement depuis `/opt/edusphere`, avec les commandes du §4 enchaînées dans un seul bloc qui s'arrête à la première erreur :
- avance rapide `465de4e..5c7f8f0` (PR #37) ;
- images de secours `edusphere-api:avant-landing` et `edusphere-web:avant-landing` ;
- construction de l'API et du web réussie, puis `up -d api web`.

La CI de `main` tournait encore au moment du déploiement. Le code fusionné avait le même arbre (`cceec5e`) que la branche, dont les trois contrôles étaient verts.

Vérifications :
- l'API est `healthy` ;
- `GET https://api.edulinkage.com/api/v1/public/subscription-pricing` renvoie la devise `XOF`, les cinq tranches, le palier de 250 élèves et les montants de la grille HT active (30 000 / 57 000 / 108 000 de base, le reste conforme à la grille du 2026-11-15) ;
- depuis le conteneur web, la même adresse répond `200` : le serveur Next.js lit bien les tarifs ;
- la page affichait « Tarifs sur demande » juste après le redémarrage, comme prévu au §4, puis le simulateur environ 30 secondes plus tard.

**Constat.** Dans les journaux, l'API voit chaque appel venir de `172.18.0.1`, la passerelle du réseau Docker, et non de l'adresse du visiteur. Uvicorn (0.30.1) ignore `X-Forwarded-For` hors de `FORWARDED_ALLOW_IPS`, qui vaut `127.0.0.1` par défaut.

Les limites calculées « par adresse IP » sont donc en fait communes à tout le monde :
- vérification des bulletins (30 par minute) ;
- réinitialisation du mot de passe (10 par 15 minutes) ;
- notifications PayGate (120 par minute) ;
- tarifs publics (120 par minute).

La connexion, l'oubli de mot de passe, le renouvellement de session, les paiements et les annonces ne sont pas concernés : leur limite dépend du compte ou de l'adresse e-mail.

À traiter à part, après lecture de la configuration nginx du serveur.

**Résolu le 2026-11-16.**
- Lecture de `nginx -T`, filtrée : le vhost `api.edulinkage.com` transmet `X-Real-IP`, `X-Forwarded-For` (`$proxy_add_x_forwarded_for`) et `X-Forwarded-Proto`. Le réseau `edusphere_default` est en `172.18.0.0/16`, passerelle `172.18.0.1`.
- Simulation locale avec le `ProxyHeadersMiddleware` d'uvicorn 0.30.1 et `FORWARDED_ALLOW_IPS=172.18.0.1` :
  - le visiteur est vu à sa vraie adresse, même s'il falsifie `X-Forwarded-For` ;
  - le serveur Next.js garde sa propre adresse (`172.18.0.3`) ;
  - le contrôle de santé interne est inchangé ;
  - un conteneur qui appelle l'API directement n'est pas cru.
- Production : `FORWARDED_ALLOW_IPS=172.18.0.1` ajouté au `.env` du serveur, puis `docker compose up -d --force-recreate --no-deps api`. L'API est `healthy` et la variable est lue dans le conteneur. Un appel normal et un appel avec `X-Forwarded-For: 1.2.3.4` sont tous deux journalisés depuis `82.25.116.196`, l'adresse réelle du serveur qui appelait, et non plus depuis `172.18.0.1`.
- Incident sans conséquence : la commande de retour arrière a été collée par erreur juste après le test, puis le réglage a été remis et vérifié de nouveau.

Documentation : `.env.example` et `docs/deployment/PRODUCTION_CONFIGURATION.md`, paragraphe « Adresse réelle des visiteurs ».
