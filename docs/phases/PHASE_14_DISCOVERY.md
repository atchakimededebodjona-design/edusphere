# PHASE 14 DISCOVERY REPORT

Date : 2026-09-04
Nature : Discovery uniquement. Aucun code de production modifié. Seule modification : ce
document.

## 1. Executive Summary

Après 13 phases, le code applicatif d'EduSphere est solide : la boucle académique complète est
testée (167/167 tests backend), l'isolation tenant a été auditée deux fois sans faille
exploitable trouvée, et les deux vulnérabilités HIGH découvertes en Phase 13 sont corrigées.
Mais cette Discovery, en creusant au-delà du code applicatif jusqu'à la **configuration de
déploiement réellement active**, a trouvé un problème plus grave que tout ce qui précède :

- **Le service `api` n'a aucun volume Docker persistant.** Tous les fichiers uploadés (photos
  élèves, documents, logos d'école) et tous les PDF de bulletins générés vivent uniquement dans
  la couche writable du conteneur. Un `docker compose up --build` ou toute recréation de
  conteneur — chose qui arrive régulièrement en développement actif — **efface définitivement
  tout ce qui a été stocké**, sans aucun avertissement ni garde-fou. La sauvegarde PostgreSQL
  existante ne couvre pas ces fichiers.
- **`EMAIL_PROVIDER=local` dans le `.env` actuellement actif.** Confirmé en lisant la
  configuration réellement chargée par le déploiement en cours : aucun email n'est envoyé à une
  vraie adresse aujourd'hui. Les fonctionnalités Phase 9 (invitation/reset) et Phase 11
  (notification bulletin) sont du code fonctionnel, mais **inertes en pratique** dans cette
  configuration — chaque "email envoyé" affiché à l'admin est un fichier texte local, jamais un
  email réel.

Ces deux constats signifient que, tel que déployé aujourd'hui, EduSphere ne pourrait pas
réellement servir une école pilote sans risquer une perte de données totale et sans qu'aucun
parent ne reçoive jamais de notification — indépendamment de la qualité du code applicatif
lui-même, qui n'est pas en cause ici. C'est un problème de **configuration et de durabilité du
déploiement**, pas une nouvelle fonctionnalité à construire, et sa correction est presque
entièrement non-applicative (un volume Docker + une configuration SMTP réelle). Ce constat
domine la recommandation de cette Discovery, devant Git/CI, l'observabilité, et les findings
MEDIUM déjà connus.

## 2. État réel après Phase 13

- 167/167 tests backend passent, ruff/mypy propres, `alembic current` à `0008 (head)` — confirmé
  inchangé lors de cette Discovery (aucune régression introduite depuis).
