# Phase 21 Discovery — Communications & Notifications

Discovery uniquement. Aucun code applicatif, aucune migration, aucune dépendance, aucun changement
Docker/.env, aucun commit, aucun push n'ont été produits pendant cette phase. Seul ce document a
été créé. Chaque affirmation distingue **PROUVÉ** (lecture réelle du code/tests) de **NON VÉRIFIÉ**
ou **ABSENT** (recherche réelle, aucun résultat).

> **Implémentée** — voir [`docs/phases/PHASE_21_IMPLEMENTATION.md`](PHASE_21_IMPLEMENTATION.md)
> pour le rapport d'implémentation réel (migration `0011`, modèle `Notification`, annonces,
> RLS par destinataire), verdict **GO**.

## 1. Executive Summary

EduSphere envoie déjà 4 emails transactionnels réels (mot de passe oublié, création de compte,
publication de bulletin, reçu de paiement) via `EmailProvider`, tous testés, tous best-effort. **Il
n'existe en revanche aucun concept de notification générique** : ni modèle `Notification`, ni
centre de notifications in-app, ni compteur non-lu, ni push, ni scheduler applicatif, ni annonce
scolaire — confirmé par grep exhaustif, résultat **ABSENT** sur chacun. La recommandation de la
Phase 19/20 Discovery (Communications en position 2, derrière la sécurité) est **revalidée** par
cet audit : aucun besoin plus urgent n'a émergé de la Phase 20 (qui a fermé exactement les 4 sujets
qu'elle ciblait, sans en ouvrir de nouveaux dans ce domaine).

**Recommandation** : **PHASE 21 = Communications & Notifications**, avec un MVP volontairement
étroit — un modèle `Notification` in-app unique (pas un `Announcement` séparé), des annonces
scolaires **in-app uniquement** (pas d'email de masse, pour éviter exactement le risque de
performance déjà réel avec la publication de bulletins), et l'ajout d'une notification in-app aux
2 événements qui ont déjà un email et un point d'entrée testé (bulletin publié, paiement enregistré)
— sans toucher à `EmailProvider`. Aucun scheduler introduit. Push/SMS/WhatsApp/préférences/rappels
d'échéance/notifications d'absence : documentés, hors périmètre MVP, avec la justification précise
de chaque report.

## 2. État réel

Confirmé avant tout audit : `HEAD` = `faa3754` (Phase 20), working tree propre au début de cette
Discovery, `origin/main` synchronisé (Phase 20 poussée et CI verte, selon l'énoncé). Phase 20 a
fermé exactement les 4 sujets qu'elle ciblait (rate limiting, RLS `organizations`, en-têtes/HTTPS,
traçabilité `StudentFee`) — aucune dette Phase 20 ne recoupe le domaine communications.

## 3. Audit Email

**`apps/api/app/core/email.py`** (lu intégralement) : `EmailProvider(ABC)` avec une seule méthode
`send(to, subject, body)`, deux implémentations — `LocalEmailProvider` (écrit chaque email en
fichier `.txt`, utilisé en dev/tests) et `SmtpEmailProvider` (`smtplib` standard, jamais activé en
pratique — **aucune livraison SMTP externe réelle n'a jamais été vérifiée**, PHASE_16/17/20
concordantes sur ce point). `send_email_best_effort()` est le point d'entrée unique utilisé par
tout le code métier : avale toute exception, journalise un warning, ne fait jamais échouer
l'appelant.

**Matrice des 4 emails réellement déclenchés aujourd'hui** :

