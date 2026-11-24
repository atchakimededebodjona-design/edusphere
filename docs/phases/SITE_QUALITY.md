# Qualité du site public — demande du 2026-11-24

Demande de l'exploitant (liste de 18 points). Le travail est découpé en trois PR :

1. **Connexion** (`feat/authprovider-403`) : `AuthProvider` ne demande plus le nom de l'organisation ou de l'école aux comptes qui n'ont pas le droit de les lire. Ce fichier protégé a été modifié avec l'accord de l'exploitant.
2. **Qualité du site** (ce document) : référencement, images, page 404, anti-spam, contrastes, appel à l'action, liens, vitesse.
3. **Juridique et audience** : politique de confidentialité, CGU, CGV, bandeau cookies, mesure d'audience Umami hébergée sur le serveur.

## Points déjà en place, vérifiés

- **HTTPS forcé** : la redirection de HTTP vers HTTPS et l'en-tête HSTS sont en place depuis la revue de sécurité (2026-11-17). Ils ont été vérifiés de l'extérieur à ce moment-là. Le site ne contient aucune adresse en `http://`.
- **Aucune clé secrète côté site** :
  - le site ne lit qu'une variable au build, `NEXT_PUBLIC_API_URL`, l'adresse publique de l'API ;
  - la clé publique des notifications téléphone est fournie par l'API (`/push/config`) ;
  - le jeton PayGate, la clé privée VAPID, `JWT_SECRET_KEY` et l'identité de facturation restent dans le `.env` du serveur ;
  - une recherche dans le JavaScript livré aux visiteurs (`.next/static`) ne trouve aucun secret ;
  - aucun fichier `.env` n'est suivi par git.

## Référencement

- **Titres** : chaque page qui déclare son titre s'affiche sous la forme « Page — EduLinkage » (`title.template` dans `app/layout.tsx`). La page d'accueil garde son titre complet (`title.absolute`).
- **Descriptions** : description par défaut revue. Titres et descriptions propres à la connexion et au mot de passe oublié (`layout.tsx` de chaque route, car ces pages sont des composants client).
- **Exclusion des moteurs de recherche** :
  - espaces connectés (`(app)`, `teacher`, `parent`), liens personnels (définition du mot de passe, vérification d'un bulletin) et page hors connexion : `noindex` ;
  - `app/robots.ts` les exclut aussi et indique le sitemap.
- **Sitemap** : `app/sitemap.ts` liste les pages publiques (accueil, connexion). Les pages juridiques s'y ajouteront avec la PR 3.
- **Aperçu sur les réseaux sociaux** : `public/og-image.jpg` (1200 × 630, 42 Ko), au format recommandé par Facebook, WhatsApp, LinkedIn et X, avec un texte alternatif. Il est composé du logo officiel non retouché, sur le fond de la marque.
- **Page 404** : `app/not-found.tsx`, en français, dans le cadre de la connexion. Elle renvoie vers l'accueil et la connexion, avec un vrai code HTTP 404.

## Images

Les images sont servies telles quelles (`images.unoptimized`, revue de sécurité), donc leur poids compte directement. Les originaux sont gardés dans `apps/web/branding-sources/`, qui n'est pas servi. Les fichiers servis sont ces originaux redimensionnés, sans retouche :

| Fichier | Avant | Après |
|---|---|---|
| Logo complet (connexion, pages d'accès) | PNG 1536 × 1024, 1,7 Mo | WebP 780 × 520, 93 Ko |
| Symbole (en-tête de chaque page) | PNG 1254 × 1254, 657 Ko | PNG 256 × 256, 42 Ko |
| Icône de l'onglet (`app/icon.png`) | PNG 1254 × 1254, 657 Ko | PNG 256 × 256, 42 Ko |

Le service hors connexion garde moins de données à l'installation : l'ancien logo de 1,7 Mo n'est plus servi.

**Textes alternatifs** :
- le logo a un texte alternatif (« EduLinkage », « Logo EduLinkage ») ;
- l'aperçu de réseaux sociaux a le sien ;
- les icônes et les maquettes d'écran de la page d'accueil sont décoratives (`aria-hidden`).

Le contrôle d'accessibilité vérifie que chaque image affichée a un `alt`.

## Page d'accueil

- **Appel à l'action** :
  - le bouton principal devient « Essayer gratuitement », vers WhatsApp avec un message prérempli, accompagné de « Premier trimestre offert » ;
  - sur téléphone, une barre « Essayer gratuitement — 1er trimestre offert » reste en bas de l'écran une fois le haut de page dépassé (`components/landing/StickyCta.tsx`). Elle se masque dans la section « Contact », qui propose déjà les mêmes boutons, et sur le pied de page.
- **Contrastes** :
  - les textes réels en gris clair (`slate-400`) passent en gris lisible (`slate-600`) : mention sous les fonctionnalités, copyright, liens du pied de page, durée du simulateur ;
  - sur le fond bleu nuit de « Contact », la devise passe de `slate-500` (environ 3,9:1) à `slate-300` ;
  - les maquettes décoratives passent de `slate-400` à `slate-500`.
- **Protection anti-spam de l'adresse e-mail** : l'adresse n'est plus écrite dans le HTML envoyé par le serveur. Elle est assemblée dans le navigateur après le chargement (`components/landing/ProtectedEmail.tsx`), donc les robots qui collectent les adresses sur les pages ne la trouvent pas.

## Protection anti-spam des formulaires

« Mot de passe oublié » déclenche l'envoi d'un e-mail. Jusqu'ici, la demande était limitée par adresse e-mail seulement : 3 par quart d'heure. Un robot qui change d'adresse à chaque demande pouvait donc faire envoyer des centaines d'e-mails à des inconnus.

La demande est maintenant aussi limitée **par adresse IP** : 10 par heure, assez pour toute une école derrière la même connexion (`forgot_password_ip_rate_limit_*` dans `app/core/config.py`). La réponse reste générique : elle n'indique jamais si un compte existe.

La connexion était déjà limitée par adresse e-mail et par adresse IP, et la définition du mot de passe par adresse IP. Le site n'a pas de formulaire de contact public : le contact passe par WhatsApp, le téléphone et l'e-mail.

## Vérifications

- **API** : `tests/test_forgot_password_ip_rate_limit.py` (sous le seuil, puis au-delà avec des adresses toutes différentes) et les tests des limites existantes : 47 tests réussis.
- **Site** (build de production, vraie API) :
  - vérification des types, analyse du code ;
  - **42 vérifications** du scénario de ce lot ;
  - **92 vérifications** d'accessibilité des pages publiques, accueil et 404 comprises ;
  - poids mesuré sur téléphone :
    - accueil : 278 Ko en 16 requêtes, dont 42 Ko d'images (le symbole pesait seul 657 Ko avant) ;
    - connexion : 318 Ko, dont 93 Ko d'images (environ 2,4 Mo d'images avant) ;
  - non-régression : pages d'accès (52), règles de connexion (52), enveloppes (105) et les 8 scénarios hors connexion (124), dont la connexion sans internet ; le service hors connexion garde 167 fichiers ;
  - le scénario couvre le référencement, la page 404, le poids des images, l'adresse protégée, l'appel à l'action, les liens internes et ancres de toutes les pages publiques, le poids et le temps de chargement sur téléphone.
