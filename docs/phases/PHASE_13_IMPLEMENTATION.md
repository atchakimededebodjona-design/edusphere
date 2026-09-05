# PHASE 13 IMPLEMENTATION REPORT

Date : 2026-09-04
Périmètre : `apps/api` uniquement — aucun fichier web ou mobile modifié.

## 1. Objectif

Corriger les deux vulnérabilités HIGH identifiées lors du premier audit sécurité dédié
(Phase 13 Discovery) : une traversée de chemin dans l'upload de fichiers, et un canal de fuite
temporelle sur `/auth/login` et `/auth/forgot-password`. Ne pas traiter les findings MEDIUM
(hors nécessité directe), ne démarrer aucune nouvelle fonctionnalité, aucune migration, aucune
nouvelle dépendance.

## 2. Vulnérabilités traitées

### HIGH #1 — Path Traversal

- **Cause** : `LocalStorageProvider._resolve()` (`app/core/storage.py`) construisait le chemin
  final par simple `self._base_path / path`, sans jamais vérifier que le résultat restait à
  l'intérieur du répertoire de stockage. `pathlib` ne filtre rien : ni les séquences `..`, ni le
  cas où `path` se trouve être un chemin absolu (l'opérateur `/` ignore alors silencieusement
  `self._base_path` et renvoie directement ce chemin absolu).
- **Fichier/fonction** : `app/core/storage.py::LocalStorageProvider._resolve` (partagée par
  `upload`/`download`/`delete`) ; trois appelants construisaient `path` à partir d'un nom de
  fichier fourni par le client sans le nettoyer : `app/modules/students/router.py:187` (photo),
  `app/modules/students/router.py:222` (documents), `app/modules/schools/router.py:109` (logo).
- **Vecteur** : un utilisateur authentifié disposant de `students.manage` (dont le rôle `STAFF`)
  ou de la permission de gestion d'école pouvait soumettre un fichier via ces trois endpoints avec
  un `filename` multipart contenant des séquences `../` (ou un chemin absolu), pour tenter de
  faire écrire le contenu du fichier en dehors du répertoire de stockage prévu.
- **Impact** : écriture arbitraire potentielle sur le système de fichiers du conteneur `api`,
  dans la limite des permissions du processus — confirmé comme un vecteur réel par l'audit
  dédié, pas seulement théorique (voir §3 pour la démonstration).