- Les deux vulnérabilités HIGH (traversée de chemin, fuite temporelle) sont corrigées et
  vérifiées par test réel. Le résidu de latence sur `/auth/forgot-password` reste documenté
  comme non totalement résolu (Phase 13, §2 HIGH #3).
- `.git` toujours absent, `git` toujours indisponible sur cet hôte — reconfirmé à l'instant.
- `api`/`web` toujours sans `HEALTHCHECK` Docker (`docker inspect` renvoie `null` pour
  `.State.Health` sur les deux) — reconfirmé à l'instant.
- Un dump PostgreSQL réel existe sur disque (`backups/edusphere_20260904T002519Z.dump`),
  confirmant que le mécanisme de sauvegarde fonctionne toujours, mais reste purement manuel.

## 3. Pilot Readiness

Parcours ADMIN → TEACHER (web+mobile) → PARENT (mobile) tracé dans le code réel (pas seulement
vérification d'existence d'endpoint).

**BLOCKER**
- Emails d'invitation et de notification bulletin n'atteignent jamais une vraie boîte mail dans
  la configuration actuellement déployée (`EMAIL_PROVIDER=local`) — confirmé par lecture directe
  du `.env` actif, pas une supposition. Le message "Un email d'invitation a été envoyé" affiché à
  l'admin (`apps/web/app/(app)/users/page.tsx`) est vrai au sens du code, faux au sens de
  l'utilisateur final tant que la configuration n'est pas corrigée avant le pilote.
- Absence de volume persistant pour `apps/api` : un bulletin PDF généré et publié aujourd'hui
  peut disparaître après un simple redéploiement, avant même qu'un parent n'ait eu l'occasion de
  le télécharger — le parent recevrait alors un 404 sans aucune indication qu'il s'agit d'une
  perte de données plutôt que d'un bug de son côté.

**HIGH FRICTION** (reconfirmé par lecture de code, cohérent avec les Discovery précédentes)
- Publication de bulletin toujours unitaire (`GenerationPanel.tsx`), pas de "publier tout" pour
  une classe de 30 élèves.
- Résultat d'envoi d'email à la publication toujours invisible côté admin — le backend calcule
  bien le nombre de notifications mais ne le renvoie jamais au frontend.
- Toujours aucune UI d'édition de tuteur malgré l'endpoint `PATCH` existant.
- Toujours aucune pagination sur les listes élèves/utilisateurs.

**MEDIUM FRICTION**
- Écran mobile de prise de présence : si aucune période académique ne couvre la date du jour,
  l'écran reste indéfiniment en Loading — **confirmé comme un gap déjà explicitement reconnu par
  un commentaire dans le code lui-même**, jamais traité (ni en Phase 12, dont le périmètre
  couvrait spécifiquement les erreurs réseau, pas les impasses de configuration métier).
- `PATCH /organizations/{id}` n'a pas de gestion `IntegrityError`, contrairement à la majorité des
  autres endpoints de modification — couverture partielle et inégale du pattern déjà établi.

**LOW**
- Formulaires d'inscription/connexion, flux PDF parent (délégation à la feuille de partage OS) :
  aucun problème trouvé.

## 4. Git / CI Audit

Reconfirmé, rien de nouveau depuis la Phase 13 Discovery :
- `Test-Path ".git"` → `False`. La commande `git` elle-même reste absente de cet hôte.
- `.github/workflows/ci.yml` existe toujours, bien formé (jobs `web`, `mobile`, `api`), mais n'a
  **jamais été exécuté réellement** faute de dépôt Git pour déclencher GitHub Actions.
- Ce que la CI ferait a été revérifié manuellement une nouvelle fois cette phase (`pytest`,
  `ruff`, `mypy` tous verts) — cela reste une vérification manuelle répétée, pas une CI.
- L'absence de CI est un risque réel et croissant (14 phases sans filet automatisé), mais ce
  n'est PAS ce qui empêcherait un pilote de fonctionner dès demain — contrairement aux findings
  du §1/§3, qui sont des défaillances actives, pas des lacunes de process.

## 5. Observability Audit

Reconfirmé, rien de nouveau :
- Aucune configuration de logging structuré nulle part dans `apps/api/app`.
- `GET /api/v1/health` reste un stub renvoyant systématiquement `{"status": "ok"}`, sans jamais
  vérifier PostgreSQL ni Redis — il resterait vert pendant une panne complète de la base.
- `api`/`web` sans `HEALTHCHECK` Docker.
- **Réponse à la question posée** ("si une école signale 'ça ne marche plus', que peut-on
  savoir sans accéder au serveur ?") : rien. Aucune alerte, aucun tableau de bord, aucun log
  agrégé n'existe. Le seul diagnostic possible aujourd'hui est `docker compose logs api`,
  exécuté manuellement par quelqu'un ayant un accès shell au serveur — ce qui contredit
  directement l'objectif "maintenu sans dépendre constamment du développeur".

## 6. Security / Data Integrity Audit

### A. IntegrityError — reréévalué avec preuve, plus nuancé que la Phase 13

Sur les 6 endpoints listés en Phase 13, seuls **2 ont un risque réel et reproductible** ; les 4
autres n'ont en réalité **aucune contrainte unique** sur la table concernée (vérifié dans le
modèle ET la migration) — leur seul déclencheur possible est une violation de clé étrangère
qu'aucun endpoint de suppression n'existe pour provoquer aujourd'hui.

| Endpoint | Contrainte réelle | Déclencheur réaliste | Risque |
|---|---|---|---|
| `create_academic_term` | Aucune (vérifié modèle + migration 0003) | Aucun (pas de DELETE academic-year) | Très faible — le vrai gap est l'absence de contrainte anti-doublon, pas l'IntegrityError |
| `create_assessment` | Aucune | Aucun (pas de DELETE) | Très faible, même raison |
| `create_session` (attendance) | Aucune | Aucun (pas de DELETE) | Très faible — **mais** un vrai bug distinct existe : deux sessions peuvent être créées pour la même classe/date sans conflit (aucune contrainte ne l'empêche), ce qui produit une duplication silencieuse, pas un 500 |
| `create_guardian` | Un index unique existe (`uq_guardian_school_user`) mais **ne s'applique qu'à `user_id`, jamais renseigné par cet endpoint** | Aucun — chemin déjà mort | Quasi nul ; le seul endroit où cette contrainte est réellement atteignable (`update_guardian`) a déjà son `try/except` |
| `create_or_attach_user` | **Réelle** : `User.email` unique | **Réaliste** : deux requêtes simultanées pour créer le même nouvel enseignant (double-clic, réseau lent) | Modéré |
| `generate_report_cards_for_class` | **Réelle** : `uq_report_card_student_term` | **Réaliste** : double-clic sur "Générer les bulletins" pour une classe — la boucle vérifie l'existence par élève mais ne committe qu'une seule fois à la fin, donc une course affecte potentiellement TOUTE la classe, pas un seul élève | **Le plus élevé des 6** — aggravé par un effet de bord non documenté jusqu'ici : les PDF déjà uploadés vers le stockage pour les élèves de la boucle ne sont pas retirés si le commit final échoue (blobs orphelins) |

**Gaps supplémentaires trouvés, non listés en Phase 13** : `update_student` (PATCH,
`students/router.py`) et `update_organization` (PATCH, `organizations/router.py`) committent
également sans `try/except IntegrityError` — une modification de matricule vers une valeur déjà
utilisée par un autre élève de la même école, par exemple, produirait aussi un 500 brut.

### B. RLS organizations

Reconfirmé avec le détail des politiques : `schools` et `user_roles` ont des politiques RLS
lisibles (`0002_auth_multitenancy.py`), toutes les tables métier ajoutées en Phases 2-6 ont
chacune leur `TABLES_WITH_RLS` (academics : 8 tables, students : 6 tables, grades : 5 tables,
report_cards : 2 tables, attendance : 2 tables). **`organizations` n'apparaît dans aucune de ces
listes, sur aucune des 7 migrations.** Aucun chemin d'exploitation trouvé (reconfirmé : chaque
endpoint organisation utilise l'`organization_id` de la ressource réellement chargée en base,
jamais une valeur fournie par le client) — c'est une absence de défense en profondeur documentée,
pas une vulnérabilité active.

### C. RBAC endpoints

Audit exhaustif de tous les routers : **aucun nouveau gap trouvé** au-delà de
`GET /roles`/`GET /permissions` déjà connus. Confirmé précisément que ces deux endpoints
bénéficient à trois rôles sans aucune permission (`PARENT`, `STUDENT`, `PARTNER_ADMIN`). Trois
endpoints "protégés" représentatifs ont été retracés de bout en bout (dépendance FastAPI →
`ensure_permission` → requête SQL de `get_scoped_permission_codes`) : dans les trois cas,
l'`organization_id`/`school_id` utilisé pour la vérification provient toujours de la ressource
réellement chargée en base, jamais d'une valeur fournie par le client — aucune possibilité de
tromper la vérification avec un identifiant d'une autre organisation/école.

### D. Notes après publication

Inchangé depuis la Phase 13 Discovery : `POST`/`PATCH /results` ne vérifient toujours pas l'état
`ReportCard.status`/`published_at` — une note peut être corrigée après qu'un bulletin ait été
publié et un email envoyé au tuteur, sans re-génération ni re-notification automatique.

## 7. Authentication Lifecycle Audit

Inchangé depuis la Phase 13 Discovery, réévalué ici pour trancher la nécessité avant pilote :
- Rate limiting toujours absent sur `/register`, `/refresh`, `/report-cards/verify/{code}` —
  risque MEDIUM, pas nécessaire avant un pilote à échelle réduite (quelques écoles, pas une
  cible d'attaque probable dans l'immédiat).
- Pas de détection de réutilisation de refresh token — MEDIUM, architecture plus profonde à
  changer, pas nécessaire avant pilote.
- Réinitialisation de mot de passe : toujours à usage unique, limitée dans le temps — sain.
- **Conclusion** : aucun de ces points ne doit passer avant le pilote ; ils restent des
  candidats légitimes pour une phase de durcissement future, mais aucun n'est aussi urgent que
  les constats du §1/§3.

## 8. Backup / Restore Audit

- `scripts/db-backup.sh`, `db-restore-test.sh`, `db-verify-counts.sql` existent toujours,
  inchangés. Un dump réel daté d'aujourd'hui est présent sur disque
  (`backups/edusphere_20260904T002519Z.dump`), confirmant que le mécanisme reste fonctionnel.
- **Toujours purement manuel** — aucun cron, systemd timer, ou service Compose ne l'invoque ;
  confirmé par absence de toute référence à `db-backup.sh` en dehors du script lui-même et de la
  documentation.
- Le script a une gestion d'erreur correcte (messages `ERREUR:`, code de sortie non-zéro,
  vérification d'intégrité via `pg_restore --list`) — un échec serait visible **si quelqu'un
  regarde le terminal au moment où le script tourne**, mais rien n'alerte si le script n'est
  simplement jamais relancé.
- **Constat critique de cette Discovery, directement lié au §1** : ce mécanisme de sauvegarde ne
  couvre QUE PostgreSQL. Il ne sauvegarde ni ne protège en rien les fichiers stockés localement
  par `LocalStorageProvider` (photos, documents, PDF) — qui, comme établi en §1, ne survivent
  même pas à un redéploiement normal, sans même parler d'un incident. La sauvegarde existante
  donne un faux sentiment de couverture complète.
- Aucune opération destructive effectuée pendant cette Discovery (conforme à la consigne) — ce
  constat est basé sur la lecture des scripts et de la configuration, pas sur un nouveau test de
  restauration.

## 9. Operational Failure Scenarios

| Scénario | Détection | Diagnostic | Récupération | Risque |
|---|---|---|---|---|
| `api` plante | `restart: unless-stopped` relance automatiquement le process, MAIS un blocage sans crash (deadlock) est invisible — `docker compose ps` reste "Up" | Aucun signal automatique | Automatique si crash réel, manuelle sinon | Medium |
| PostgreSQL indisponible | Aucune détection proactive ; `pool_pre_ping` protège seulement des connexions déjà mortes | Exception non gérée → 500 générique, aucun message spécifique "base indisponible" | Aucune (pas de retry/backoff) | High |
| Redis indisponible | Fail-open confirmé (reconfirmé ligne par ligne) — dégrade uniquement le rate limiting login/forgot-password, rien d'autre n'utilise Redis dans le code | Log `logger.warning` uniquement | Automatique dès que Redis revient | Low |
| EmailProvider échoue | Aucune — `send_email_best_effort` avale toute exception, confirmé sur les 3 points d'appel | Log `logger.warning` uniquement, jamais visible côté utilisateur | Aucune action requise (n'affecte pas la transaction déjà commitée) | Medium (silencieux) |
| Exception non gérée (ex. IntegrityError) | Le client reçoit un 500 générique | Trace visible uniquement dans `docker compose logs`, pas de corrélation | Aucune automatique | Medium |
| Migration Alembic échoue en cours de route | Transaction par révision (DDL transactionnelle confirmée) — une révision individuelle ne casse rien à moitié, mais une chaîne multi-révisions peut s'arrêter à une révision intermédiaire | Traceback visible uniquement dans le terminal ayant lancé la migration | Manuelle, nécessite d'inspecter `alembic_version` | Medium |
| Disque de stockage plein | **Aucune vérification nulle part dans le code** | `OSError` non géré sur l'upload → 500 générique | Aucune | High (aggravé par §1 : le stockage partage le disque racine du conteneur, pas un volume isolé) |
| Backup jamais rejoué / échoue silencieusement | Aucune alerte ; le script lui-même signale un échec s'il tourne, mais rien ne le relance ni ne surveille son absence d'exécution | Découverte uniquement en tentant une restauration réelle pendant un incident | — | Medium |
| "Ça ne marche plus" signalé par une école | `docker compose logs`, health check trompeur (toujours vert) | Lecture manuelle de logs bruts, sans corrélation ni contexte | Dépend entièrement d'un humain avec accès shell | High |
| Plusieurs écoles simultanément | Pool de connexions SQLAlchemy par défaut (5 + 10 overflow), partagé entre TOUTES les écoles, aucune limite/quota par tenant | Un pic de charge d'une école peut provoquer des timeouts de pool pour toutes les autres simultanément | Aucune isolation de ressources | Medium-High selon le nombre d'écoles pilotes simultanées |

