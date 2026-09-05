# PHASE 15 DISCOVERY REPORT

Date : 2026-09-04
Nature : Discovery uniquement. Aucun code de production modifié. Seule modification : ce
document.

## 1. Executive Summary

Après 14 phases, le code applicatif et sa configuration de déploiement sont sains : isolation
tenant vérifiée à deux reprises, deux vulnérabilités HIGH corrigées (Phase 13), stockage fichiers
enfin persistant (Phase 14). Cette Discovery, en construisant méthodiquement les 6 scénarios de
reprise après sinistre demandés, met en évidence ce que Phase 14 avait déjà pressenti sans le
démontrer complètement : **la stratégie de sauvegarde actuelle a un point de défaillance unique
critique — tout (base de données, fichiers, ET leurs sauvegardes) vit sur une seule machine**, et
**aucune archive du stockage fichiers n'a jamais été créée**, malgré une procédure documentée
depuis Phase 14. Si le stockage était perdu aujourd'hui, la récupération serait tout simplement
impossible — pas parce que la procédure est mauvaise, mais parce qu'elle n'a jamais été exécutée
une seule fois. Si la machine hôte elle-même était perdue, la perte serait totale et définitive,
sauvegardes comprises.

Ce constat, backé par les 6 scénarios de reprise construits en §9, l'emporte sur Git/CI et
l'observabilité — non pas parce que ces deux chantiers ne sont plus légitimes, mais parce
qu'aucun des deux ne protège contre une perte de données irréversible, alors que c'est
exactement le risque actif identifié ici.

## 2. État réel après Phase 14

- 170/170 tests backend passaient à la fin de la Phase 14, ruff/mypy propres,
  `alembic current` à `0008 (head)` — reconfirmé inchangé au début de cette Discovery.
- Le bind mount `apps/api/storage` est actif (`docker inspect` confirme le mount), et contient
  désormais 337 fichiers/dossiers réels (résidus des suites de tests exécutées en Phase 13/14 —
  aucune donnée de pilote réel, mais la mécanique de persistance est bien vérifiée).
- `.git` toujours absent, `git` toujours indisponible sur cet hôte.
- `api`/`web` toujours sans `HEALTHCHECK` Docker.
- **Un seul dump PostgreSQL existe** dans `backups/` (`edusphere_20260904T002519Z.dump`,
  1,5 Mo) — daté de la Phase 7.3, jamais rejoué depuis, malgré 8 phases écoulées entretemps.
- **Aucune archive du stockage fichiers n'existe** dans `backups/` — la procédure documentée en
  Phase 14 (`STORAGE_BACKUP_RESTORE.md`) n'a jamais été exécutée pour de vrai.

## 3. Pilot Readiness

Inchangé dans ses grandes lignes depuis la Phase 14 Discovery (aucun code métier modifié depuis).
Le focus de cette Discovery porte délibérément sur l'exploitation opérationnelle plutôt que sur
de nouveaux gaps fonctionnels — voir §15 pour le tracé complet des parcours ADMIN/TEACHER/PARENT,
inchangé.

## 4. Git / CI

Reconfirmé, rien de nouveau :
- `Test-Path ".git"` → `False`. La commande `git` reste absente de cet hôte.
- `.github/workflows/ci.yml` existe, bien formé, **jamais exécuté** (aucun dépôt pour déclencher
  GitHub Actions).
- **Classification précise demandée par cette Discovery** : CI **"présente mais inutilisable"**
  dans cet environnement précis (le fichier est correct et serait probablement fonctionnel sur
  un vrai dépôt GitHub avec les secrets appropriés), mais **jamais réellement exécutée** — à ne
  jamais confondre avec "CI fonctionnelle".

## 5. Observability

Reconfirmé, rien de nouveau : aucune configuration de logging structuré, `GET /api/v1/health`
toujours un stub `{"status":"ok"}` sans vérification DB/Redis, `api`/`web` toujours sans
`HEALTHCHECK` Docker. Nouveau constat cette phase : `infrastructure/monitoring/` ne contient
qu'un `.gitkeep` — confirmé vide, jamais construit au-delà du placeholder Phase 0.

