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
