# Runbook support — EduSphere

Phase 23 (Production Observability & Configuration Hardening). Ce document couvre le **premier
niveau de réponse** face à un incident signalé par une école pilote — pas la reprise après
sinistre infrastructurel (conteneur/base/stockage perdu), déjà couverte par
[`DISASTER_RECOVERY.md`](../deployment/DISASTER_RECOVERY.md).

**Principe directeur (même règle de vérité que le reste du projet)** : ne jamais deviner la cause
d'un incident avant de l'avoir réellement vérifiée dans les logs/la base. Ce document donne où
chercher, pas des suppositions à annoncer à l'école avant vérification.

**Règle absolue** : ne jamais demander à un utilisateur (école, enseignant, parent) de fournir un
mot de passe, un token, un secret, ou une clé API — quelle que soit l'urgence. Un `Request ID` ou
un email/nom suffit toujours à investiguer.

## Utiliser le Request ID (Phase 23)

Depuis la Phase 23, chaque réponse de l'API contient un en-tête `X-Request-Id` (visible dans les
outils réseau du navigateur — onglet "Réseau"/"Network" des outils de développement — ou dans tout
message d'erreur technique que l'école pourrait avoir capturé). Chaque ligne de log produite
pendant le traitement de cette requête porte le **même** `request_id` (voir
`apps/api/app/core/log_context.py`).

Pour retrouver la trace exacte :

```bash
docker compose logs api | grep '"request_id": "<ID_FOURNI>"'
```

ou, pour ne garder que les lignes de niveau erreur/critique de cette requête :

```bash
docker compose logs api | grep '"request_id": "<ID_FOURNI>"' | grep -E '"level": "(ERROR|CRITICAL)"'
```

Chaque ligne est un objet JSON complet (`timestamp`, `level`, `logger`, `message`, et
`request_id`/`user_id`/`organization_id`/`school_id` quand disponibles) — lisible directement,
ou via `| jq .` si `jq` est installé sur la machine d'exploitation.

**Si l'école ne peut pas fournir de Request ID** (cas le plus fréquent en pratique) : demander
l'heure approximative de l'incident et l'action effectuée ("j'ai cliqué sur Publier le bulletin de
la classe CE1 vers 14h32"), puis chercher dans les logs de cette fenêtre de temps :

```bash
docker compose logs api --since "2026-09-06T14:25:00" --until "2026-09-06T14:40:00"
```

## Scénario 1 — Un enseignant ne peut pas se connecter

**Symptômes** : message "Invalid email or password" (401) ou page de connexion qui ne progresse
jamais.

**Informations à demander à l'école** :
- L'adresse email exacte utilisée (jamais le mot de passe).
- Un message d'erreur exact affiché à l'écran, si possible une capture d'écran.
- Si possible, le `Request ID` de la tentative (voir ci-dessus).

**Où chercher** :
- Le compte existe-t-il et est-il actif ? Vérifier via `/users` (web, permission `users.manage`)
  ou directement en base (`SELECT email, is_active FROM users WHERE email = '<email>';` — jamais
  afficher `hashed_password`).
- Le compte a-t-il un rôle scopé à la bonne école ? (`user_roles` — voir
  `apps/api/app/modules/rbac/models.py`).
