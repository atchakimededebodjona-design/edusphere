# EduSphere

Plateforme SaaS scolaire multi-tenant pour l'Afrique — monorepo.

> **Statut : phases 0 à 5 livrées, API et web.** Côté API (FastAPI) :
> bootstrap, auth + multi-tenancy, administration scolaire, élèves,
> académique (notes/moyennes/classement) et génération de bulletins PDF
> avec vérification par QR code. Côté web (Next.js) : session persistante
> et layout protégé, puis une interface complète pour chaque module —
> École, Configuration académique, Élèves, Notes, Bulletins (génération,
> publication, téléchargement, page publique de vérification par QR).
> L'app mobile est encore au stade de scaffold, rien n'y est construit.
>
> Manques connus, volontairement hors périmètre pour l'instant :
> - affectation d'enseignants à une classe-matière (bloqué en amont :
>   aucun endpoint API ne liste/recherche les utilisateurs d'une école) ;
> - app mobile non démarrée.
>
> Voir [docs/architecture/overview.md](docs/architecture/overview.md).

## Structure du monorepo

```
edusphere/
├── apps/
│   ├── web/          # Next.js (TypeScript, Tailwind)
│   ├── api/           # FastAPI (Pydantic, SQLAlchemy, Alembic)
│   └── mobile/         # Expo / React Native (TypeScript)
├── packages/
│   ├── types/           # types partagés (vide, Phase 0)
│   ├── ui/               # composants UI partagés (vide, Phase 0)
│   ├── config/            # configuration partagée (vide, Phase 0)
│   └── validation/         # schémas de validation partagés (vide, Phase 0)
├── infrastructure/
│   ├── docker/
│   ├── nginx/
│   ├── monitoring/
│   └── deployment/
├── docs/
└── scripts/
```

## Prérequis

- Node.js 20 (voir `.nvmrc`)
- pnpm 9 (`corepack enable`)
- Python 3.12
- Docker + Docker Compose

## Démarrage rapide (Docker)

```bash
cp .env.example .env
docker compose up --build
```

- Web : http://localhost:3000
- API : http://localhost:8000
- Health check : http://localhost:8000/api/v1/health
- Postgres : localhost:5432
- Redis : localhost:6379

## Développement local (sans Docker)

### Web

```bash
pnpm install
pnpm --filter @edusphere/web dev
```

### API

```bash
cd apps/api
python -m venv .venv
. .venv/Scripts/activate   # Windows (Git Bash: source .venv/Scripts/activate)
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

Migrations :

```bash
cd apps/api
alembic upgrade head
```

### Mobile

```bash
pnpm install
pnpm --filter @edusphere/mobile start
```

## Tests

```bash
# API
cd apps/api && pytest

# Web
pnpm --filter @edusphere/web lint
pnpm --filter @edusphere/web type-check
pnpm --filter @edusphere/web build
```

## Variables d'environnement

Voir [.env.example](.env.example). Ne jamais committer `.env`.

## Stockage de fichiers

Le stockage passe par l'interface `StorageProvider`
(`apps/api/app/core/storage.py`) — aucun fournisseur cloud n'est figé à ce
stade. L'implémentation par défaut (`LocalStorageProvider`) écrit sur le
filesystem local pour le développement.

## Prochaine étape

Combler l'un des manques listés ci-dessus (module utilisateurs pour
l'affectation d'enseignants, ou démarrage de l'app mobile), ou entamer une
nouvelle phase métier (ex. paiements).
