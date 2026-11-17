# Renforcement de sécurité — novembre 2026

Revue de sécurité du 2026-11-17 (API, site, dépendances, configuration Docker et serveur). Ce document
décrit les **corrections apportées** ; il ne recense pas de faiblesse ouverte (le dépôt est public).

## Corrections

**Dépendances**
- **Site** : Next.js 14.2.5 → **14.2.35** (dernière version 14.x, nombreuses failles corrigées).
  L'optimiseur d'images (`/_next/image`) est **désactivé** (`images.unoptimized`) : le site n'affiche
  que ses propres logos, et les failles graves de cet optimiseur ne sont corrigées qu'à partir de
  Next.js 15.5.
- **API** : FastAPI 0.111 / Starlette 0.37 → **FastAPI 0.163.1 / Starlette 1.10**, pydantic 2.14
  (dénis de service corrigés, dont CVE-2024-47874). httpx, email-validator et python-multipart, que
  l'ancienne FastAPI installait d'office, sont déclarés explicitement.
- **defusedxml** : utilisé automatiquement par openpyxl pour lire les classeurs Excel importés
  (bombes XML, entités externes).

**Connexion et mots de passe**
- **Réinitialisation du mot de passe** : ferme toutes les sessions ouvertes du compte et rend
  inutilisables les autres liens de réinitialisation encore valides.
- **Échecs de connexion par adresse IP** en plus du compteur par email : 50 échecs en 15 minutes
  depuis une même adresse (`LOGIN_IP_RATE_LIMIT_MAX_FAILURES`, `LOGIN_IP_RATE_LIMIT_WINDOW_SECONDS`).
  Seuls les échecs comptent ; une école entière derrière une même adresse n'y arrive pas en usage normal.
- **Nouveau mot de passe** (`app/core/passwords.py`) : 12 à 128 caractères, ni mot de passe très
  courant, ni un seul caractère répété. Les mots de passe existants ne changent pas.

**Fichiers et PDF**
- **PDF** (bulletins, reçus) : xhtml2pdf ne charge plus que les ressources intégrées (`data:`). Un
  modèle de bulletin ne peut plus faire lire un fichier du serveur ni appeler une adresse réseau.
- **Téléchargement d'un document** : nom de fichier nettoyé et encodé (RFC 6266). Un guillemet ou un
  retour à la ligne dans le nom ne casse plus l'en-tête.

**Site**
- **Politique de contenu (CSP) désormais bloquante** :
  - appels réseau limités au site et à l'API ;
  - images limitées au site, aux images intégrées (`data:`) et aux fichiers créés sur place (`blob:`) ;
  - aucun plugin, aucune mise en cadre, formulaires vers le site seulement.

  Scripts et styles « inline » restent permis : Next.js 14 en insère dans chaque page, et une
  politique par nonce imposerait un rendu dynamique, incompatible avec les pages gardées hors
  connexion (Phase 32).
- **`X-Powered-By: Next.js`** n'est plus envoyé.

## Serveur (à appliquer par l'exploitant)
- nginx : `server_tokens off;` dans les blocs `server` d'EduLinkage seulement. La configuration de
  l'autre projet hébergé sur le serveur n'est pas touchée.

## Vérifications (2026-11-17)
- **API** :
  - ruff, mypy, collecte des 1 166 tests ;
  - les tests qui tournent sans base, exécutés et réussis : règle des mots de passe, PDF sans
    ressource externe, en-tête de téléchargement, reçu officiel ;
  - un test de fumée de la nouvelle FastAPI (santé, en-têtes de sécurité, 401, 422, CORS, 404) ;
  - le reste de la suite, dont `tests/test_security_review.py`, tourne dans la CI.
- **Site** : vérification des types, analyse du code, `test:config`, build de production.
- **CSP bloquante dans Chromium** : pages publiques, administrateur, enseignant et caissier. Aucune
  violation, aucune image cassée, aucune erreur JavaScript.
- **Non-régression** : tous les parcours hors connexion (lots 1 à 3, connexion sans internet) réussis.