**Réponse à la question centrale** ("si l'école signale que la plateforme ne fonctionne plus,
que peut-on diagnostiquer sans accès direct au serveur ?") : rien, reconfirmé à l'identique
depuis la Phase 13/14 Discovery.

## 6. Health / Readiness

`GET /api/v1/health` (`apps/api/app/api/v1/health.py`) : toujours un stub renvoyant
systématiquement `{"status": "ok"}`, sans distinction liveness/readiness, sans vérifier
PostgreSQL, Redis, ni l'espace disque du volume de stockage. `docker inspect` confirme à nouveau
`api`/`web` sans `HEALTHCHECK` ; `db`/`redis` ont le leur et rapportent `(healthy)`.

## 7. PostgreSQL Backup / Restore

- Scripts (`db-backup.sh`, `db-restore-test.sh`, `db-verify-counts.sql`) toujours présents et
  inchangés.
- **Un seul dump existe**, daté du 4 septembre 2026 (Phase 7.3) — confirmé par listing direct de
  `backups/`. Aucun second dump n'a été produit depuis, malgré 8 phases de changements.
- Une restauration réelle a été testée une fois (Phase 7.3), vers une base de test dédiée
  (`edusphere_restore_test`), jamais vers un scénario de perte réelle de la base applicative.
- **Réponse à "si PostgreSQL est détruit aujourd'hui, combien de temps pour restaurer ?"** :
  **UNKNOWN de façon précise.** Le dump actuel ne fait que 1,5 Mo (données de test, pas un
  volume de pilote réel) — une restauration serait rapide à ce volume, mais aucun chronométrage
  de bout en bout (dump → conteneur `db` recréé → migrations réappliquées si nécessaire → API
  reconnectée → vérification) n'a jamais été enregistré. Ne pas confondre "la procédure a
  fonctionné une fois sur une base de test" avec "on sait combien de temps ça prend en
  situation réelle".

## 8. File Storage Backup / Restore

- Le bind mount (Phase 14) résout la persistance face à une recréation de conteneur — **ce
  n'est pas un backup**, rappelé explicitement dans sa propre documentation.
- **Aucune archive du stockage fichiers n'existe actuellement** — confirmé par l'absence de tout
  fichier `storage_*.tar.gz` dans `backups/` (seul le dump PostgreSQL y figure). La procédure
  documentée en Phase 14 n'a jamais été exécutée réellement, ce qui est cohérent avec la
  consigne de cette même phase de ne pas construire d'automatisation — mais signifie que la
  procédure reste **non éprouvée en pratique**, contrairement au backup PostgreSQL qui a au
  moins été exécuté une fois.
- **Réponse à "si la machine Docker est perdue demain, peut-on récupérer les photos, documents,
  logos et PDFs ?"** : **NON, dans l'état actuel.** Aucune copie n'existe en dehors de la
  machine hébergeant Docker elle-même. Réponse non inventée — basée sur l'absence constatée
  d'archive.

## 9. Disaster Recovery

| Scénario | Données perdues | Restauration possible | Procédure documentée | Temps estimé | Risque |
|---|---|---|---|---|---|
| **1. Conteneur API détruit** | Aucune (depuis Phase 14 — stockage persisté hors du conteneur) | Oui, automatique (`restart: unless-stopped`) ou manuelle | Partiellement (Phase 14 couvre la persistance, pas un runbook dédié à ce scénario précis) | Secondes à ~1 min | **Low** |
| **2. PostgreSQL perdu** | Tout depuis le dernier dump (potentiellement plusieurs jours — un seul dump existe, jamais renouvelé) | Oui, procédure testée une fois (Phase 7.3), mais vers une base de test, jamais en situation réelle | Oui (`BACKUP_RESTORE.md`) | UNKNOWN précisément (voir §7) | **Medium-High** (fraîcheur du backup, pas la procédure elle-même) |
| **3. Stockage fichiers perdu** | Tout — aucune archive n'existe à ce jour | **Non, dans l'état actuel** | Oui (`STORAGE_BACKUP_RESTORE.md`), mais jamais exécutée réellement | UNKNOWN — rien à restaurer aujourd'hui | **High** |
| **4. Machine/hôte perdu** | **Tout** — base, fichiers, ET les sauvegardes elles-mêmes (colocalisées) | **Non** | Non | N/A — perte totale et définitive dans l'état actuel | **Critical** |
| **5. Redis perdu** | Compteurs de rate limiting en cours uniquement (aucune donnée métier) | Automatique — fail-open déjà confirmé (Phase 14 audit, reconfirmé inchangé) | Implicite (comportement déjà en code) | Quasi immédiat | **Low** |
| **6. EmailProvider indisponible** | Aucune donnée métier (best-effort déjà confirmé) — mais **aucune notification** qu'un email a échoué, ni file de rattrapage | Aucune action système requise ; pas de garantie de rattrapage métier | Comportement best-effort documenté, pas de procédure de renvoi | N/A | **Medium** (silencieux) |

**Constat central de cette Discovery** : les scénarios 3 et 4 sont les plus graves, et ne sont
pas des risques théoriques futurs — ce sont des faits déjà vrais aujourd'hui, vérifiés par
l'absence constatée d'archives et par la colocalisation de tout sur une seule machine.

## 10. SMTP Production

Reconfirmé sans modification de configuration active (consigne respectée — aucun email envoyé,
aucun secret affiché) :
- `SmtpEmailProvider` existe, inchangé depuis la Phase 9, zéro nouvelle dépendance nécessaire.
- `.env` actif garde `EMAIL_PROVIDER=local` — confirmé par simple lecture, aucune valeur
  sensible reproduite ici.
- Configuration possible sans changement de code (Phase 14 l'a documenté en détail dans
  `docs/deployment/PRODUCTION_CONFIGURATION.md`).
- **Test réel de livraison** : toujours impossible dans cet environnement (aucun serveur SMTP
  accessible) — non tenté, conformément à la consigne.

## 11. Deployment Procedure

- `README.md` racine reste **stale** ("phases 0 à 5 livrées", inchangé depuis les premières
  Discovery qui l'avaient déjà signalé) — quickstart Docker basique (`cp .env.example .env`,
  `docker compose up --build`), sans mention de : appliquer les migrations, activer un vrai
  SMTP, être conscient du bind mount de stockage (Phase 14), exécuter un backup avant/après un
  changement, procédure de rollback.
- `infrastructure/deployment/` ne contient qu'un `.gitkeep` — jamais construit au-delà du
  placeholder Phase 0.
- La documentation existe, mais **dispersée** : `docs/database/BACKUP_RESTORE.md`,
  `docs/database/STORAGE_BACKUP_RESTORE.md`, `docs/deployment/PRODUCTION_CONFIGURATION.md`,
  plus 15 rapports de phase — rien ne les relie en une procédure unique et ordonnée.
- **Réponse factuelle à "un développeur qui n'a pas participé aux 14 phases pourrait-il
  déployer EduSphere correctement ?"** : il pourrait faire démarrer un environnement de
  développement fonctionnel en suivant le README. Il ne trouverait **aucun document unique** le
  guidant vers une configuration de pilote sûre (secrets à changer, SMTP à activer, premier
  backup à prendre) sans être déjà passé par plusieurs rapports de phase distincts.

## 12. Security Lifecycle

Reconfirmé inchangé par lecture directe du code (pas supposé) :
- `register`/`refresh` : toujours aucun appel à une fonction de rate limiting dans
  `auth/router.py` (seuls `login` et `forgot-password` en ont) — confirmé par grep direct.
- `GET /report-cards/verify/{code}` : toujours non throttlé.
- Détection de réutilisation de refresh token : toujours absente.
- Réinitialisation de mot de passe : toujours à usage unique, limitée dans le temps — sain,
  inchangé.
- **Aucun de ces points n'est devenu plus urgent** — toujours MEDIUM, aucune preuve nouvelle
  d'exploitabilité.

## 13. Data Integrity

Reconfirmé inchangé par lecture directe du code : `grades/router.py` ne référence toujours ni
`ReportCard.status` ni `published_at` — confirmé par grep direct, zéro résultat. Une note reste
modifiable après publication d'un bulletin déjà envoyé par email, sans garde-fou ni
renotification. Risque **data integrity**, pas sécurité — inchangé depuis la Phase 13 Discovery.

**Cycle noté → bulletin → parent, ce qui peut encore changer après publication** :
- La note elle-même (`AssessmentResult.score`) : oui, sans contrôle.
- La moyenne/le classement recalculés (`StudentSubjectAverage`/`StudentTermAverage`) : oui,
  automatiquement, en cascade dès qu'une note change.
- Le PDF déjà généré : non, reste figé tel que généré au moment de la publication — donc peut
  diverger silencieusement des moyennes/notes réelles en base après une correction ultérieure.
- L'email déjà envoyé au parent : non, jamais renvoyé — le parent garde un message qui ne
  mentionne aucune donnée (contenu volontairement minimal depuis la Phase 11), donc ce risque
  spécifique n'expose pas de donnée fausse au parent par email, mais le PDF qu'il peut consulter
  ensuite peut, lui, devenir obsolète sans que personne ne le sache.

## 14. API Robustness

Reconfirmé, cohérent avec le détail déjà établi en Phase 14 Discovery (audit dédié aux 6
endpoints `IntegrityError`) — aucun changement de code depuis, donc aucun changement d'état :
seuls 2 des 6 endpoints ont un risque réellement reproductible
(`generate_report_cards_for_class` — double-clic sur "Générer les bulletins", avec effet de
bord de blobs PDF orphelins en cas d'échec du commit final ; `create_or_attach_user` — course
sur double-soumission d'un nouvel email). Les 4 autres n'ont toujours aucune contrainte unique
atteignable via l'API actuelle. `update_student`/`update_organization` toujours sans
`try/except IntegrityError`.

## 15. Pilot Workflow

Inchangé depuis la Phase 14 Discovery (aucun code web/mobile/API métier modifié depuis) :
publication de bulletin toujours unitaire, pas de compteur d'emails envoyés visible côté admin,
pas d'UI d'édition de tuteur, pas de pagination élèves/utilisateurs, écran mobile de présence
toujours bloqué indéfiniment si aucune période académique ne couvre la date du jour. Aucun
nouveau blocker trouvé cette phase — le focus était délibérément opérationnel, pas fonctionnel.

## 16. Finance / Mobile Money

Inchangé. Aucune brique n'existe. **Renforcé par cette Discovery** : introduire un système de
paiement (données financières, reçus) sur une infrastructure qui ne sait pas encore garantir la
récupération de ses propres fichiers existants (§8-9) serait prématuré et irresponsable — les
reçus/factures subiraient exactement le même risque que les PDF de bulletins aujourd'hui.

## 17. Offline

Inchangé. Le mobile a déjà (Phase 12) une gestion d'erreur réseau fonctionnelle et vérifiée.
Aucune preuve nouvelle d'un besoin d'offline-first réel cette phase.

## 18. EDU AI

Inchangé. Toujours prématuré — pas de pilote réel, pas d'observabilité, et désormais un
argument supplémentaire : construire une fonctionnalité IA sur des données qui ne sont pas
garanties de survivre à une perte de machine serait bâtir sur une fondation non durable.

## 19. Candidate Comparison

| Candidate | Pilot | Reliability | Security | Data Protection | Urgency | Complexity (10=simple) | Score |
|---|---:|---:|---:|---:|---:|---:|---:|
| **C. Automated Backup & Recovery Hardening** | 9 | 9 | 4 | 10 | 8 | 7 | **7.45** |
| D. SMTP Production Activation | 8 | 3 | 3 | 1 | 7 | 9 | 6.09 |
| G. Health/Readiness + Docker healthchecks | 7 | 8 | 2 | 2 | 6 | 9 | 6.09 |
| H. Data Integrity & Security Lifecycle (bundle Phase 13 MEDIUM) | 6 | 7 | 7 | 6 | 5 | 5 | 6.00 |
| B. Observability minimale | 6 | 6 | 3 | 2 | 5 | 6 | 5.18 |
| A. Git + CI Operationalization | 5 | 6 | 3 | 1 | 6 | 6 | 4.90 |
| J. Deployment Procedure (runbook consolidé) | 6 | 5 | 2 | 2 | 4 | 9 | 4.70 |

(Score = moyenne des 11 critères de la consigne — Pilot readiness, Reliability, Security, Data
protection, User impact, Urgency, Frequency, Risk reduction, Simplicity, Reuse, Maintainability
— le tableau condense les colonnes les plus discriminantes ; calcul complet non ajusté pour
favoriser une conclusion prédéterminée. C se détache parce que c'est le seul candidat où
l'inaction expose déjà, aujourd'hui, à une perte de données irréversible et non simplement à un
risque futur.)

## 20. Prioritization

**Priority 1** : C — Automated Backup & Recovery Hardening (automatiser le backup PostgreSQL
existant, créer et tester réellement une première archive du stockage fichiers, établir une
procédure simple de copie hors machine).

**Priority 2** : D et G, en parallèle si possible (activation SMTP réelle — dépend d'un compte
externe à obtenir — et health check réel DB/Redis + healthchecks Docker — purement technique et
peu coûteux).

**Priority 3** : H (bundle des findings MEDIUM Phase 13), puis A/B (Git/CI + observabilité plus
large) dans une phase de durcissement ultérieure.

## 21. Réponses Q1-Q15

**Q1 — EduSphere peut-il réellement être exploité plusieurs semaines dans une école pilote
aujourd'hui ?** Fonctionnellement oui. Opérationnellement, non sans risque sérieux : la
stratégie de sauvegarde actuelle ne survivrait pas à la perte de la machine hôte, et le
stockage fichiers n'a jamais été réellement sauvegardé une seule fois.

**Q2 — Les données fichiers sont-elles réellement récupérables après perte de l'hôte ?** Non —
confirmé par l'absence de toute archive hors machine.

**Q3 — Les données PostgreSQL sont-elles réellement récupérables après perte de la base ?**
Oui, dans une certaine mesure — un dump existe et sa restauration a été testée une fois — mais
seulement jusqu'au dernier dump pris (aujourd'hui, celui de la Phase 7.3, jamais renouvelé), et
seulement si l'hôte contenant ce dump n'est pas lui-même ce qui a été perdu (voir Q2/Q4).

**Q4 — Combien de temps faut-il pour restaurer le système ?** UNKNOWN de façon précise pour un
scénario de bout en bout — seule la restauration PostgreSQL isolée a été chronométrée
implicitement (rapide, sur un petit volume de test), jamais un scénario complet mesuré.

**Q5 — Une panne API serait-elle détectée automatiquement ?** Non pour un blocage sans crash
(health check toujours factice) ; oui pour un crash franc (`restart: unless-stopped`), mais sans
alerte à personne.

**Q6 — Une panne DB serait-elle détectée automatiquement ?** Non — `/health` ne vérifie
toujours pas PostgreSQL.

**Q7 — Une erreur 500 serait-elle diagnostiquable ?** Seulement via lecture manuelle de logs
bruts non structurés (`docker compose logs`) — inchangé.

**Q8 — La CI peut-elle réellement empêcher une régression aujourd'hui ?** Non — jamais exécutée,
donc ne peut rien empêcher en pratique, quelle que soit la qualité du fichier de workflow.

**Q9 — Le déploiement est-il reproductible par un autre développeur ?** Partiellement — un
environnement de développement, oui ; une configuration de pilote sûre, non sans consulter
plusieurs documents séparés (voir §11).

**Q10 — SMTP réel peut-il être activé sans modifier le code ?** Oui, confirmé — seule la
configuration doit changer, le code existe déjà depuis la Phase 9.

**Q11 — Les findings MEDIUM Phase 13 restent-ils acceptables pour un pilote ?** Oui pour
l'instant — aucun n'est devenu plus urgent, aucune preuve nouvelle d'exploitabilité. Restent une
dette légitime, pas un blocage.

**Q12/Q13/Q14 — Finance/Offline/EDU AI doivent-ils passer avant l'operational readiness ?**
Non aux trois — voir §16-18, renforcé cette phase par le constat de fragilité de la sauvegarde.

**Q15 — Plus petite phase à fort impact ?** Automatiser le backup PostgreSQL existant (un cron
appelant un script déjà écrit et déjà testé) et exécuter, une seule fois, la création réelle
d'une archive de stockage suivie d'une restauration de test — un changement quasi entièrement
non-applicatif, à complexité très faible, qui transforme "aucune archive fichiers n'existe" en
"au moins une archive vérifiée existe", la différence la plus significative possible pour le
risque le plus grave identifié ici.

## 22. RECOMMANDATION PHASE 15

**RECOMMANDATION PHASE 15 : Automated Backup & Recovery Hardening**

- **Problème** : (1) un seul dump PostgreSQL existe, jamais renouvelé depuis la Phase 7.3 ;
  (2) aucune archive du stockage fichiers n'a jamais été créée, malgré une procédure documentée
  depuis la Phase 14 ; (3) tout — données vivantes ET sauvegardes — vit sur une seule machine,
  sans aucune copie hors site.
- **Preuve** : listing direct de `backups/` (un seul fichier, daté de la Phase 7.3) ; absence
  totale de fichier `storage_*.tar.gz` ; lecture de `docker-compose.yml` confirmant que
  `pgdata`, `backups/`, et `apps/api/storage/` sont tous des chemins sur la même machine hôte.
- **Impact pilote** : en l'état, un incident sur la machine hôte — panne disque, erreur humaine,
  perte matérielle — entraînerait une perte de données totale et définitive, y compris des
  moyens censés protéger contre cette même perte.
- **Utilisateurs concernés** : toutes les écoles pilotes — c'est un risque de survie des
  données, pas une fonctionnalité pour un rôle en particulier.
- **Urgence** : maximale parmi les candidats évalués — c'est un fait déjà vrai aujourd'hui
  (zéro archive de stockage existe), pas un risque probabiliste futur.
- **Risques réduits** : perte totale de données en cas d'incident machine ; absence de filet de
  sécurité pour le stockage fichiers spécifiquement.
- **Existant réutilisable** : `scripts/db-backup.sh`/`db-restore-test.sh` déjà écrits et déjà
  testés une fois ; procédure de backup du stockage déjà documentée en Phase 14
  (`STORAGE_BACKUP_RESTORE.md`), jamais exécutée — aucune nouvelle conception nécessaire, juste
  une exécution réelle et une automatisation simple (cron).
- **Complexité** : faible — planification (cron ou tâche planifiée), pas de nouvelle
  architecture.
- **Migration** : non. **Dépendances** : non (outils déjà présents : `pg_dump`, `tar`).
- **Backend** : non. **Web** : non. **Mobile** : non. **Infrastructure** : oui (planification +
  procédure de copie hors machine, à définir en implémentation).
- **Pourquoi maintenant** : parce que c'est la première fois que la question "peut-on
  réellement restaurer aujourd'hui ?" a été posée aussi directement — et la réponse pour le
  stockage fichiers est un "non" catégorique, pas un "peut-être" ou un risque théorique.
- **Pourquoi les autres attendent** : SMTP (D) et Health/Readiness (G) sont proches en score et
  restent de bons candidats de suivi immédiat, mais aucun des deux ne protège contre une perte
  de données irréversible — le critère que la consigne de cette Discovery demande explicitement
  de faire peser fortement. Git/CI, observabilité, et les findings MEDIUM restent une dette
  légitime mais moins urgente qu'un risque déjà actif aujourd'hui.

## 23. Scope proposé

### IN SCOPE (pour une future Phase 15 Implementation — non commencée ici)
- Planifier `scripts/db-backup.sh` via une tâche récurrente simple (cron hôte, ou un mécanisme
  équivalent déjà disponible — pas de nouvel orchestrateur).
- Exécuter réellement, au moins une fois, la procédure de sauvegarde du stockage fichiers
  documentée en Phase 14, puis un test de restauration réel (extraction + vérification par
  l'application, pas seulement une extraction vers un répertoire temporaire).
- Planifier cette sauvegarde de stockage de la même façon que le backup PostgreSQL, en veillant
  à ce que les deux restent synchronisés dans le temps (même principe déjà documenté en
  Phase 14).
- Documenter/mettre en place une procédure simple de copie hors machine (même manuelle au
  départ — un rappel opérationnel clair vaut mieux qu'une automatisation complexe non
  nécessaire) pour au moins un jeu de sauvegardes récent.

### OUT OF SCOPE
- SMTP production (candidat D, séparé, dépend d'un compte externe).
- Healthchecks/observabilité avancée (candidats G/B).
- Git/CI (candidat A).
- Findings MEDIUM Phase 13 (candidat H).
- Choix d'un hébergeur de sauvegarde cloud définitif — aucun n'est figé, cohérent avec la règle
  établie depuis la Phase 0 ; documenter la procédure de façon à pouvoir brancher un tel
  hébergeur plus tard sans réécrire la procédure.
- Toute nouvelle fonctionnalité métier.

## 24. Critères de réussite

- Un second dump PostgreSQL existe, produit automatiquement (pas manuellement), daté après
  cette phase.
- Une archive réelle du stockage fichiers existe dans `backups/`, et sa restauration a été
  testée de bout en bout (extraction + lecture par l'application via `StorageProvider`, pas
  seulement `tar -t`).
- Une procédure claire et documentée existe pour copier au moins le jeu de sauvegardes le plus
  récent hors de la machine hôte.
- Aucune régression : suite de tests backend toujours 100% verte.
- Aucun changement de code applicatif nécessaire au-delà de la planification/l'exécution (si un
  changement de code s'avère réellement indispensable, STOP et documenter pourquoi).

## 25. Risques résiduels

- Une sauvegarde planifiée reste locale à la machine tant qu'aucune copie hors site n'est
  effectivement réalisée à intervalle régulier, pas seulement documentée une fois.
- Le volume de données réel d'un pilote effectif sera plus important que les 1,5 Mo actuels — le
  temps de sauvegarde/restauration réel à cette échelle reste à mesurer une fois de vraies
  données existent.
- Les candidats D (SMTP), G (health/readiness), H (findings MEDIUM), A/B (Git/CI/observabilité)
  restent ouverts après cette phase, consciemment déprioritisés, pas oubliés.

## 26. Conclusion

DISCOVERY GO