- Le compte a-t-il été désactivé récemment par un admin (Phase 22 — `PATCH /users/{id}`,
  `is_active=false`) ? À confirmer avec l'école avant de réactiver : une désactivation volontaire
  (départ de l'enseignant) ne doit pas être annulée sans vérification.
- Rate limiting : 5 tentatives échouées / 5 minutes par email (`app/core/rate_limit.py`) — un
  enseignant qui vient de changer de mot de passe et retape l'ancien plusieurs fois peut se voir
  bloqué temporairement (`429`). Se résout seul après la fenêtre, ou en vidant la clé Redis
  `login_attempts:<email>` si une vérification immédiate est nécessaire.

**Comment utiliser le request_id** : chercher `"logger": "app.modules.auth"` ou
`"logger": "app.core.rate_limit"` autour de l'heure indiquée.

**Vérifications de base** : `docker compose ps` (tous healthy), `GET /api/v1/ready`.

**Quand escalader** : si le compte est actif, non rate-limité, avec le bon rôle, et l'échec
persiste — cas non couvert par ce runbook, remonter avec le `request_id` exact et l'heure précise.

**Ne pas faire** : ne jamais réinitialiser un mot de passe sans confirmation explicite de
l'identité de la personne (le token de réinitialisation donne un accès complet au compte).

## Scénario 2 — Un administrateur ne voit pas une donnée attendue

**Symptômes** : "je ne vois pas l'élève X", "la classe n'apparaît pas", "le paiement a disparu".

**Informations à demander** : l'identifiant ou le nom exact de la donnée attendue, l'école/la
classe concernée, le rôle du compte qui constate l'absence.

**Où chercher** :
- **Isolation multi-tenant (RLS)** — la cause la plus fréquente : la donnée existe mais appartient
  à une autre école/organisation, invisible par conception (voir
  `apps/api/tests/test_tenant_isolation.py` pour le comportement attendu — un 404 sur une
  ressource d'un autre tenant est **normal**, pas un bug).
- Le rôle du compte a-t-il la permission de lecture nécessaire (`students.read`, `grades.read`,
  etc.) ? Un enseignant ne voit que ses classes affectées (`TeacherAssignment`) — vérifier
  l'affectation avant de conclure à un bug.
- La donnée a-t-elle été créée dans la bonne école (`school_id`) ? Une erreur de saisie lors de la
  création (mauvaise école sélectionnée dans un compte multi-établissements) est une cause réelle
  déjà rencontrée dans ce type de produit.

**Comment utiliser le request_id** : la requête `GET` correspondante (ex. `GET /students?...`)
loguée avec ce `request_id` ne produit normalement AUCUNE ligne d'erreur si la cause est un
filtrage RLS normal — l'absence de log est elle-même une information (pas un bug silencieux).

**Vérifications de base** : reproduire la recherche avec un compte `SUPER_ADMIN`/`SCHOOL_ADMIN` de
la bonne école pour confirmer si la donnée existe réellement à cet endroit.

**Quand escalader** : si la donnée est confirmée présente dans la bonne école, avec un compte
disposant de la bonne permission, et reste invisible — remonter avec le `request_id`.

**Ne pas faire** : ne jamais désactiver ou contourner la RLS pour "vérifier rapidement" — voir
`apps/api/app/core/tenancy.py::set_platform_wide_context`, réservé au code, jamais à une
investigation manuelle en production.

## Scénario 3 — L'import élèves produit des doublons/incohérences

**Symptômes** : le rapport d'import (`apps/web` — formulaire d'import, `apps/api/app/modules/
students/service.py::import_students`) signale des doublons inattendus, ou des élèves attendus
n'apparaissent pas après import.

**Informations à demander** : le fichier source (CSV/XLSX) si l'école peut le renvoyer, le rapport
d'import affiché après la tentative (nombre de lignes, créés, doublons ignorés, erreurs).

**Où chercher** :
- La déduplication se fait par `matricule` **et** par identité `(prénom, nom, date de naissance)`
  — un élève ré-importé avec un matricule légèrement différent mais la même identité est
  intentionnellement ignoré comme doublon (`service.py::import_students`, comportement voulu, pas
  un bug).
- Format de date : seul `AAAA-MM-JJ` (ou une vraie cellule date Excel) est accepté — une date au
  format `JJ/MM/AAAA` produit une erreur de ligne, pas un import silencieusement incorrect.
- Le fichier utilise-t-il exactement les colonnes `matricule, first_name, last_name,
  date_of_birth, sex` ? Aucune tolérance de nom de colonne alternatif n'existe actuellement (limite
  connue, voir `docs/phases/` Discovery — pas un bug à corriger dans l'urgence).
- Import partiel confirmé sain : chaque ligne est validée indépendamment, une ligne en erreur
  n'empêche pas les lignes valides d'être importées (voir le rapport retourné : `created` +
  `duplicates_skipped` + `errors` = `total_rows`).

**Comment utiliser le request_id** : chercher `"logger": "app.modules.students"` autour de l'heure
de l'import — un import ne produit pas de ligne `ERROR` pour un rejet de ligne individuel (compté
dans le rapport JSON renvoyé au client, pas dans les logs serveur) ; seule une erreur système
(ex. fichier corrompu) produit une ligne d'erreur serveur.