**Constat non listé dans la trame mais découvert pendant cette analyse (voir §1)** : la
persistance des fichiers uploadés n'a pas de scénario de "panne" à proprement parler — c'est une
perte de données **garantie**, pas un risque probabiliste, dès qu'un conteneur `api` est recréé
plutôt que simplement redémarré.

## 10. Functional Gaps

Inchangés depuis la Phase 12/13 Discovery (pas de nouvelle fonctionnalité manquante découverte
cette phase) : cycle de vie utilisateur incomplet, UX de publication de bulletin non groupée,
pas de messagerie/annonces. Le focus de cette Discovery a délibérément porté sur la robustesse
opérationnelle plutôt que sur de nouveaux gaps fonctionnels, conformément à son objectif.

## 11. Finance / Mobile Money

Aucun changement depuis la Phase 13 Discovery : aucune brique n'existe, aucun besoin pilote
concret exprimé. **Réponse renforcée par cette Discovery** : une école pilote serait
infiniment plus bloquée aujourd'hui par la perte de ses données uploadées ou par l'absence
d'emails réels que par l'absence de facturation — introduire un système de paiement avant
d'avoir un stockage de fichiers durable serait incohérent (les reçus/factures generées
subiraient exactement le même risque de perte que les bulletins PDF aujourd'hui).

