# EduSphere — Vue d'ensemble architecture (Phase 0)

## Contexte

EduSphere est une plateforme SaaS scolaire **multi-tenant** destinée au
marché africain. Ce document reprend les principes structurants fixés par le
cahier des charges et le document d'architecture technique, tels
qu'appliqués au bootstrap technique (Phase 0).

## Principe directeur : phases indépendantes et vérifiables

Le projet ne se construit pas en une fois. Chaque phase livre un incrément
testable et stable avant que la suivante ne démarre. La Phase 0 pose
uniquement la fondation technique — aucune fonctionnalité métier.

## Monorepo

- Gestion des dépendances JS/TS via **pnpm workspaces**.
- Trois applications indépendantes : `apps/web` (Next.js), `apps/api`
  (FastAPI), `apps/mobile` (Expo/React Native).
- Code partagé dans `packages/` (`types`, `ui`, `config`, `validation`),
  consommé par les apps au fur et à mesure des besoins réels — pas de
  contenu spéculatif.

## Multi-tenancy

Le modèle de multi-tenancy (isolation des données par établissement
scolaire) sera défini et implémenté en **Phase 1**. La Phase 0 ne contient
aucune table ni logique liée aux tenants, écoles, utilisateurs ou élèves.

## Stockage de fichiers : abstraction dès le départ

Aucun hébergeur cloud n'est choisi à ce stade. Pour éviter tout couplage
prématuré, l'API expose une interface `StorageProvider`
(`apps/api/app/core/storage.py`) :

```python
class StorageProvider(ABC):
    async def upload(self, path: str, content: bytes) -> str: ...
    async def download(self, path: str) -> bytes: ...
    async def delete(self, path: str) -> None: ...
    async def get_url(self, path: str) -> str: ...
```

En développement, `LocalStorageProvider` implémente cette interface sur le
filesystem local. Une implémentation compatible S3 (ou autre) pourra être
ajoutée plus tard sans modifier le code appelant. Le choix définitif
d'hébergeur sera tranché avant la phase de déploiement production.

## Infrastructure locale

- **PostgreSQL 16** et **Redis 7** tournent via Docker Compose
  (`docker-compose.yml` à la racine).
- Les migrations de schéma passent par **Alembic**, configuré en mode async
  (SQLAlchemy 2.0). La migration initiale de la Phase 0 ne crée qu'une table
  technique de vérification (`_bootstrap_check`), pas de table métier.

## CI

GitHub Actions exécute, pour chaque application, lint, vérification de
types et build (tests pour l'API). La CI doit être verte avant toute
fusion.

## Secrets

Aucun secret n'est committé. `.env.example` documente toutes les variables
attendues avec des valeurs factices ; `.gitignore` exclut `.env` et tout
fichier de clé/certificat.

## Prochaine phase

**Phase 1 — Authentification & Multi-tenancy** a démarré après validation
explicite que la Phase 0 était stable (les trois apps démarrent, la CI est
verte, ce rapport a été relu). Les principes ci-dessus (monorepo,
abstraction du stockage, infrastructure locale, CI, secrets) restent en
vigueur pour toutes les phases suivantes. Voir [README.md](../../README.md)
pour le statut d'avancement actuel.