**Vérifications de base** : redemander le fichier exact utilisé et le rapport d'import affiché —
la quasi-totalité des cas se résout par une relecture du rapport déjà produit, jamais consulté
entièrement par l'école au moment de l'import.

**Quand escalader** : si le rapport d'import lui-même semble incohérent avec le fichier fourni
(ex. compte total erroné) — remonter avec le fichier et le rapport exacts.

**Ne pas faire** : ne jamais réimporter le même fichier "pour voir" sans d'abord comprendre le
premier rapport — la déduplication rend un second import globalement sûr, mais complique le
diagnostic du premier incident.

## Scénario 4 — Un bulletin ne se génère pas

**Symptômes** : la génération (`POST /report-cards/generate`) échoue, prend un temps anormalement
long, ou produit un PDF vide/incorrect.

**Informations à demander** : la classe et la période concernées, le nombre d'élèves de la classe,
si l'opération a fini par aboutir après un délai.

**Où chercher** :
- La génération est **synchrone** : pour une classe de 40 élèves, l'API génère 40 PDF l'un après
  l'autre avant de répondre (pas de file d'attente — limite connue, documentée dans la Discovery
  Phase 23, non corrigée par cette phase). Un délai de plusieurs secondes à un peu plus d'une
  minute pour une grande classe est un ralentissement connu, pas nécessairement une panne.
- Toutes les notes de la classe/période sont-elles saisies ? Un bulletin peut se générer avec des
  matières manquantes sans erreur explicite si la Discovery/le produit le permet — vérifier le
  taux de complétude via le tableau de bord école avant de conclure à un bug.
- Modèle de bulletin (`ReportCardTemplate`) : existe-t-il un modèle actif pour cette école ? Une
  classe sans modèle assigné ne peut pas générer de bulletin.

**Comment utiliser le request_id** : chercher `"logger": "app.modules.report_cards"`. Une erreur
de rendu (`xhtml2pdf`) apparaît en `ERROR` avec la trace complète (`exception` dans la ligne JSON)
mais sans jamais exposer cette trace à l'école (réponse HTTP générique, voir
`app/main.py::unhandled_exception_handler`).

**Vérifications de base** : `GET /api/v1/ready` (stockage fichiers en particulier — un bulletin
généré doit être écrit sur disque via `StorageProvider`).

**Quand escalader** : toute erreur de rendu PDF reproductible — remonter avec le `request_id` et
la classe/période exactes.

**Ne pas faire** : ne jamais relancer la génération en boucle rapprochée sur une classe nombreuse
en cas de lenteur apparente — chaque tentative relance les 40 rendus depuis le début.

## Scénario 5 — Un paiement semble incorrect ou refusé

**Symptômes** : un paiement enregistré n'apparaît pas dans le solde, une tentative
d'enregistrement échoue, un montant semble erroné.

**Informations à demander** : l'élève concerné, le montant exact, la méthode de paiement, si un
message d'erreur précis est apparu (ex. "Payment allocation exceeds the remaining balance").

**Où chercher** :
- **Idempotence** : chaque paiement porte une `idempotency_key` — une double soumission (double
  clic) avec la MÊME clé ne crée jamais de doublon, elle renvoie le paiement déjà existant
  (`apps/api/app/modules/fees/service.py::record_payment`). Un paiement "manquant" après un double
  clic apparent est presque toujours déjà enregistré une seule fois — vérifier `GET /payments`
  avant de conclure à une perte.