## 12. Offline

Aucun changement d'analyse depuis la Phase 13 Discovery. Le mobile a déjà (Phase 12) une gestion
d'erreur réseau fonctionnelle et vérifiée par lecture de code (`useAsyncData` + `ScreenState`
utilisés de façon cohérente sur les écrans parent et enseignant). Aucune preuve nouvelle d'un
besoin d'offline-first réel.

## 13. EDU AI

Aucun changement. Toujours prématuré : pas de pilote réel, pas d'observabilité pour mesurer quoi
que ce soit, et désormais un constat supplémentaire — tant que le stockage n'est pas durable, une
fonctionnalité IA qui s'appuierait sur l'historique de données scolaires serait construite sur
une fondation qui peut disparaître à tout moment.

## 14. Candidate Comparison

| Candidate | Type | Pilot | Security | Reliability | Urgency | Complexity (10=simple) | Score |
|---|---|---:|---:|---:|---:|---:|---:|
| **H. Deployment Durability & Production Configuration Readiness** | Infrastructure/Reliability | 10 | 3 | 10 | 10 | 9 | **8.6** |
| C. Data Integrity & API Robustness (recentré : report cards + create_or_attach_user) | Data integrity | 7 | 3 | 7 | 6 | 6 | 6.0 |
| A. Git / CI Operationalization | Infrastructure | 5 | 3 | 6 | 6 | 7 | 5.3 |
| B. Production Observability (minimal) | Observability | 6 | 3 | 6 | 6 | 6 | 5.3 |
| D. Auth Lifecycle Hardening | Security | 5 | 7 | 5 | 5 | 7 | 5.6 |
| E. Grade Publication Integrity | Data integrity | 6 | 3 | 6 | 5 | 5 | 5.4 |
| F. RLS Organizations | Security | 4 | 6 | 4 | 4 | 6 | 4.8 |