| Email | Déclencheur | Destinataire | Contenu | Provider | Échec | Tests | Prod-ready |
|---|---|---|---|---|---|---|---|
| Réinitialisation mot de passe | `POST /auth/forgot-password` (`auth/service.py::request_password_reset`) | Email fourni, si un compte existe (jamais révélé sinon) | Lien `reset-password?token=...`, aucune donnée personnelle | `EmailProvider` (best-effort) | N'affecte jamais la réponse (toujours 202) | `test_forgot_password_rate_limit.py`, `test_auth.py` | Mécanisme oui, livraison réelle **NON VÉRIFIÉE** |
| Bienvenue / activation de compte | `POST /users` (`users/service.py::create_or_attach_user`, un nouvel email) | Le nouvel utilisateur (enseignant/staff/accountant/parent) | Lien `reset-password?token=...` pour définir le mot de passe | `EmailProvider` (best-effort) | N'affecte jamais la création du compte | Couvert indirectement (tous les tests utilisant `_create_user_with_role`/`_create_parent_user` dépendent de `dev_reset_token`, pas un test d'email dédié) | Mécanisme oui, livraison **NON VÉRIFIÉE** |
| Bulletin publié | `POST /report-cards/{id}/publish` (`report_cards/service.py::prepare_/send_report_card_published_notifications`) | Chaque `Guardian.email` non nul lié à l'élève, dans SON école uniquement | Nom élève + période, **jamais** moyenne/rang/appréciation/code de vérification (vérifié explicitement par test) | `EmailProvider` (best-effort, lu avant commit, envoyé après) | N'affecte jamais la publication | `test_report_cards_notifications.py` — **15 tests**, dont non-régression cross-école, échec provider, non-renvoi à la republication | Mécanisme prouvé à l'identique du besoin Phase 21 (patron directement réutilisable) |
| Reçu de paiement | `POST /payments` (`fees/service.py::_prepare_/send_payment_notifications`) | Chaque `Guardian.email` non nul lié à l'élève | Montant + numéro de reçu, invite à ouvrir l'app mobile (pas de pièce jointe, pas de lien direct — voir Phase 19 Discovery §26) | `EmailProvider` (best-effort, même séquence lecture-avant-commit/envoi-après-commit) | N'affecte jamais l'enregistrement du paiement | Couvert indirectement par `test_fees.py` (paiement réussi), **aucun test dédié au contenu de l'email** contrairement aux bulletins | Mécanisme identique au précédent, moins testé spécifiquement |

