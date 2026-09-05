# PHASE 11 IMPLEMENTATION REPORT — Notification email au parent (bulletin publié)

## 1. Objectif

Lorsqu'un bulletin est publié, informer par email les tuteurs de l'élève qui disposent d'une
adresse email enregistrée — premier mécanisme de réengagement parent, réutilisant exclusivement
l'infrastructure email construite en Phase 9.

## 2. Workflow de publication

Point de déclenchement unique, inchangé au niveau de son contrat : `POST
/api/v1/report-cards/{id}/publish` (`report_cards/router.py::publish_report_card`). Aucun autre
chemin du code ne fait passer un bulletin à `PUBLISHED` — vérifié par lecture complète du
module (`generate_report_cards_for_class` ne fait au contraire que remettre `published_at` à
`None` lors d'une régénération).

## 3. Déclenchement email

Uniquement à l'intérieur de `publish_report_card`, et seulement si le bulletin **n'était pas
déjà publié** avant cet appel (voir §6). Aucun email n'est envoyé pour : une génération/
régénération (statut `DRAFT`), une simple consultation, un téléchargement PDF, ou tout autre
événement — vérifié réellement (tests §14, items 5 et 11).

## 4. Destinataires

Pour l'élève du bulletin : `StudentGuardian` (filtré par `student_id` **et** `school_id` du
bulletin — jamais de recherche globale) → `Guardian` correspondants → uniquement ceux dont
`email IS NOT NULL`. Chaque tuteur avec email reçoit son propre email ; un tuteur sans email
n'en reçoit aucun ; plusieurs tuteurs avec email reçoivent chacun le leur. Vérifié réellement
(tests §14, items 1-4, 9).

## 5. Contenu de l'email

```
Objet : Bulletin disponible — {prénom} {nom de l'élève}

Bonjour {nom complet du tuteur},

Le bulletin de {prénom} {nom de l'élève} pour la période {nom du terme} vient d'être publié.

Connectez-vous à l'application mobile EduSphere pour le consulter.

— EduSphere
```

Aucune note, moyenne, classement, appréciation, code de vérification ni contenu du bulletin —
vérifié réellement (test §14 item 13/14). **Aucun lien cliquable inclus** : voir §"URL" ci-dessous.

### URL — décision et justification

Aucun lien direct n'a été inclus, par choix délibéré et non par omission. Le portail parent
d'EduSphere est **mobile uniquement** (Phase 7) — le rôle `PARENT` ne possède aucune permission
RBAC (`PARENT: []`), donc un lien vers l'application web (`(app)/page.tsx`, le dashboard admin
de la Phase 10) renverrait un **403** à tout parent qui cliquerait dessus : ce serait une
expérience cassée, pas un point d'entrée utile. La seule autre page web pertinente,
`/verify/{code}` (Phase 5), est une page publique d'authenticité de bulletin papier qui affiche
déjà moyenne/rang/statut — y renvoyer depuis cet email contredirait directement la consigne de
ne jamais inclure ces informations. Aucune infrastructure de lien profond (deep link) vers
l'application mobile Expo n'existe. Le texte invite donc explicitement le parent à ouvrir
l'application mobile, sans URL — cohérent avec la consigne "utiliser le point d'entrée parent
existant plutôt que créer une nouvelle fonctionnalité de navigation" : aucun point d'entrée web
approprié n'existe réellement pour ce rôle.

## 6. Comportement best-effort

`send_email_best_effort` (Phase 9, inchangé) ne lève jamais — un échec d'envoi (panne du
fournisseur, adresse invalide côté serveur SMTP, etc.) est capturé et journalisé, jamais
propagé. Vérifié réellement (test §14 item 8) : la publication renvoie `200` avec
`status: "PUBLISHED"` même quand le fournisseur d'email échoue systématiquement.

## 7. Gestion des erreurs

Toute exception dans l'envoi est absorbée par `send_email_best_effort` (déjà en place, Phase 9)
— rien de nouveau à ajouter à ce niveau. Le message journalisé (`logger.warning`) contient
uniquement l'adresse email destinataire et le nom du fournisseur configuré — jamais de mot de
passe, jeton, JWT, ni contenu du bulletin.

## 8. Sécurité

- **Isolation tenant/école** : la requête des tuteurs filtre explicitement par
  `StudentGuardian.student_id` **et** `StudentGuardian.school_id` égal à ceux du bulletin —
  jamais de recherche globale. Vérifié réellement (test §14 item 9) : deux écoles avec un
  bulletin chacune, aucune fuite croisée dans le contenu des emails envoyés.
- **Absence de données sensibles** : ni note, ni moyenne, ni classement, ni appréciation, ni
  code de vérification, ni PDF (pas de pièce jointe) — vérifié réellement.
