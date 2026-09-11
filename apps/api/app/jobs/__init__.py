"""Un job standalone (`python -m app.jobs.<module>`) démarre dans un process Python neuf, sans
passer par `app.main` (qui importe transitivement tous les modèles ORM via ses routers) : seuls
les modèles réellement importés par le job lui-même sont alors connus de `Base.metadata`. Une
`ForeignKey("<table>")` référencée par nom de table (ex. `notifications.recipient_user_id` ->
`users.id`) n'est résolue par SQLAlchemy qu'à la configuration des mappers — si le module
propriétaire de cette table n'a jamais été importé, cela lève `NoReferencedTableError` au premier
usage, même si le schéma PostgreSQL et Alembic sont parfaitement à jour.

`app/db/model_registry.py` existe déjà pour ce problème côté Alembic (voir `alembic/env.py`) : il
importe explicitement tous les modules de modèles pour peupler `Base.metadata`. On réutilise ici
le même mécanisme plutôt que d'ajouter des imports ad hoc dans chaque job — `python -m
app.jobs.<module>` exécute toujours ce fichier avant le sous-module ciblé, ce qui couvre tout job
présent ou futur de ce paquet."""

from app.db import model_registry  # noqa: F401