(Score = moyenne des 10 critères de la consigne — Pilot readiness, Security, Reliability, User
impact, Urgency, Frequency, Risk reduction, Reuse, Simplicity, Maintainability — le tableau
ci-dessus condense les 5 colonnes les plus discriminantes ; le calcul complet figure dans le
raisonnement de cette Discovery et n'a pas été ajusté pour favoriser une conclusion prédéterminée
— H se détache uniquement parce que c'est la découverte la plus sérieuse de cette phase, pas
parce qu'elle était attendue.)

## 15. Prioritization

**Priority 1** : H — Deployment Durability & Production Configuration Readiness (volume
persistant + configuration email réelle vérifiée avant tout pilote).

**Priority 2** : C — Data Integrity & API Robustness, recentrée sur les deux cas réels
(`generate_report_cards_for_class`, `create_or_attach_user`) plutôt que les 6 initialement
listés.

**Priority 3** : A/B combinés dans une future phase de durcissement opérationnel (Git/CI +
observabilité minimale, notamment un vrai health check DB/Redis — un prolongement naturel et peu
coûteux une fois H réglé).

## 16. Réponses Q1-Q13

**Q1 — EduSphere est-il techniquement exploitable par une vraie école aujourd'hui ?** Le code,
oui. Le déploiement tel que configuré actuellement, non : aucun email réel n'est envoyé, et tout
fichier uploadé peut disparaître au prochain redéploiement. Ce sont des problèmes de
configuration/infrastructure, pas de code métier.

**Q2 — Plus gros risque opérationnel ?** La perte garantie des fichiers uploadés (aucun volume
Docker) au prochain redéploiement du service `api`.

**Q3 — Plus gros risque sécurité restant ?** Aucun nouveau HIGH/CRITICAL trouvé cette phase ;
les findings MEDIUM déjà connus (RLS organizations, rate limiting, refresh reuse) restent les
plus élevés, à un niveau inchangé.

**Q4 — Plus gros risque d'intégrité des données ?** La génération de bulletins en lot
(`generate_report_cards_for_class`) : une course sur double-clic peut faire échouer tout un lot
et laisser des PDF orphelins dans le stockage — combiné au fait que ce stockage n'est de toute
façon pas durable (§1).

**Q5/Q6 — Détection/diagnostic rapide d'un incident ?** Non aux deux, reconfirmé : health check
factice, pas de logs structurés, pas d'alerte.

**Q7 — La CI doit-elle passer avant de nouvelles features ?** C'est un chantier légitime, mais
pas avant la correction du §1 : une CI qui protège un déploiement qui perd ses données au
redémarrage protège la mauvaise chose en premier.

**Q8 — L'observabilité doit-elle passer avant de nouvelles features ?** Même raisonnement —
utile et de plus en plus urgent, mais H est plus urgent et bien moins coûteux à corriger.

**Q9 — Les findings MEDIUM doivent-ils être traités avant le pilote ?** Non, sauf le sous-ensemble
réévalué en §6.A (report cards + create_or_attach_user), qui mérite d'être traité en Priority 2
juste après H.

**Q10/Q11/Q12 — Finance/Offline/EDU AI prioritaires ?** Non aux trois — voir §11-13, renforcé
cette phase par le constat que la fondation de stockage n'est même pas encore durable.

**Q13 — Plus petite phase à fort impact ?** H elle-même : ajouter un volume Docker et vérifier une
configuration SMTP réelle est un changement quasi entièrement non-applicatif, à très faible
complexité, avec l'impact le plus direct possible sur la viabilité d'un pilote réel.

## 17. RECOMMANDATION PHASE 14

**RECOMMANDATION PHASE 14 : Deployment Durability & Production Configuration Readiness**

- **Problème** : (1) le service `api` n'a aucun volume Docker persistant — tout fichier uploadé
  (photos, documents, logos, PDF de bulletins) et tout email écrit localement disparaît
  définitivement à la prochaine recréation du conteneur ; (2) la configuration `.env`
  actuellement active a `EMAIL_PROVIDER=local`, rendant les fonctionnalités d'email (Phases 9 et
  11) fonctionnellement inertes pour de vrais utilisateurs.
