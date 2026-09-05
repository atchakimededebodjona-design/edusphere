# Release Checklist

Phase 18. À vérifier avant toute livraison — chaque case ne doit être cochée que si l'élément a
été **réellement vérifié pour cette livraison précise**, pas parce qu'il l'a été une fois par le
passé. Voir [`docs/deployment/GIT_AND_CI.md`](GIT_AND_CI.md) pour la procédure complète.

- [ ] Git propre — `git status` sans modification non intentionnelle, branche à jour
- [ ] Aucun secret — `git diff --cached` relu, aucune valeur sensible réelle
- [ ] `pytest -q` OK (backend)
- [ ] `ruff check .` OK
- [ ] `mypy app` OK
- [ ] Web lint OK (`pnpm --filter @edusphere/web lint`)
- [ ] Web build OK (`pnpm --filter @edusphere/web build`)
- [ ] Mobile type-check OK (`tsc --noEmit` dans `apps/mobile`)
- [ ] Migrations vérifiées — `alembic current` = `alembic heads`, aucune migration orpheline
- [ ] Docker build OK — `docker compose build` (API + Web) sans erreur
- [ ] `/health` OK — `200 {"status":"ok"}` réellement observé
- [ ] `/ready` OK — `200` avec `database`/`redis`/`storage` tous `"ok"` réellement observé
- [ ] Backup récent — un dump PostgreSQL + une archive storage produits dans les dernières 24h
      (voir `docs/database/BACKUP_RESTORE.md`)
- [ ] Restore récemment vérifié — un test de restauration réel effectué récemment, pas seulement
      "un jour, ça a marché" (voir `docs/database/STORAGE_BACKUP_RESTORE.md`)
- [ ] Configuration SMTP vérifiée — `EMAIL_PROVIDER` correspond à l'intention réelle du
      déploiement (`local` en dev, `smtp` seulement si un compte réel est configuré et testé —
      voir `docs/deployment/PRODUCTION_CONFIGURATION.md`)
- [ ] Documentation à jour — tout changement de comportement reflété dans les docs concernées
- [ ] Rollback possible — image précédente disponible, dernier backup identifié et restaurable

## Note sur la CI distante

Cette checklist reste valable même sans CI GitHub exécutée (voir `GIT_AND_CI.md` — remote
absent à ce jour). Toutes les vérifications ci-dessus sont conçues pour être exécutables
localement, exactement comme le fait le workflow `.github/workflows/ci.yml` — la CI, une fois
un remote connecté, ne fait qu'automatiser ce que cette checklist demande déjà de faire à la
main.