- **Correction** (deux couches, comme demandé — pas seulement au niveau des endpoints déjà
  identifiés) :
  1. **Couche autorité** : `LocalStorageProvider._resolve()` résout désormais réellement le
     chemin final (`.resolve()`) puis vérifie qu'il reste `is_relative_to(self._base_path)` ;
     sinon elle lève `StoragePathError` (nouvelle exception, `ValueError`). Cette vérification
     s'applique à `upload`, `download` et `delete` — donc à tout appelant présent ou futur de
     l'abstraction, pas seulement aux trois endpoints connus. `self._base_path` est lui-même
     résolu une fois à l'initialisation (`Path(base_path).resolve()`), pour que la comparaison
     soit fiable même si le chemin de base contient des liens symboliques ou est relatif.
  2. **Couche hygiène (défense en profondeur)** : nouvelle fonction `safe_filename()` dans
     `app/core/storage.py`, utilisée aux trois points d'upload — réduit le nom de fichier fourni
     par le client à son dernier composant (ni `/` ni `\` conservés, `.`/`..`/vide rejetés au
     profit d'un nom de repli `"file"`). Empêche qu'un nom de fichier contenant des séparateurs
     ne crée des sous-dossiers inattendus, en plus de réduire la probabilité d'atteindre la
     couche 1 en pratique.
- **Protection finale** : après ce correctif, un nom de fichier hostile soumis à l'un des trois
  endpoints est neutralisé silencieusement (l'upload réussit normalement, avec un nom de fichier
  assaini) ; toute tentative de faire résoudre un chemin hors du répertoire de stockage — par
  n'importe quel appelant de `StorageProvider`, pas seulement ces trois endpoints — est rejetée
  par une exception dédiée. Aucun changement de format pour les fichiers déjà stockés
  (l'environnement de développement ne contenait que des fichiers de test).

### HIGH #2 — Timing Leak Login

- **Cause** : `app/modules/auth/service.py::authenticate()` évaluait
  `if user is None or not user.is_active or not verify_password(...)`. L'évaluation
  court-circuitée de `or` fait que `verify_password` (bcrypt, coût délibérément élevé) n'était
  invoqué QUE si le compte existait et était actif — un compte inexistant ou désactivé répondait
  donc nettement plus vite qu'un compte actif avec un mauvais mot de passe.
- **Fichier/fonction** : `app/modules/auth/service.py::authenticate`.
- **Comportement observé (avant correctif)** : trois branches de coût différent — (A) compte
  inexistant : une requête SQL, aucun bcrypt ; (B) compte existant mais désactivé : idem, aucun
  bcrypt ; (C) compte actif, mot de passe incorrect : une requête SQL + un bcrypt complet. La
  réponse HTTP était identique (401, message générique) dans les trois cas, mais leur latence ne
  l'était pas.
- **Correction** : un hash bcrypt factice (`_DUMMY_PASSWORD_HASH`, précalculé une seule fois au
  chargement du module) est désormais vérifié dans les branches (A) et (B), avant de lever la
  même exception 401 générique. Le coût bcrypt est donc payé dans tous les cas où
  l'authentification échoue, qu'un compte existe ou non. Aucune donnée de l'utilisateur réel
  n'est utilisée dans cette vérification factice.
- **Limites** : ce correctif équilibre le coût **CPU** (bcrypt), qui était l'écart dominant et le
  plus facilement mesurable à distance. Il n'élimine pas d'éventuels écarts de latence réseau ou
  d'infrastructure plus fins (temps de requête SQL selon l'état du cache, la charge du serveur,
  etc.) — un canal de fuite temporelle n'est jamais prouvé "impossible" par une seule mesure ou un
  seul correctif ; ce qui est démontré ici (voir §3) est la **parité du nombre d'opérations
  coûteuses exécutées**, pas une égalité de latence mesurée en conditions réelles.

### HIGH #3 — Timing Leak Forgot Password

- **Cause** : `app/modules/auth/service.py::request_password_reset()` retournait immédiatement
  (`return None`) si l'email ne correspondait à aucun compte, avant toute génération de token,
  écriture en base, ou tentative d'envoi d'email — contre un chemin "compte existant" qui exécute
  ces trois opérations, dont potentiellement un appel réseau SMTP (`SmtpEmailProvider`, coût
  variable et possiblement élevé).
- **Fichier/fonction** : `app/modules/auth/service.py::request_password_reset`.
- **Comportement observé (avant correctif)** : email inexistant → retour quasi immédiat ; email
  existant → génération de token + hachage + `INSERT` + `COMMIT` + envoi d'email attendu avant la
  réponse. Réponse HTTP identique dans les deux cas (202, `dev_token` généraliste), latence non
  identique.
- **Correction** : pour un email inexistant, un travail équivalent de génération + hachage de
  token (`generate_opaque_token()` + `hash_opaque_token()`) est désormais exécuté avant de
  retourner — sans écriture en base ni envoi d'email (voir "Limites" et §8 de la consigne : ne
  jamais envoyer d'email supplémentaire ni créer de ligne pour un compte inexistant).
- **Limites — assumées et documentées, pas corrigées ici** : le facteur de latence dominant
  restant — l'écriture en base (`INSERT`+`COMMIT`) et surtout l'envoi d'email potentiellement
  synchrone vers un serveur SMTP externe — n'est **pas** équilibré par ce correctif. L'équilibrer
  proprement demanderait soit un délai artificiel disproportionné sur toutes les requêtes (proscrit
  explicitement par la consigne de cette phase), soit une file d'attente différée pour l'envoi
  d'email (queue/worker — également proscrit explicitement, aucun besoin démontré). Ce résidu
  est donc laissé en l'état, mitigé en pratique par la limitation de débit déjà en place depuis la
  Phase 10.1 (3 tentatives / 15 minutes par email), qui borne fortement le nombre d'échantillons
  temporels qu'un attaquant peut collecter. Documenté comme dette résiduelle explicite, pas comme
  résolu.

## 3. Tests de sécurité

Tous les tests ci-dessous ont été **réellement exécutés** dans le conteneur `api`
(`pytest -q tests/test_storage_security.py tests/test_auth_timing.py`) — voir §4 pour la sortie
complète. 21 tests, tous passés.

| Test | Résultat |
|---|---|
| Upload normal | PASS — `test_legitimate_filename_upload_is_unaffected` : nom de fichier normal inchangé, comportement identique à avant la phase |
| `../` | PASS — `test_local_storage_provider_rejects_any_path_resolving_outside_base[relative-traversal]` (unitaire, `StoragePathError` levée) + `test_student_photo_upload_with_traversal_filename_stays_contained` (bout en bout via l'endpoint réel, upload réussit avec nom assaini, fichier confiné) |
| `..\` | PASS — `test_local_storage_provider_windows_style_path_stays_contained_on_this_platform` (unitaire) + `test_school_logo_upload_with_traversal_filename_stays_contained` (bout en bout) — **note de véracité** : `\` n'est pas un séparateur sous POSIX (environnement réel de ce backend) ; le test vérifie que la chaîne reste confinée en tant que nom littéral, pas un contournement d'un vrai séparateur Windows |
| Absolute Unix | PASS — `test_local_storage_provider_rejects_any_path_resolving_outside_base[absolute-unix]` (unitaire, `/etc/passwd`) + `test_student_document_upload_with_absolute_unix_filename_stays_contained` (bout en bout) |
| Absolute Windows | PASS avec réserve explicite — même test unitaire `..._windows_style_path_stays_contained_on_this_platform` : le confinement est vérifié et tient, mais **ce n'est pas une validation sous un véritable interpréteur Windows** (indisponible dans cet environnement) ; sur POSIX, une chaîne `"C:\\..."` n'est de toute façon jamais reconnue comme un chemin absolu par `pathlib`, elle est donc intrinsèquement inoffensive ici — documenté honnêtement plutôt que présenté comme une preuve plus forte qu'elle ne l'est |
| Multi-level traversal | PASS — `test_local_storage_provider_rejects_any_path_resolving_outside_base[multi-level-traversal]` (20 niveaux de `../`) |
| School isolation | PASS — `test_school_isolation_still_enforced_on_student_photo` : un admin d'une autre école reçoit 404 sur la photo d'un élève qui n'est pas le sien |
| Organization isolation | PASS — `test_organization_isolation_still_enforced_on_student_photo` : même garantie entre deux organisations distinctes |
| Login unknown user | PASS — `test_login_unknown_email_and_wrong_password_return_identical_response` (réponse identique) + `test_login_unknown_and_wrong_password_perform_the_same_number_of_bcrypt_verifications` (1 appel `verify_password`, contre 0 avant le correctif) |
| Login wrong password | PASS — mêmes tests que ci-dessus, branche symétrique (1 appel `verify_password`, inchangé par rapport à avant) |
| Login valid | PASS — `test_login_valid_credentials_still_authenticate` : non-régression du chemin nominal |
| Forgot password unknown | PASS — `test_forgot_password_unknown_and_known_email_return_identical_response_shape` + `test_forgot_password_unknown_and_known_email_perform_the_same_number_of_token_generations` (1 appel `generate_opaque_token`, contre 0 avant le correctif) |
| Forgot password known | PASS — mêmes tests, branche symétrique + `test_forgot_password_rate_limiting_still_works` (non-régression Phase 10.1) |

Couverture additionnelle non listée dans le tableau imposé mais ajoutée pour la robustesse du
correctif : `safe_filename()` avec nom vide/`None`/`"."`/`".."` (repli sur `"file"`),
roundtrip upload/download normal sur `LocalStorageProvider` directement.

**Ce que ces tests prouvent, et ce qu'ils ne prouvent pas** (règle de vérité) : ils démontrent que
(a) aucune tentative de traversée testée ne fait sortir le chemin résolu du répertoire de
stockage, (b) le nombre d'opérations coûteuses (bcrypt, génération de token) est désormais
identique entre "compte inexistant" et "compte existant avec échec", et (c) aucune régression
fonctionnelle n'a été introduite. Ils ne prouvent PAS l'absence mathématique de tout canal
temporel resurgissant à un niveau plus fin (réseau, OS, cache) — ce point est explicitement
documenté en §2 (HIGH #2) et §9, jamais présenté comme "résolu définitivement".

## 4. Régression

Exécuté réellement dans le conteneur `api` :

```
pytest -q
167 passed, 2 warnings in 227.95s (0:03:47)
```

167 = 146 tests déjà existants après Phase 11/12 + 21 nouveaux tests de sécurité (Phase 13).
Zéro échec, zéro régression.

```
ruff check .
All checks passed!
```

```
mypy app
Success: no issues found in 70 source files
```

`alembic current` → `0008 (head)`, inchangé (aucune migration créée). `docker compose ps` → les
4 conteneurs actifs, `db`/`redis` toujours `(healthy)`, `api`/`web` toujours sans healthcheck
Docker (état inchangé, hors périmètre de cette phase).

Aucun fichier `apps/web` ni `apps/mobile` modifié — non applicable de lancer un build front-end ;
confirmé par la liste exacte des fichiers touchés (§8).

## 5. Findings MEDIUM non traités

Conformément à la consigne, laissés explicitement pour une phase future (dette documentée, pas
oubliée) :

- `organizations` sans politique RLS — aucun contournement exploitable trouvé, deuxième ligne de
  défense absente.
- `IntegrityError` non interceptée sur 6 endpoints de création (`create_academic_term`,
  `create_assessment`, `create_session`, `create_guardian`, `create_or_attach_user`,
  `generate_report_cards_for_class`) — 500 opaque au lieu de 409 propre.
- Absence de rate limiting sur `/auth/register`, `/auth/refresh`, et
  `GET /report-cards/verify/{code}`.
- Absence de détection de réutilisation de refresh token / de révocation en cascade d'une famille
  de sessions.
- Modification de notes possible sans garde-fou après publication d'un bulletin déjà envoyé par
  email au tuteur.
- `GET /roles`/`GET /permissions` toujours accessibles sans vérification de permission dédiée.
- Pas de plafond absolu de durée de session (rolling refresh 30 jours).
- Emails loggés en clair sur échec d'envoi (`core/email.py`).
- Git/CI et observabilité — dette future, non traitée ici (aucune dépendance bloquante découverte
  qui aurait justifié une exception).

Aucune exception au périmètre n'a été nécessaire : aucun des correctifs HIGH n'a naturellement
recoupé l'un de ces points.

## 6. Migration

Confirmé : **aucune migration créée**. `alembic current` reste à `0008 (head)` avant et après
cette phase. Aucun modèle SQLAlchemy modifié.

## 7. Dependencies

Confirmé : **aucune nouvelle dépendance**. `requirements.txt` et `requirements-dev.txt` non
modifiés. Le correctif de traversée de chemin utilise uniquement `pathlib` (bibliothèque
standard, déjà utilisée) ; le correctif de timing utilise les fonctions déjà présentes
(`hash_password`, `verify_password`, `generate_opaque_token`, `hash_opaque_token` de
`app/core/security.py`).

## 8. Fichiers modifiés

Modifiés :
- `apps/api/app/core/storage.py`
- `apps/api/app/modules/students/router.py`
- `apps/api/app/modules/schools/router.py`
- `apps/api/app/modules/auth/service.py`

Créés :
- `apps/api/tests/test_storage_security.py`
- `apps/api/tests/test_auth_timing.py`

Aucun autre fichier du dépôt n'a été touché (aucun fichier `apps/web`, `apps/mobile`, aucune
migration, aucun fichier Docker/CI/config).

## 9. Sécurité résiduelle

- Le résidu de latence sur `/auth/forgot-password` (écriture en base + envoi d'email non
  équilibrés) reste réel — mitigé par le rate limiting existant (Phase 10.1), pas éliminé. Une
  correction complète nécessiterait une architecture d'envoi différé, explicitement hors
  périmètre.
- Les six findings MEDIUM et trois findings LOW listés en §5 restent ouverts, avec le même niveau
  de risque qu'évalué en Phase 13 Discovery — aucun n'a été aggravé ni amélioré par ce correctif.
- La protection de traversée de chemin repose sur `Path.resolve()` + `is_relative_to()` : robuste
  contre toutes les variantes testées dans cet environnement (POSIX), mais n'a pas pu être
  vérifiée sous un système de fichiers différent (Windows réel, ou un système avec une sémantique
  de liens symboliques inhabituelle) faute d'environnement disponible pour le faire — documenté
  plutôt que supposé équivalent.
- Aucune vulnérabilité HIGH ou CRITICAL connue ne reste ouverte après cette phase, sur la base de
  l'audit dédié mené en Phase 13 Discovery (qui n'en avait identifié que deux, toutes deux
  traitées ici).

## 10. Validation

GO