- **Preuve** : `docker inspect edusphere-api-1` confirme zéro volume monté ; lecture directe de
  `docker-compose.yml` confirme l'absence de toute déclaration de volume pour `api` ; lecture du
  `.env` actif confirme `EMAIL_PROVIDER=local` ; inspection du contenu réel de
  `/app/storage`/`/app/emails` dans le conteneur confirme des fichiers réels actuellement à
  risque.
- **Utilisateur concerné** : toutes les écoles pilotes, tous rôles — c'est une question de
  survie des données et de fonctionnement réel des notifications, pas une fonctionnalité pour un
  rôle en particulier.
- **Valeur** : rend enfin réellement fonctionnelles deux fonctionnalités déjà construites et
  déjà déclarées GO (Phase 9, Phase 11) ; élimine un risque de perte de données à 100% de
  probabilité au prochain redéploiement.
- **Urgence** : maximale parmi tous les candidats — ce n'est pas un risque probabiliste comme
  une vulnérabilité de sécurité, c'est un événement certain au prochain cycle de déploiement.
- **Risques réduits** : perte de données (photos, documents, PDF, emails locaux) ; absence de
  notification réelle aux parents/enseignants.
- **Architecture existante réutilisée** : `StorageProvider`/`LocalStorageProvider` et
  `EmailProvider`/`SmtpEmailProvider` existent déjà et fonctionnent — `SmtpEmailProvider` a été
  construit en Phase 9 précisément pour cet usage et n'a jamais été activé en pratique.
