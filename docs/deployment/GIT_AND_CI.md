# Git & CI — Processus de livraison

Phase 18 (Pilot Readiness & Git/CI). Décrit l'état réel du dépôt Git, le workflow GitHub Actions
existant, et la procédure de livraison — ce qui est **prouvé localement** vs **prouvé sur GitHub**
étant deux choses différentes, jamais confondues dans ce document.

## État réel (Phase 18)

- Dépôt Git initialisé localement (`git init`, branche `main`), 271 fichiers stagés en un
  premier commit — voir [`docs/phases/PHASE_18_IMPLEMENTATION.md`](../phases/PHASE_18_IMPLEMENTATION.md)
  pour le détail complet et l'état exact du commit.
- **Aucun remote GitHub configuré.** `REMOTE GITHUB : ABSENT`.
- **`git` n'est pas installé sur le PATH Windows natif de cet hôte** — disponible uniquement via
  l'environnement WSL déjà utilisé ailleurs dans ce projet (`/usr/bin/git`, confirmé
  fonctionnel). Toute commande Git sur cet hôte doit passer par `bash -c "cd '<chemin WSL> ' &&
  /usr/bin/git ..."`, en utilisant le chemin monté (`/mnt/c/...`), pas un chemin Windows direct.

## Pourquoi WSL et pas Git pour Windows

Aucune installation de Git pour Windows n'existe sur cette machine (vérifié : absent du `PATH`,
absent de `Program Files`/`Program Files (x86)`). Plutôt que d'installer un nouvel outil pour
cette phase, l'environnement WSL déjà présent et déjà utilisé dans ce projet (voir les phases
précédentes concernant `bash`/`tar`) fournit un `git` fonctionnel. Cohérent avec la consigne de
ne pas alourdir l'environnement sans nécessité.

## Workflow GitHub Actions

`.github/workflows/ci.yml` existait déjà avant cette phase (créé en tout début de projet, jamais
exécuté faute de dépôt Git) — **conservé sans réécriture**, seulement validé :

- Syntaxe YAML confirmée valide (`yaml.safe_load` réel, pas une relecture visuelle).
- 3 jobs : `web` (lint, type-check, build), `mobile` (type-check), `api` (ruff, mypy, migration
  Alembic, pytest — avec services PostgreSQL et Redis **éphémères**, jamais la base locale ni de
  production).
- Chaque étape reproduite **réellement en local** dans cette phase, résultats dans
  [`docs/phases/PHASE_18_IMPLEMENTATION.md`](../phases/PHASE_18_IMPLEMENTATION.md).

## Décision : pas de build Docker dans la CI (Phase 18)

Évalué explicitement, décision de **ne pas ajouter** de job de build Docker à
`.github/workflows/ci.yml` cette phase :

- La validation Docker (build API + Web) est déjà démontrée **localement**, à de multiples
  reprises depuis la Phase 13, y compris dans cette phase même (`docker compose build`, succès
  réel, voir rapport Phase 18).
- Le job `api` de la CI existante valide déjà ce qui compte le plus (tests, types, migrations) —
  un job Docker supplémentaire ralentirait la CI pour une garantie largement redondante avec ce
  que le job `api`/`web` valide déjà (le code qui tourne dans l'image est le même code que celui
  testé/lint/typé).
- Aucun registre, aucun push d'image n'est de toute façon prévu — un job CI Docker n'aurait
  d'utilité que comme "smoke test" de construction, pas comme étape de déploiement.

Si ce choix doit être révisé plus tard (ex. un Dockerfile casse silencieusement sans qu'aucun
test ne le détecte), ajouter un job minimal `docker build` sur API et Web uniquement, sans
Compose complet, sans registre — pas avant qu'un besoin réel soit démontré.

## `REMOTE GITHUB : ABSENT` / `REMOTE CI EXECUTION : NOT VERIFIED`

Ces deux affirmations sont distinctes et doivent le rester :

- **`CI workflow créé et validé localement`** — vrai, prouvé (syntaxe + reproduction de chaque
  étape).
- **`CI exécutée avec succès sur GitHub`** — **faux à ce stade**, impossible à affirmer tant
  qu'aucun remote n'existe. Ne jamais écrire "CI GitHub validée" avant qu'un push réel vers un
  dépôt GitHub ait réellement déclenché le workflow et que son résultat ait été observé.

## Procédure de livraison

1. Créer une branche depuis `main` (`git checkout -b <nom>`).
2. Développer, en respectant le périmètre de la tâche.
3. Lancer les tests localement AVANT de committer :
   `pytest -q` / `ruff check .` / `mypy app` (API) ;
   `pnpm --filter @edusphere/web lint/type-check/build` (Web) ;
   `tsc --noEmit` (Mobile, via `apps/mobile`).
4. `git add` puis vérifier `git status`/`git diff --cached --name-only` — aucun secret, aucun
   fichier runtime (`.env`, `backups/`, `apps/api/storage/`).
5. `git commit` (identité Git requise — voir "Identité Git" ci-dessous).
6. `git push` vers la branche de fonctionnalité (nécessite un remote configuré — absent à ce
   stade, voir ci-dessus).
7. Ouvrir une Pull Request vers `main`.
8. Attendre le résultat de la CI GitHub Actions (jobs `web`/`mobile`/`api`) — non exécutable tant
   qu'aucun remote n'existe.
9. Merger seulement si la CI est verte.
10. Déployer (voir `docs/deployment/PRODUCTION_CONFIGURATION.md`, `RELEASE_CHECKLIST.md`).

Aucune stratégie de branches complexe imposée — une branche principale (`main`), des branches de
fonctionnalité courtes, des Pull Requests validées par la CI avant fusion. Rien de plus pour un
projet à ce stade.

## Identité Git

**Non configurée sur cet hôte** au moment de la Phase 18 — ni `user.name` ni `user.email`,
globalement ou localement. Une identité doit être fournie explicitement avant tout commit ; ce
projet n'en invente jamais une par défaut (voir
[`docs/phases/PHASE_18_IMPLEMENTATION.md`](../phases/PHASE_18_IMPLEMENTATION.md) pour l'état
exact au moment de la rédaction).

## Créer/connecter un remote GitHub (procédure, non exécutée)

Aucun remote n'est inventé par ce projet. Lorsqu'un dépôt GitHub réel existe :

```bash
git remote add origin <URL fournie par vous>
git push -u origin main
```

Le `push` ne doit être exécuté qu'avec une autorisation explicite — jamais automatiquement.