- **Logs** : aucun secret, jeton ou donnée personnelle sensible journalisé au-delà de l'adresse
  email destinataire (déjà le comportement de `send_email_best_effort`, inchangé).
- **URL** : aucune URL sensible ou capable de fuiter des données incluse (voir §5).

## 9. Isolation tenant — détail technique important (découverte pendant l'implémentation)

**Ce projet applique Row Level Security PostgreSQL avec un contexte posé par `SET LOCAL`, lié à
la transaction courante — ce contexte expire au `COMMIT`.** La première version du code lisait
les tuteurs **après** `await db.commit()` (par analogie avec le principe "l'envoi doit se faire
après la publication déjà durable") : **tous les tests échouaient avec zéro email envoyé**, la
requête `SELECT` s'exécutant sans contexte RLS actif ne voyait plus aucune ligne. C'est
exactement le même piège déjà documenté ailleurs dans ce dépôt (`auth/service.py::register`,
commentaire "refresh() AVANT commit").

**Correction appliquée** : la fonction a été scindée en deux étapes distinctes —
`prepare_report_card_published_notifications` (lecture DB, doit s'exécuter **avant** le
commit, pendant que le contexte RLS est encore actif, retourne les emails déjà entièrement
composés) et `send_report_card_published_notifications` (envoi réseau pur, aucun accès DB,
s'exécute **après** le commit). Cela satisfait simultanément les deux exigences : les données
sont lues correctement (RLS actif) ET un échec d'envoi ne peut jamais affecter une transaction
déjà validée (le commit a eu lieu avant toute tentative réseau).

## 10. Fichiers créés

- `apps/api/tests/test_report_cards_notifications.py`

## 11. Fichiers modifiés

- `apps/api/app/modules/report_cards/service.py` — ajout de
  `prepare_report_card_published_notifications` et `send_report_card_published_notifications`.
- `apps/api/app/modules/report_cards/router.py` — `publish_report_card` : garde d'idempotence
  (`was_already_published`), lecture des destinataires avant le commit, envoi après.

Aucun autre fichier `apps/api`, `apps/web`, `apps/mobile`, dashboard, wizard, auth, ou
rate-limiting n'a été modifié.

## 12. Migration

**Aucune.** Aucune nouvelle table, aucune nouvelle colonne — `Guardian.email`,
`StudentGuardian`, `ReportCard.published_at` existaient déjà (Phases 3 et 5). `alembic current`
confirmé à `0008 (head)`, inchangé.

## 13. Dépendances

**Aucune nouvelle.** Réutilisation stricte d'`EmailProvider`/`send_email_best_effort`
(`app/core/email.py`, Phase 9) — aucun SMTP direct, aucun SDK, aucune queue.

## 14. Tests

**`apps/api/tests/test_report_cards_notifications.py` — 11 tests, exécutés réellement (API +
Postgres + Redis réels du docker-compose, `LocalEmailProvider` isolée par `tmp_path`, aucun
mock du backend) :**

1. `test_publish_notifies_single_guardian_with_email` — un tuteur avec email.
2. `test_publish_notifies_multiple_guardians_with_email` — plusieurs tuteurs avec email.
3. `test_publish_sends_nothing_for_guardian_without_email` — tuteur sans email.
4. `test_publish_notifies_only_guardians_with_email` — mix avec/sans email.
5. `test_publish_with_no_guardian_succeeds_without_email` — aucun tuteur.
6/7/8. `test_publish_succeeds_even_when_email_provider_fails` — panne du fournisseur, la
   publication réussit malgré tout (best-effort).
9/10. `test_publish_never_notifies_guardians_of_another_school` — isolation tenant/école.
11. `test_generating_without_publishing_sends_no_email` — bulletin non publié → aucun email.
12. `test_email_sent_to_correct_recipient_address` — bon destinataire.
13/14. `test_email_content_is_minimal_and_never_contains_sensitive_data` — contenu minimal,
   absence de données sensibles.
15. `test_republishing_already_published_report_card_does_not_resend_email` — republication
    (aucun second envoi) puis régénération+republication (nouvel envoi légitime, contenu changé).

## 15. Résultats pytest

**146 passed**, 0 failed (135 précédents + 11 nouveaux), 2 warnings pré-existants sans rapport
avec cette phase (158.74s).

## 16. Résultats ruff

`All checks passed!`

## 17. Résultats mypy

`Success: no issues found in 70 source files` (inchangé — aucun nouveau fichier sous `app/`).

## 18. Playwright

**Aucun nouveau test E2E ajouté — limite documentée, pas contournée.** `LocalEmailProvider`
écrit sur le système de fichiers du conteneur `api`, non observable depuis le navigateur/test
runner Playwright ; aucun endpoint ne renvoie d'indicateur "email envoyé" (contrairement à
`dev_token`/`dev_reset_token` utilisés dans les phases précédentes pour piloter un flux réel).
Ajouter un tel indicateur aurait été un changement d'API hors périmètre. Conformément à la
consigne ("sinon, ajouter un test d'intégration backend suffisamment réaliste et documenter la
limite E2E"), la couverture réelle repose sur les 11 tests backend (§14), qui exercent le vrai
flux HTTP de bout en bout (publication réelle → email réellement "envoyé" via
`LocalEmailProvider` → fichier réellement vérifié).

Suites Playwright existantes réexécutées par prudence (aucune n'exerçait déjà la publication de
bulletin, donc aucune régression attendue ni trouvée) : **19/19** (`admin-onboarding` 3/3,
`dashboard` 3/3, `password-reset` 4/4, `setup-wizard` 6/6, `smoke` 3/3).

## 19. Build

Aucun fichier frontend modifié — build web non nécessaire pour cette phase.

## 20. Limites

- **Idempotence non absolue** : le garde-fou (`published_at` déjà renseigné) protège contre un
  double-appel direct de `/publish` sur le même bulletin, mais pas contre deux requêtes HTTP
  strictement concurrentes arrivant avant que la première n'ait committé (fenêtre de course
  théorique, très étroite en pratique pour une action manuelle d'administrateur). Une garantie
  parfaite exigerait soit une contrainte DB dédiée, soit un verrou explicite — hors périmètre
  (pas de nouvelle table/migration demandée), documenté ici plutôt que corrigé.
- **Pas d'E2E navigateur réel** (voir §18) — limite architecturale, pas un renoncement.
- **`LocalEmailProvider` en environnement actuel** : aucun email n'est réellement envoyé à une
  vraie boîte mail dans cet environnement de développement — voir §"EmailProvider" en sortie
  finale.
- **Volume** : best-effort séquentiel, un envoi réseau par tuteur — raisonnable au volume
  observé (quelques tuteurs par élève) ; aucune optimisation prématurée (queue, parallélisation)
  n'a été ajoutée, conformément à la consigne.

## 21. Discovered / Deferred

Rien découvert pendant cette implémentation ne relève de queue, préférences de notification,
historique, notification in-app, SMS ou push — tous restent hors périmètre, non implémentés,
conformément à la consigne. Le seul élément réellement découvert (§9, l'ordonnancement RLS/
commit) a été corrigé dans le périmètre même de cette phase, pas différé, car il s'agissait d'un
bug bloquant la fonctionnalité elle-même, pas d'un sujet hors périmètre.

## 22. Critères d'acceptation

| Critère | Statut |
|---|---|
| Publier un bulletin envoie réellement un email à chaque tuteur avec adresse enregistrée | ✅ Vérifié réellement |
| Un tuteur sans email n'entraîne ni erreur ni envoi | ✅ Vérifié réellement |
| Une panne du fournisseur n'empêche jamais la publication de réussir | ✅ Vérifié réellement |
| Aucune donnée sensible du bulletin dans l'email | ✅ Vérifié réellement |
| Isolation tenant/école respectée | ✅ Vérifiée réellement |
| Aucune régression | ✅ 146/146 pytest, 19/19 Playwright, ruff/mypy propres |
| Aucune migration, aucune nouvelle dépendance | ✅ |
| Aucun nouvel endpoint | ✅ |

## 23. Verdict

**GO**

Le mécanisme fonctionne réellement de bout en bout, réutilise exclusivement l'infrastructure
Phase 9, sans nouvelle table, endpoint, dépendance ou migration. Un bug réel et bloquant
(ordonnancement RLS/commit) a été découvert et corrigé pendant l'implémentation elle-même — pas
différé, puisqu'il empêchait la fonctionnalité approuvée de fonctionner du tout.

---

PHASE 11 IMPLEMENTATION COMPLETE

Implemented:
Notification email — bulletin publié

Recipients:
Tous les Guardian liés à l'élève du bulletin (via StudentGuardian, scopé school_id/organization_id) disposant d'un email non nul — un envoi par tuteur, jamais de recherche globale

Migration:
NO

Dependencies:
Aucune (EmailProvider existant, Phase 9)

Tests:
pytest 146/146 (135 précédents + 11 nouveaux) — ruff clean — mypy clean (70 fichiers)

Playwright:
19/19 (suites existantes, non-régression) — aucun nouveau test E2E (limite architecturale documentée §18, couverte par 11 tests d'intégration backend réels à la place)

Build:
Non applicable (aucun fichier frontend modifié)

EmailProvider:
local (LocalEmailProvider) dans cet environnement — aucun email n'est réellement envoyé à une vraie boîte mail ici, seulement écrit sur disque pour vérification

Best effort:
OK — vérifié réellement : la publication réussit même quand l'envoi échoue systématiquement

Status:
GO

WAITING FOR VALIDATION