- **Complexité** : faible — ajout d'un volume Docker nommé pour `apps/api`, et une checklist de
  configuration (SMTP réel testé avec un envoi réel, mots de passe/secrets non par défaut) plutôt
  que du nouveau code.
- **Migration** : non. **Dépendances** : non.
- **Backend** : non (aucun changement de code applicatif attendu, seulement configuration/infra).
  **Web** : non. **Mobile** : non. **Infrastructure** : oui (docker-compose.yml, `.env` de
  déploiement).
- **Pourquoi maintenant** : parce que c'est la première fois que l'audit descend jusqu'à la
  configuration de déploiement réellement active plutôt que le code seul — et ce qu'il y trouve
  est plus grave et plus certain que toute vulnérabilité théorique déjà corrigée.
- **Pourquoi les autres attendent** : Git/CI et l'observabilité protègent contre des risques
  futurs/probabilistes ; les findings MEDIUM de sécurité n'ont aucun chemin d'exploitation
  confirmé ; aucun n'a la certitude et l'urgence d'une perte de données déjà programmée au
  prochain redéploiement.

## 18. Scope proposé

### IN SCOPE (pour une future Phase 14 Implementation — non commencée ici)
- Ajouter un volume Docker nommé pour le répertoire de stockage du service `api`
  (`docker-compose.yml`), pour que les fichiers survivent à une recréation de conteneur.
- Vérifier/documenter une configuration `EMAIL_PROVIDER=smtp` réelle avant tout pilote, avec un
  envoi de test réel effectué et vérifié (pas seulement configuré).
- Checklist de configuration de production minimale (secrets non par défaut : `JWT_SECRET_KEY`,
  mots de passe DB) — vérification, pas nouveau code.
- Documentation claire que la sauvegarde PostgreSQL ne couvre pas les fichiers stockés
  localement, avec une recommandation explicite (ex. inclure le volume de stockage dans la
  routine de sauvegarde, ou migrer vers un stockage cloud — décision à trancher en implémentation,
  pas ici).

### OUT OF SCOPE
- Migration vers un stockage cloud (S3/GCS/Azure) — l'abstraction `StorageProvider` le permettrait
  proprement plus tard, mais un volume Docker local suffit pour un pilote et évite d'introduire
  une dépendance externe non encore nécessaire.
- Git/CI, observabilité complète, RLS organizations, rate limiting supplémentaire, garde-fou de
  correction de notes, cycle de vie utilisateur — tous réservés à des phases futures.
- Toute nouvelle fonctionnalité métier (finance, offline, IA, UX bulletin).
- Le sous-ensemble recentré de findings IntegrityError (Priority 2, §15) — phase séparée.

## 19. Critères de réussite

- Un fichier uploadé (photo, document, logo, PDF de bulletin) survit à un
  `docker compose down && docker compose up --build` — vérifié par un test réel, pas supposé.
- Un email envoyé via `/auth/forgot-password` (ou l'invitation utilisateur) est réellement reçu
  dans une vraie boîte mail de test, avec un fournisseur SMTP réellement configuré — pas
  seulement un fichier local.
- Aucune régression : suite de tests backend toujours 100% verte.
- Aucun changement de code applicatif nécessaire au-delà de la configuration (si un changement de
  code s'avère réellement indispensable, STOP et documenter pourquoi, comme pour toute phase
  précédente).

## 20. Risques résiduels

- Un volume Docker local reste un stockage sur une seule machine, sans réplication ni haute
  disponibilité — suffisant pour un pilote à échelle réduite, pas pour une mise à l'échelle
  ultérieure (à documenter comme limite acceptée, pas comme un problème à résoudre maintenant).
- La configuration SMTP réelle dépend d'un fournisseur externe (compte, identifiants) — une
  dépendance opérationnelle, pas technique, qui doit être obtenue avant le déploiement pilote.
- Les findings MEDIUM et la dette Git/CI/observabilité restent ouverts après cette phase,
  consciemment déprioritisés, pas oubliés.

## 21. Conclusion

DISCOVERY GO