**Constat de doublon/incohérence** : les deux mécanismes de notification existants (bulletins,
paiements) sont du code dupliqué presque à l'identique (`_prepare_X_notifications` / `send_X_
notifications`, même requête `Guardian` JOIN `StudentGuardian`, même best-effort après commit) —
**opportunité de réutilisation directe pour Phase 21**, pas un défaut à corriger en soi (chaque
duplication a été un choix délibéré et documenté à l'époque, cohérent avec le style du projet).
**Aucun email non utilisé, aucun template incohérent** — les 4 corps de message sont du texte brut
simple généré en Python, pas de moteur de template partagé (report_cards utilise Jinja2, mais
uniquement pour le PDF du bulletin, jamais pour un email).

## 4. Audit Notifications

Recherche exhaustive (grep insensible à la casse, tout `apps/`) : `notification`, `Notification`,
`NotificationService`, `notification_preferences`, `unread`, `mark.?as.?read`, `push`, `FCM`,
`APNs`, `expo-notifications`, `in-app`. **Résultat : ABSENT sur tous les points sauf les 5 fichiers
déjà connus** (les deux paires prepare/send de §3 et leurs tests). Aucun modèle `Notification`,
aucune table, aucun centre in-app, aucun compteur non-lu, aucun mécanisme de "marquer comme lu".
Confirmé également : `apps/mobile/package.json` ne liste **aucune** dépendance push
(`expo-notifications` absent des `dependencies`) — pas même une fondation commencée.

## 5. Audit Events (événements métier)

| Événement | Statut | Preuve |
|---|---|---|
| Compte créé | **A — réellement existant** | `users/service.py::create_or_attach_user`, déclenche déjà un email |
| Mot de passe réinitialisé (demande) | **A** | `auth/service.py::request_password_reset` |
| Bulletin publié | **A** | `report_cards/router.py::publish_report_card` |
| Paiement enregistré | **A** | `fees/service.py::record_payment` |
| Note saisie | **B — implicite** | `grades/service.py::apply_results_and_recompute` recalcule moyennes/rangs mais ne notifie personne — aucun point d'accroche préparé |
| Élève créé | **B — implicite** | `students/router.py::create_student` existe, aucun événement ni notification associée |
| Présence marquée / élève absent | **B — implicite** | `attendance/service.py::upsert_records` existe, verrouillage de session existe (`locked`/`locked_at`/`locked_by`), mais **aucun** hook de notification — voir §14 |
| Frais ajusté (`StudentFee.updated_by`, Phase 20) | **B — implicite** | La donnée est tracée (qui, quand) mais rien n'en informe le parent |
| Échéance de paiement proche/dépassée | **C — inexistant** | Aucun job ne compare `StudentFee.due_date` à la date courante ; `fees/service.py::compute_fees_summary` calcule un `overdue_count` à la demande (lecture), jamais en tâche de fond |
| Annonce école | **C — inexistant** | Aucun modèle, aucune route |

## 6. Audit Scheduler

Grep exhaustif (`celery|APScheduler|RQ|BackgroundTasks|scheduler|worker`, tout `apps/api`) :
**ABSENT** — confirmé, aucun résultat pertinent (les seules occurrences du mot "scheduler"
concernent le Planificateur de tâches **Windows**, un mécanisme d'**exploitation** pour les
sauvegardes, Phase 15 — jamais invoqué par l'application elle-même). `.github/workflows/ci.yml`
audité : aucun déclencheur `schedule:` (cron GitHub Actions), seulement `push`/`pull_request`.
**FastAPI `BackgroundTasks`** n'est utilisé nulle part dans le code actuel (grep confirmé) — même
le best-effort email se fait de façon synchrone dans la requête (après le commit, mais toujours
dans le même cycle requête/réponse).

**Distinction demandée, confirmée** : le scheduler de backup (OS-level, Phase 15) n'a **aucun**
rapport avec un éventuel besoin applicatif — ce ne sont pas la même chose, et le premier n'apporte
rien au second.

**Réponse à la question centrale du §31** : **oui, Phase 21 peut fonctionner entièrement sans
scheduler**, à condition que le MVP se limite à des notifications déclenchées de façon synchrone
par un événement HTTP déjà existant (bulletin publié, paiement enregistré) — exactement le patron
déjà prouvé deux fois. Tout ce qui nécessite un déclenchement **différé** (rappel d'échéance,
"school digest" quotidien) nécessite un scheduler qui n'existe pas encore et **ne doit pas être
introduit dans cette phase** sans preuve d'un besoin qui ne peut pas attendre.

## 7. Audit Parent (mobile)

`apps/mobile/app/(parent)/children/[studentId].tsx` : 4 onglets (Présence, Notes, Bulletins, Frais
— ce dernier ajouté Phase 19). **Aucun onglet ou écran "Notifications" n'existe.** Aucun badge
non-lu, aucune navigation dédiée, aucun deep-link. Le parent découvre un bulletin publié ou un
paiement enregistré uniquement en ouvrant l'onglet concerné — l'email est aujourd'hui le seul
signal qui l'invite à le faire. Motif `useAsyncData`/`ScreenState` (Loading/Error) déjà établi et
directement réutilisable pour un futur écran de notifications.

## 8. Audit Teacher (mobile)

`apps/mobile/app/(teacher)/` : 5 écrans (`index`, `classes/[id]`, `attendance/[classId]`,
`assessments/[classSubjectId]`, `assessments/[id]/grades`) — confirmé en Phase 20 Discovery,
revérifié cohérent. **Aucune notification, aucun message admin→enseignant n'existe.** Un besoin
réel identifiable (ex. "la direction publie une annonce visible par tous les enseignants d'une
école") mais **aucune preuve d'urgence pilote** au-delà de l'hypothèse — à confirmer par les
écoles pilotes elles-mêmes, pas par supposition.

## 9. Audit Web Admin

`apps/web/components/app-shell/Nav.tsx` (lu intégralement, Phase 19) : `Tableau de bord, Mise en
place, École, Académique, Élèves, Présences, Notes, Bulletins, Frais scolaires, Paiements,
Utilisateurs`. **Aucune entrée "Communications"/"Annonces"/"Notifications".** Un centre de
communications complet (annonces + historique + destinataires + statut + aperçu, comme évoqué au
§24 de la commande) serait une construction neuve — non justifiée pour un MVP dont le besoin
prioritaire (§18/§19) est in-app, pas un outil de campagne.

## 10. Audit RBAC

`apps/api/app/modules/rbac/seed.py` (catalogue complet relu) : aucune permission
`notifications.*`/`announcements.*` n'existe. Précédent direct et pertinent : **`PARENT` ne détient
aucune permission RBAC** (`ROLE_PERMISSIONS["PARENT"] = []`) et pourtant reste correctement
scopé tenant — confirmé en relisant `users/service.py::create_or_attach_user`, qui crée bien une
ligne `UserRole(organization_id=school.organization_id, school_id=school.id)` pour **tout** rôle
attribué via `POST /users`, `PARENT` inclus. La permission RBAC (table `role_permissions`) et le
scope tenant (table `user_roles`) sont deux mécanismes indépendants — un rôle peut avoir un scope
tenant correct sans aucune permission. **Conséquence directe pour Phase 21** : "lire mes propres
notifications" ne nécessite **aucune** nouvelle permission (même patron que `GET /auth/me`,
`GET /auth/sessions` — auto-scopé par `current_user.id`, jamais par permission). Seule une action
de **création d'annonce** (diffusion vers plusieurs destinataires) justifierait une permission
nouvelle, ex. `announcements.manage`, à réserver à `SCHOOL_ADMIN`/`DIRECTOR` (cohérent avec qui
gère déjà `students.manage`/`fees.manage`) — **aucun rôle nouveau**, conforme à la consigne.

## 11. Audit RLS

29 tables ont RLS aujourd'hui (Phase 1 à 20, `organizations` incluse depuis la Phase 20). Motif
constant : `school_id` + `organization_id` dénormalisés, policy `{table}_tenant_isolation`
identique partout. Une éventuelle table `notifications` suivrait exactement ce motif — vérifié ci-
dessus (§10) que le contexte tenant d'un `PARENT` (`app.tenant_org_ids` via `apply_tenant_context`)
est correctement peuplé malgré l'absence de permissions, donc la policy standard fonctionnerait
sans adaptation pour ce rôle. **Aucune table `notifications` n'existe aujourd'hui** — rien à
auditer au-delà de la conformité au motif déjà établi.

## 12. Audit Security

Risques analysés (aucun code créé, analyse conceptuelle sur le modèle proposé §19) :
- **IDOR/cross-school/cross-org** : couvert par le motif RLS déjà systématique (§11) + un contrôle
  applicatif `recipient_user_id == current_user.id` sur toute lecture individuelle — même
  double-couche que partout ailleurs dans ce projet.
- **Email au mauvais tuteur** : déjà résolu par le code réutilisé (`Guardian` JOIN
  `StudentGuardian` scopé `school_id`, prouvé sans fuite cross-école par
  `test_publish_never_notifies_guardians_of_another_school`).
- **Données financières/sensibles dans un email** : principe déjà établi et testé
  (`test_email_content_is_minimal_and_never_contains_sensitive_data`) — à reconduire explicitement
  pour toute nouvelle notification (le corps annonce qu'un événement a eu lieu, jamais le détail
  sensible ; le détail reste consultable uniquement après authentification dans l'app).
- **Liens non authentifiés** : aucun des 4 emails actuels n'expose un lien donnant accès direct à
  une donnée protégée sans authentification (les liens de reset sont des jetons à usage unique
  courts, pas des liens de consultation) — à reconduire, ne jamais créer de lien de notification
  cliquable menant directement à une ressource protégée sans passer par le login.
- **XSS/contenu utilisateur** : pertinent uniquement si une annonce autorise un texte libre affiché
  ensuite dans le web/mobile — voir §26 : recommandation = texte brut échappé par le framework
  (React/React Native échappent déjà par défaut), **aucun rendu HTML/Markdown** au MVP, éliminant
  la classe de risque entièrement plutôt que la mitiger.
- **Énumération** : le motif 404 systématique du module `parent` (`_get_child_or_404`) est
  directement réutilisable pour toute notification individuelle.

## 13. Audit Finance notifications (Phase 19 revisité avec un regard sécurité)

Chaîne `StudentFee → Student → Guardian → User` déjà implémentée et testée
(`fees/service.py::_prepare_payment_notifications`) : jointure `Guardian` via `StudentGuardian`,
filtrée `school_id`, email envoyé uniquement si `Guardian.email is not None`. **Fiable pour
déclencher une notification** : l'événement (`record_payment` réussi) est atomique et déjà
transactionnellement sûr (Phase 19/20). **Rappels d'échéance/retard** : explicitement hors
périmètre — nécessitent un scheduler (§6, absent) pour comparer `due_date` à la date courante en
tâche de fond ; les inclure maintenant reviendrait à construire un scheduler juste pour ce besoin,
contraire à la consigne anti-sur-ingénierie. **Modification de frais (`StudentFee.updated_by`,
Phase 20)** : événement fiable et atomique, mais **aucune preuve de besoin pilote** exprimée
au-delà de l'hypothèse de la commande — candidat MVP possible mais pas prioritaire (voir §16/§19).

## 14. Audit Attendance notifications

`attendance/models.py` (migration 0007, relue) : `AttendanceSession` a `locked`/`locked_at`/
`locked_by` — un verrouillage explicite, distinct de la simple création. `AttendanceRecord` a
`status`/`justified`/`reason`, unique par `(session_id, student_id)`. **Aucun événement de
notification n'existe aujourd'hui à aucun de ces points.**

**Question de timing (§21 de la commande), réponse argumentée par l'audit** : notifier **dès la
saisie** (`upsert_records`) serait risqué — une classe de 30-50 élèves peut être corrigée plusieurs
fois avant verrouillage (l'enseignant coche, recoche, corrige une erreur) ; notifier à chaque
écriture produirait un spam réel et des notifications prématurées/erronées. Notifier **après
verrouillage** (`locked=true`) est la seule option cohérente avec le modèle existant : c'est le
seul point qui signifie "cette session est finalisée." **Mais aucun verrou n'est aujourd'hui
obligatoire avant qu'une session soit considérée complète** (confirmé : `locked` est optionnel,
aucune contrainte ne force son passage à `true`) — une notification purement basée sur le
verrouillage manquerait donc les écoles qui ne verrouillent jamais leurs sessions. **Conclusion :
un vrai design d'anti-spam/timing pour les absences reste à faire (pas juste à câbler un email) —
raison suffisante pour l'exclure du MVP Phase 21** plutôt que de le construire à la hâte.

## 15. Audit Performance

**Risque réel déjà existant, pas hypothétique** : `report_cards/router.py::publish_report_card`
et `fees/router.py::create_payment` envoient déjà leurs emails **de façon synchrone, dans la
requête HTTP, en boucle sur les tuteurs** — pour un bulletin, un seul élève donc 1-3 tuteurs typ.
(risque faible en pratique) ; mais **`generate_report_cards_for_class`** génère pour toute une
classe (jusqu'à 50 élèves), et si une future action "publier tous les bulletins de la classe"
existait, ce serait 50+ emails synchrones dans une seule requête — ce cas **n'existe pas encore**
(publication actuelle = un bulletin à la fois) mais illustre le risque exact que la commande
anticipe pour une annonce école entière. **Conclusion pour Phase 21** : une annonce touchant
potentiellement des centaines de destinataires ne doit **jamais** déclencher un envoi email
synchrone en boucle dans la requête HTTP — d'où la recommandation MVP de limiter les annonces à
l'in-app uniquement (écriture en masse Postgres, une seule requête `INSERT ... SELECT`, aucun
appel réseau bloquant) plutôt que d'introduire un mécanisme asynchrone qui n'existe nulle part
ailleurs dans le projet.

## 16. Candidats de Phase 21

| Candidat | Valeur pilote | Complexité | Dépendances | Risque | Urgence | Valeur commerciale | Extensibilité |
|---|---|---|---|---|---|---|---|
| A. Notifications in-app (modèle générique) | Haute | Faible-moyenne | Aucune nouvelle | Faible | Haute | Moyenne | Haute (base de tout le reste) |
| B. Annonces scolaires (in-app) | Haute | Faible (réutilise A) | A | Faible | Haute | Moyenne | Haute |
| C. Emails événementiels (déjà existants, étendus) | Moyenne (déjà fait pour 2 événements) | Très faible | EmailProvider (inchangé) | Faible | Moyenne | Faible | Haute |
| D. Préférences de notification | Faible (aucune demande observée) | Moyenne | A | Faible | Basse | Faible | Moyenne |
| E. Push notifications | Moyenne (valeur réelle mais future) | Haute (nouvelle infra device/token) | A, Expo | Moyenne | Basse | Moyenne | Haute si posé maintenant, mais prématuré |
| F. SMS | Moyenne en théorie (zones à faible usage app) | Haute (fournisseur, coût, couverture Togo non vérifiée) | Nouveau fournisseur externe | Moyenne-haute (coût, dépendance) | Basse | Moyenne | Basse (fournisseur figé) |
| G. WhatsApp | Faible à ce stade (aucune intégration API WhatsApp Business étudiée) | Haute | Nouveau fournisseur | Moyenne | Très basse | Inconnue | Basse |
| H. Messagerie/chat complet | Faible pour un MVP | Très haute | Beaucoup | Haute (scope creep) | Très basse | Faible | — (explicitement hors périmètre) |
| I. Rappels de paiement (échéance) | Moyenne | Moyenne-haute (nécessite scheduler) | Scheduler (absent) | Moyenne | Basse (déjà différé 2 fois) | Moyenne | Moyenne |
| J. Notifications d'absence | Haute en théorie | Moyenne-haute (anti-spam/timing non résolu, §14) | Design de timing à faire | Moyenne (spam réel) | Moyenne | Moyenne | Moyenne |

## 17. Matrice de scoring

Échelle 1-5. Colonnes : pilote / parent / enseignant / administration / commerciale / urgence /
facilité d'intégration / sécurité / extensibilité / coût opérationnel inverse (5 = coût quasi nul).

| Candidat | Pilote | Parent | Enseignant | Admin | Commercial | Urgence | Intégration | Sécurité | Extensibilité | Coût inv. | **Total /50** |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A. In-app | 5 | 4 | 3 | 4 | 3 | 5 | 5 | 4 | 5 | 5 | **43** |
| B. Annonces (in-app) | 4 | 4 | 3 | 5 | 3 | 4 | 4 | 4 | 4 | 5 | **40** |
| C. Emails événementiels étendus | 3 | 3 | 2 | 2 | 2 | 3 | 5 | 4 | 4 | 5 | **33** |
| I. Rappels de paiement | 3 | 3 | 1 | 3 | 3 | 2 | 2 | 3 | 3 | 2 | **25** |
| J. Notifications d'absence | 3 | 4 | 2 | 2 | 2 | 2 | 2 | 3 | 3 | 2 | **25** |
| D. Préférences | 1 | 2 | 1 | 1 | 1 | 1 | 3 | 4 | 3 | 3 | **20** |
| E. Push | 2 | 3 | 2 | 1 | 2 | 1 | 1 | 3 | 4 | 2 | **21** |
| F. SMS | 2 | 2 | 1 | 1 | 2 | 1 | 1 | 3 | 2 | 1 | **16** |
| G. WhatsApp | 1 | 2 | 1 | 1 | 1 | 1 | 1 | 3 | 2 | 1 | **14** |
| H. Chat complet | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 2 | 2 | 1 | **12** |

**A et B dominent nettement**, cohérent avec l'analyse qualitative — aucune pondération
artificielle, les scores reflètent directement les constats des §3-15.

## 18. Architecture recommandée

**Pas de `NotificationProvider`** calqué sur `StorageProvider`/`EmailProvider`/`PaymentProvider` —
et c'est un choix délibéré, pas un oubli. Ces trois abstractions existent parce qu'elles masquent
**un seul système externe interchangeable** derrière une interface étroite (un fichier, un email,
un paiement). "Notification" n'est pas un système unique : email, in-app, push et SMS ont des
adresses, des coûts, des formats et des modes d'échec radicalement différents — les unifier
derrière un `NotificationProvider.send()` générique produirait soit une interface qui fuit
(paramètres spécifiques à chaque canal) soit une fausse promesse d'interchangeabilité. Le projet a
d'ailleurs **déjà** la bonne réponse, utilisée deux fois avec succès : chaque module métier prépare
ses destinataires puis appelle le canal directement (`send_email_best_effort`) — un patron
"événement → préparation → canal(aux)", pas un dispatcher générique.

**Recommandation** : un nouveau module `app/modules/notifications/` (suivant la convention déjà
uniforme du projet), avec :
- `models.py` — un seul modèle `Notification` (voir §19), pas de modèle `Announcement` séparé (une
  annonce = plusieurs lignes `Notification`, une par destinataire, créées en une fois).
- `service.py` — `create_notifications_for_users(db, ..., user_ids: list[uuid.UUID])` : une
  fonction d'écriture en masse (un seul `INSERT`), appelée par n'importe quel module métier qui a
  déjà résolu sa liste de destinataires (report_cards, fees, plus tard attendance/announcements).
- `router.py` — `GET /notifications` (auto-scopé `recipient_user_id == current_user.id`, aucune
  permission requise, même patron que `/auth/me`), `PATCH /notifications/{id}/read`.
- Un futur canal (push, SMS) s'ajoute en créant SA propre fonction d'envoi (comme
  `send_email_best_effort` aujourd'hui), appelée en plus de `create_notifications_for_users` aux
  mêmes points d'appel — jamais un `channel` générique dans le modèle de données lui-même.

## 19. Modèle de données (minimal, après audit)

`Notification` : `id, organization_id, school_id, recipient_user_id (FK users, CASCADE), type
(String, ex. "report_card_published"/"payment_received"/"announcement"), title, body, created_at,
read_at (nullable)`. **Volontairement absents** : `channel`/`status` (aucune queue, aucun retry
n'existe nulle part dans ce projet pour justifier un état "queued/sent/failed" — une notification
in-app EST délivrée au moment où la ligne existe ; l'email associé reste best-effort et non tracé,
cohérent avec les 4 emails existants qui ne tracent rien non plus), `related_entity_id`/lien
profond (aucun besoin concret identifié pour le MVP — le contenu textuel suffit à orienter
l'utilisateur vers l'onglet concerné). RLS : motif standard `{table}_tenant_isolation`, confirmé
compatible avec le scope tenant d'un `PARENT` (§10/§11).

## 20. Préférences de notification

**Non nécessaires au MVP** — aucune preuve d'un besoin (aucune école pilote, aucun retour
utilisateur, le produit n'a pas encore d'utilisateur réel de notifications à préférer). Ajouter un
système de préférences maintenant serait construire pour une demande hypothétique. À réévaluer une
fois que des utilisateurs réels auront été exposés à au moins un canal.

## 21. Annonces vs Notifications

Tranché en §18/§19 : **un seul modèle**, pas deux. Une annonce est une notification dont la
création est un acte administratif explicite (fan-out immédiat vers tous les destinataires
ciblés) plutôt que la conséquence automatique d'un événement système — la distinction est dans
**qui déclenche la création**, pas dans la structure des données.

## 22. Anti-spam

Pertinent uniquement pour les candidats hors MVP (notifications d'absence — §14 — et toute
notification par élément individuel plutôt que par lot). Le MVP proposé (§16 A/B/C) ne présente
aucun risque de spam par construction : bulletins et paiements sont déjà des actions unitaires
(un événement = un petit nombre de destinataires), les annonces sont un acte explicite unique de
l'admin (une création = un lot, pas une répétition). Batching/déduplication/cooldown : **non
nécessaires maintenant**, à concevoir seulement si/quand les notifications d'absence sont
priorisées.

## 23. Retry / échec

`EmailProvider` reste best-effort sans retry ni queue (confirmé §3, comportement inchangé et
volontairement conservé). Une notification in-app n'a pas de mode d'échec réseau — c'est une
écriture Postgres classique dans la même transaction que l'événement métier (ou juste après,
suivant le même motif lecture-avant-commit déjà établi) : si elle échoue, elle échoue comme
n'importe quelle autre écriture métier, sans mécanisme spécial à inventer.

## 24. Observabilité

Minimum réellement nécessaire : `created_at` (déjà proposé) et `read_at` (déjà proposé) suffisent
à répondre à "combien de notifications non lues" et "quand a-t-elle été lue" — les deux seuls
besoins concrets identifiés (badge non-lu, historique). Pas de `sent_at`/`delivered_at` (n'aurait
de sens qu'avec un canal ayant un accusé de réception, aucun n'existe).

## 25. Sécurité — synthèse

Voir §12 pour le détail. Aucun risque nouveau non couvert par les patrons déjà en place
(RLS + contrôle applicatif + 404 anti-énumération + contenu minimal non sensible + pas de rendu
HTML/Markdown).

## 26. Contenu utilisateur (annonces)

Recommandation : **texte brut uniquement**, pas de HTML, pas de Markdown, pas d'éditeur riche.
React (web) et React Native (mobile) échappent le texte par défaut — aucun risque XSS si aucun
rendu HTML n'est jamais introduit. Limite de longueur raisonnable (ex. 2000 caractères, cohérent
avec les champs `note`/`Text` déjà utilisés ailleurs dans le projet, ex. `StudentFee.note`).

## 27. Pièces jointes

**Non nécessaires au MVP** — aucune demande identifiée. Si un besoin réel apparaît plus tard
(ex. joindre un règlement intérieur PDF à une annonce), `StorageProvider` est directement
réutilisable sans modification (même patron que les documents élèves/logos d'école) — mais
l'ajouter maintenant serait anticiper un besoin non prouvé.

## 28. Matrice des emails existants

Voir §3 (matrice complète). Résumé : 4 emails, tous best-effort, tous testés à des degrés divers
(bulletins = 15 tests dédiés incluant sécurité ; paiements = couverts indirectement seulement ;
compte créé/mot de passe = couverts par les tests d'auth existants, pas de test de contenu dédié).
**Aucun doublon fonctionnel, aucun email mort.**

## 29. Production readiness

Inchangé par rapport à Phase 20 : **B. PILOT READY**. Pour Communications spécifiquement :
mécanisme in-app 100% réalisable avec l'infrastructure actuelle (aucune dépendance externe) ; email
reste au même niveau que documenté depuis la Phase 16 (`EMAIL_PROVIDER=local` en dev, SMTP jamais
vérifié en livraison réelle) — ne pas présenter Communications comme "email production-ready" tant
que cette réserve historique n'est pas levée séparément.

## 30. Roadmap proposée (découle de l'audit, non imposée)

- **Phase 21 → Communications & Notifications (MVP in-app + 2 événements existants)** — cohérent
  avec ce document.
- Phase 22 → à déterminer après retour des écoles pilotes sur l'usage réel des notifications
  in-app (pourrait être notifications d'absence avec un vrai design anti-spam, ou Mobile Money
  foundations, ou Admissions — aucun signal suffisant aujourd'hui pour trancher par avance).
- Rappels d'échéance de paiement et push restent des candidats sérieux mais **dépendent tous deux
  d'une brique absente** (scheduler pour l'un, infra device/token pour l'autre) — à envisager
  ensemble si un scheduler minimal devient nécessaire pour plusieurs besoins à la fois, plutôt que
  d'en construire un pour un seul.

## 31. Questions nécessitant une décision humaine

1. Les annonces scolaires doivent-elles être visibles par **toute l'école** au MVP, ou faut-il
   déjà un ciblage par classe/niveau (plus de complexité, aucun besoin prouvé pour l'instant) ?
2. Confirme-t-on qu'**aucun email** n'est envoyé pour les annonces au MVP (in-app uniquement,
   pour la raison de performance du §15), ou est-ce un besoin produit non négociable dès
   maintenant ?
3. Le champ `type` de `Notification` doit-il rester une simple chaîne libre (le plus simple), ou
   faut-il dès maintenant une énumération fermée contrôlée côté base ?
4. Qui peut créer une annonce — uniquement `SCHOOL_ADMIN`/`DIRECTOR` (proposé §10), ou aussi
   `STAFF`/`TEACHER` pour des annonces limitées à leur classe ?
5. Le MVP doit-il inclure une notification in-app pour la **modification manuelle d'un frais**
   (`StudentFee.updated_by`, Phase 20) dès Phase 21, ou est-ce trop tôt sans retour pilote ?
6. Accepte-t-on de laisser les notifications d'absence et les rappels d'échéance explicitement
   hors périmètre de Phase 21 (tous deux nécessitant un travail de conception supplémentaire non
   fait ici), quitte à les proposer pour une phase ultérieure une fois un besoin réel confirmé ?

## 32. Risques

Risque principal identifié : introduire par erreur un envoi email de masse synchrone pour les
annonces (§15) — mitigé par la recommandation in-app-only du MVP. Risque secondaire : sur-
construire (préférences, push, SMS) sans demande réelle — mitigé par le périmètre volontairement
étroit proposé. Aucun risque de sécurité nouveau non couvert par les patrons existants (§12/§25).

## 33. Verdict

**GO WITH NOTES**

Communications & Notifications reste la priorité correcte après la Phase 20 — aucun besoin plus
urgent n'a été révélé par l'audit, et l'infrastructure actuelle (EmailProvider, RLS, RBAC, patron
prepare/send déjà prouvé deux fois) rend un MVP étroit directement réalisable sans nouvelle
dépendance ni scheduler. Le "WITH NOTES" reflète les 6 questions du §31, toutes des décisions
produit réelles (ciblage des annonces, email ou non pour les annonces, qui peut publier) plutôt que
des inconnues techniques — la Discovery elle-même est complète et n'est pas bloquée par elles.