- **Sur-allocation refusée par conception** : un paiement ne peut jamais allouer plus que le solde
  restant d'un frais (`fees/service.py:217-220`) — un rejet ici est le comportement voulu, pas un
  bug, mais peut signaler une confusion sur le montant réellement dû par l'école.
- Le paiement a-t-il été annulé (`POST /payments/{id}/cancel`) par un autre utilisateur entre
  temps ? Vérifier `payment.status` et `cancelled_by`/`cancelled_reason`.
- Rate limiting (Phase 22) : 60 opérations de paiement par minute par utilisateur — un compte
  saisissant un volume inhabituel de paiements en rafale peut être temporairement bloqué (`429`).

**Comment utiliser le request_id** : chercher `"logger": "app.modules.fees"` — une tentative de
sur-allocation ou une idempotence déclenchée produit un log explicite à ce niveau.

**Vérifications de base** : `GET /students/{id}/financial-summary` pour confirmer l'état réel du
solde avant toute correction manuelle.

**Quand escalader** : tout écart confirmé entre le solde affiché et la somme réelle des paiements
enregistrés — ne jamais corriger un solde manuellement en base sans comprendre la cause exacte.

**Ne pas faire** : ne jamais annuler un paiement "pour repartir à zéro" sans confirmation de
l'école — l'annulation est tracée (`cancelled_by`) et n'est pas anodine pour la comptabilité de
l'école.

## Scénario 6 — Une école signale une erreur générique "ça ne marche pas"

**Symptômes** : signalement vague, sans détail technique.

**Démarche, dans l'ordre** :
1. Demander (jamais un secret) : quelle page/action précise, quel rôle (enseignant/parent/admin),
   quelle heure approximative, et — si possible — le `Request ID` (voir en-tête ci-dessus).
2. Vérifier l'état global du service AVANT de chercher un incident spécifique à cette école :
   ```bash
   docker compose ps
   curl -s https://<domaine>/api/v1/health
   curl -s https://<domaine>/api/v1/ready
   ```
   Si `/ready` renvoie `503`, l'incident est probablement une panne d'infrastructure globale
   (base, Redis, ou stockage) — traiter comme reprise après sinistre, voir
   [`DISASTER_RECOVERY.md`](../deployment/DISASTER_RECOVERY.md), pas ce runbook.
3. Si `/health`/`/ready` sont `200`, chercher dans les logs de la fenêtre de temps indiquée
   (`docker compose logs api --since ... --until ...`) toute ligne `ERROR`/`CRITICAL` — chaque
   ligne JSON porte `request_id`/`user_id`/`school_id` quand disponible, ce qui permet souvent de
   retrouver l'utilisateur concerné même sans `Request ID` fourni explicitement.
4. Reproduire l'action décrite avec un compte de test dans la même école si possible, avant de
   conclure à un problème propre à cette école.

**Quand escalader** : dès que `/ready` signale une dépendance en erreur, ou qu'aucune ligne de log
pertinente n'explique le symptôme décrit après une recherche raisonnable dans la fenêtre de temps
indiquée.

**Ne pas faire** : ne jamais annoncer une cause à l'école avant de l'avoir réellement vérifiée dans
les logs — un diagnostic annoncé puis démenti nuit plus à la confiance qu'un délai de réponse.

## Limites connues de ce runbook

Ce document couvre les six scénarios ci-dessus, choisis parce qu'ils correspondent aux domaines
métier les plus susceptibles de générer un signalement pendant un pilote (authentification,
visibilité de données, import, bulletins, paiements, signalement générique). Il ne couvre pas :
- Les scénarios de perte d'infrastructure (conteneur/base/stockage/Redis) — voir
  `DISASTER_RECOVERY.md`.
- Un incident touchant les notifications/annonces ou la présence — non encore rencontré en usage
  réel au moment de la rédaction de ce document ; à compléter dès qu'un premier cas réel se
  présente, plutôt que d'inventer une procédure non éprouvée.
