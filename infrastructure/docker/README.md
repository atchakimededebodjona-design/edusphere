# infrastructure/docker

Le `docker-compose.yml` de la Phase 0 vit à la racine du monorepo — il suffit
pour le développement local (postgres, redis, api, web).

Ce dossier est réservé aux ressources Docker additionnelles (compose
overrides par environnement, scripts d'init) qui seront ajoutées dans les
phases suivantes, une fois la stratégie d'hébergement tranchée.
