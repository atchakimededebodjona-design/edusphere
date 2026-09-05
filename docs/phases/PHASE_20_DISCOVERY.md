# Phase 20 Discovery — Next Strategic Priority

Discovery uniquement. Aucun code applicatif, aucune migration, aucune dépendance, aucun changement
Docker/.env, aucun commit, aucun push n'ont été produits. Seul ce document a été créé. Chaque
affirmation distingue **PROUVÉ (lecture réelle)** de **NON VÉRIFIÉ**.

> **Implémentée** — voir [`docs/phases/PHASE_20_IMPLEMENTATION.md`](PHASE_20_IMPLEMENTATION.md)
> pour le rapport d'implémentation réel (migration `0010`, rate limiting register/refresh/verify,
> RLS `organizations`, traçabilité `StudentFee.updated_by`), verdict **GO WITH NOTES**.

## 1. Executive Summary

EduSphere (Phases 0-19) couvre aujourd'hui l'intégralité du cœur métier scolaire : organisation
multi-tenant, années/périodes/classes/matières, élèves+tuteurs+inscriptions (création manuelle ET
import en masse), notes (évaluations pondérées, moyennes, classements), bulletins (PDF+QR+
publication), présence (sessions verrouillables+statistiques), un tableau de bord opérationnel réel
(4 métriques, Phase 10 — pas une simple page statique), un espace parent mobile en lecture seule
couvrant présence/notes/bulletins/**frais** (Phase 19), sauvegarde/restauration/DR testées, santé/
readiness, Git+CI réels.

**Confirmé absent (NOT FOUND, vérifié par grep exhaustif)** : tout système de communication/
notification générique (aucun modèle `Notification`, aucun centre de notification in-app, aucun
ordonnanceur — `celery`/`APScheduler`/`cron`/`BackgroundTasks` : zéro occurrence dans `apps/api`) ;
tout flux d'admission/candidature ; tout concept d'emploi du temps (`Room` existe mais n'est
utilisé nulle part au-delà de son propre CRUD — un concept mort) ; tout module Examens distinct
(les "examens" sont aujourd'hui de simples `Assessment` avec un `AssessmentType` libre) ; toute
trace d'IA (aucun provider, aucune dépendance, une seule mention historique — comme exclusion de
périmètre, jamais comme projet).

**Confirmé accumulé sans être traité, depuis 6+ phases** : rate limiting incomplet
(`register`/`refresh`/`verify-by-code` jamais protégés), **HTTPS totalement absent** (aucun reverse
proxy, `infrastructure/nginx/` est un placeholder Phase 0), `organizations` sans policy RLS
(MEDIUM, documenté), aucune validation mobile réelle sur simulateur/appareil physique, aucun
garde-fou sur la correction de note après publication d'un bulletin, sauvegarde externe non
reproductible hors de cette machine de développement précise.

**Recommandation** (détaillée en §24/§26) : la fonctionnalité "suivante" objectivement la mieux
justifiée par le score n'est **ni** Mobile Money **ni** Communications **ni** aucun des candidats
métier proposés — c'est un candidat H, **durcissement sécurité + traçabilité financière**, motivé
par le fait que la Phase 19 a introduit de véritables données financières sur une infrastructure
qui n'a toujours pas fermé des lacunes de sécurité connues et documentées depuis la Phase 13. Ce
n'est pas un choix par défaut : c'est le score le plus élevé de la matrice (§7), argumenté
candidat par candidat.

## 2. État réel du produit

Confirmé par lecture directe (dashboard, `apps/web/app/(app)/page.tsx`, backend
`schools/service.py::get_dashboard_summary`) : le tableau de bord affiche 4 métriques réelles
(élèves actifs, taux de présence, complétude des notes, bulletins publiés) via ~5-6 requêtes
agrégées fixes — **pas** de N+1, **pas** un legs de page statique (contrairement à ce que
`PHASE_8_DISCOVERY.md:49-50` décrivait avant son implémentation en Phase 10).

`git log` confirme : `HEAD` = `32209dd` (Phase 19), arbre de travail propre, remote GitHub réel
configuré (`origin` = `https://github.com/atchakimededebodjona-design/edusphere.git`), CI déjà
verte sur `main` (vérifié Phase 18). Aucun problème Git/CI hérité à traiter.

## 3. Audit des modules

| Domaine | Statut | Preuve |
|---|---|---|
| Organizations/Schools/Setup | **A. COMPLET** | CRUD complet, `currency`/`timezone` par école, wizard `setup` web |
| Academic years/terms/classes/subjects/teacher assignments | **A. COMPLET** | `academics` module, RLS, RBAC |
| Authentication/Users/RBAC | **A. COMPLET** | JWT+refresh, rate limiting login/forgot-password (**partiel globalement**, voir §16) |
| Guardians/Parent access | **A. COMPLET** | Lien `Guardian.user_id`, 404 anti-énumération |
| Students/Enrollments (création+import) | **A. COMPLET** | `POST /students`, `POST /students/import` (dédup en 2 requêtes, pas de N+1) |
| Grades/Gradebooks | **A. COMPLET** | Pondération, moyennes, classements, complétude |
| Report cards + QR | **A. COMPLET** | PDF sandboxé, publication, vérification publique |
| Attendance (verrouillage+stats) | **A. COMPLET** | Sessions verrouillables, résumés sans N+1 |
| Fees/Payments/Allocations/Receipts (Phase 19) | **A. COMPLET pour son périmètre MVP** | Voir `PHASE_19_IMPLEMENTATION.md` |
| Dashboard opérationnel | **A. COMPLET mais minimal** | 4 métriques fixes, aucune tendance historique, aucune ventilation par classe |
| Email transactionnel (2 événements) | **B. PARTIEL** | `report_cards`/`fees` seulement — aucun autre événement (absence, retard, nouvelle inscription) ne déclenche d'email |
| Communications/notifications génériques | **C. ABSENT** | Zéro modèle, zéro endpoint, zéro ordonnanceur — confirmé par grep exhaustif |
| Admissions/candidatures | **C. ABSENT** | Zéro trace (`admission`/`candidate`/`application` : 0 résultat repo-wide) |
| Timetable/emploi du temps | **C. ABSENT** | Zéro trace (`timetable`/`slot` : 0 résultat) ; `Room` existe mais **mort** (utilisé dans 3 fichiers, seulement son propre CRUD) |
| Module Examens dédié | **C. ABSENT (mais largement couvert par Grades)** | `AssessmentType` permet déjà de nommer "Examen" ; aucun champ/règle spécifique à un examen |
| Mobile Teacher (classes/présence/notes) | **A. COMPLET pour son périmètre** | 5 écrans, `useAsyncData`/`ScreenState` uniforme |
| Mobile Parent (lecture seule) | **A. COMPLET pour son périmètre** | Présence/Notes/Bulletins/**Frais** |
| Résilience mobile / offline | **B. PARTIEL** | Retry/timeout réseau (Phase 12) ; **aucune** persistance locale, file d'attente ou sync (`AsyncStorage`/`offline`/`queue`/`sync` : 0 résultat réel) |
| Backup/Restore PostgreSQL+Storage | **A. COMPLET localement / D. NON PRODUCTION-READY à l'échelle** | Prouvé réellement (Phases 15/17), mais copie externe dépend d'un disque de développement personnel, pas reproductible sur un futur hôte de prod |
| Health/Readiness/Logging | **A. COMPLET** | `/health`, `/ready`, logging minimal (Phase 16) |
| StorageProvider/EmailProvider | **A. COMPLET (abstraction) / D. NON PRODUCTION-READY (SMTP réel jamais testé)** | Livraison SMTP externe réelle : **BLOCKED**, `PILOT_READINESS.md:51-52` |
| PaymentProvider | **A. COMPLET pour MANUAL / C. ABSENT pour tout fournisseur réel** | Voir §9 — fondations partielles pour un futur Mobile Money |
| AI/EDU AI | **C. ABSENT** | Zéro trace de code, une seule mention documentaire (exclusion de périmètre) |
| HTTPS/TLS | **C. ABSENT** | `infrastructure/nginx/nginx.conf.placeholder` uniquement, jamais traité |
| `packages/` (types/ui/validation/config) | **D. NON UTILISÉ** | Les 4 `src/index.ts` ne contiennent que `export {};` — jamais importés par web/mobile, code mort depuis la Phase 0 |

## 4. Gaps

| Gap | Utilisateur | Impact | Urgence | Dépendances | Complexité | Risque | Valeur commerciale | Valeur pilote |
|---|---|---|---|---|---|---|---|---|
| HTTPS absent | Tous | Données (dont financières depuis Phase 19) en clair sur le réseau | Haute | Aucune (config/infra) | Moyenne | Élevé | Bloquant pour un vrai pilote public | Élevée |
| Rate limiting incomplet (`register`/`refresh`/`verify-by-code`) | Plateforme | Abus/spam de comptes, y compris création d'un faux SCHOOL_ADMIN | Haute (documentée depuis Phase 13, jamais traitée) | Aucune (`rate_limit.py` déjà là) | Faible | Moyen | Moyenne | Moyenne |
| `organizations` sans RLS | Plateforme | Deuxième ligne de défense absente (le contrôle applicatif reste, MEDIUM documenté) | Moyenne | Aucune | Faible | Faible-Moyen | Faible | Faible |
| `StudentFee` sans `updated_by` | École/Comptable | Un ajustement manuel de `amount_due` n'est pas attribuable à un utilisateur précis (seul `note`, optionnel) | Moyenne (nouveau depuis Phase 19) | Aucune | Faible | Moyen (traçabilité financière) | Faible | Moyenne |
| Aucun email au-delà de 2 événements | Parents/École | Pas d'alerte absence, pas de rappel d'échéance | Moyenne | `EmailProvider` déjà prouvé | Faible-Moyenne | Faible | Moyenne | Moyenne |
| Aucune validation mobile réelle (device/simulateur) | Enseignants/Parents | Risque de bugs UX jamais détectés en environnement réel | Moyenne (connue depuis Phase 12) | Environnement de test manquant | Faible (effort de test, pas de code) | Moyen | Faible | Moyenne |
| SMTP externe jamais testé | École | Aucune preuve qu'un email atteint réellement une boîte externe | Moyenne | Un compte SMTP réel (hors de cet environnement) | N/A (bloqué par l'environnement) | Faible | Faible | Moyenne |
| Sauvegarde externe non reproductible en prod | Plateforme | Continuité d'activité non garantie sur un futur hôte réel | Moyenne | Un hôte de production réel (n'existe pas encore) | N/A | Moyen | Faible | Faible (pas encore un pilote réel) |

Aucun gap ci-dessus n'est inventé : chacun est cité verbatim dans `PILOT_READINESS.md`,
`DISASTER_RECOVERY.md`, ou déduit directement du schéma `fees/models.py` (StudentFee).

## 5. Candidats (voir grille complète §7)

Résumé qualitatif de chaque candidat, chiffré au §7 :

- **A. Communications & Notifications** — email déjà prouvé (2 événements), aucun système
  générique. Extension raisonnable et peu risquée, mais jamais signalée comme urgente.
- **B. Admissions** — dépréciorisée explicitement dans `PHASE_8_DISCOVERY.md`/`PHASE_9_DISCOVERY.md`
  depuis le début ; fondations (students/guardians/documents/fees) maintenant solides si un jour
  nécessaire.
- **C. Timetable** — `Room` existe mais est un concept mort ; complexité réelle de détection de
  conflits ; jamais jugée urgente.
- **D. Mobile Money** — forte valeur théorique, mais fondations insuffisantes (§9) : pas de statut
  `PENDING`, pas de webhook, pas de vérification de signature, pas de HTTPS.
- **E. Offline-first** — Phase 12 a déjà tranché consciemment contre l'offline complet ; aucune
  infrastructure de sync n'existe ; le paiement (le cas le plus sensible) est déjà volontairement
  web-only pour éviter ce problème.
- **F. Examens** — déjà couvert à ~90% par le moteur `grades` existant ; gain marginal.
- **G. AI** — aucune fondation, aucun cas d'usage identifié, risque de confidentialité des données
  élèves.
- **H. Sécurité & traçabilité financière (hardening)** — candidat proposé par cette Discovery,
  justifié par l'accumulation documentée de lacunes jamais fermées, aggravée par l'arrivée de
  données financières réelles en Phase 19.

## 6. Analyse Mobile Money (voir aussi §9 pour le verdict de préparation)

Ne doit **pas** être implémenté maintenant. Score le plus bas sur les axes dépendances/complexité/
risque de toute la matrice (§7) : `PaymentProvider` existe dans sa forme (interface + factory +
singleton) mais son modèle actuel (`Payment.status ∈ {COMPLETED, CANCELLED}`, écriture
synchrone dans la même transaction HTTP) ne correspond pas au fonctionnement réel d'un paiement
Mobile Money (confirmation asynchrone via webhook, état intermédiaire `PENDING`, nécessité de
vérifier une signature de webhook — mécanisme inexistant dans ce dépôt). Voir §9 pour le détail
exact des fondations manquantes.

## 7. Matrice de scoring

Échelle 1 (faible) à 5 (fort) par critère. Critère 7 = complexité **inverse** (5 = très simple),
critère 8 = risque **inverse** (5 = très sûr).

| Critère | A Comm. | B Admissions | C Timetable | D Mobile Money | E Offline | F Examens | G AI | H Sécurité/Audit |
|---|---|---|---|---|---|---|---|---|
| 1. Valeur pilote | 5 | 3 | 3 | 5 | 3 | 2 | 1 | 5 |
| 2. Impact utilisateur | 5 | 3 | 3 | 4 | 3 | 2 | 1 | 4 |
| 3. Impact commercial | 4 | 3 | 2 | 5 | 3 | 2 | 2 | 5 |
| 4. Urgence | 2 | 1 | 1 | 1 | 2 | 1 | 1 | 5 |
| 5. Dépendances positives | 5 | 4 | 3 | 1 | 1 | 5 | 2 | 5 |
| 6. Cohérence architecture | 5 | 4 | 3 | 2 | 2 | 4 | 2 | 5 |
| 7. Complexité inverse | 4 | 3 | 2 | 1 | 1 | 4 | 2 | 4 |
| 8. Risque inverse | 5 | 4 | 3 | 1 | 2 | 4 | 1 | 5 |
| 9. Extensibilité | 3 | 3 | 3 | 4 | 3 | 3 | 3 | 4 |
| 10. Préparation Afrique | 3 | 3 | 2 | 5 | 4 | 2 | 2 | 3 |
| **Total /50** | **41** | **31** | **25** | **29** | **24** | **29** | **17** | **45** |

**H (Sécurité & traçabilité financière) obtient le score le plus élevé**, porté par l'urgence (5 —
documentée depuis 6+ phases, jamais fermée) et l'absence quasi totale de nouvelles dépendances
(tout le nécessaire existe déjà : `rate_limit.py`, le mécanisme RLS, le schéma `StudentFee`).
**A (Communications)** arrive en second, loin devant les autres candidats métier — c'est le
candidat le plus solide **si** l'on cherche une nouvelle fonctionnalité utilisateur plutôt qu'un
durcissement.

## 8. Question stratégique importante

**EduSphere possède-t-il maintenant suffisamment de fondations pour commencer des fonctionnalités
"externes" (Mobile Money, notifications avancées, admissions) ?**

Réponse argumentée : **partiellement, mais une brique interne fondamentale reste à construire
avant Mobile Money spécifiquement, et une brique de durcissement devrait précéder toute nouvelle
fonctionnalité touchant des données sensibles.** Les fondations fonctionnelles (modèle de données,
RBAC, RLS, conventions de test) sont solides et démontrées phase après phase — ce n'est pas un
problème d'architecture logicielle. Le problème est **opérationnel/sécuritaire** : HTTPS absent et
rate limiting incomplet ne sont pas des détails secondaires une fois que de l'argent réel (même
manuel) transite par le système. Communications et Admissions, en revanche, ne dépendent d'aucune
fondation manquante — elles pourraient démarrer dès aujourd'hui si elles étaient jugées
prioritaires ; ce n'est donc pas un blocage universel, seulement pour tout ce qui implique un
canal externe non authentifié (webhook Mobile Money) ou un transport non chiffré à grande échelle.

## 9. Analyse Mobile Money — préparation réelle

**Vérifié dans `apps/api/app/core/payment.py` et `apps/api/app/modules/fees/`** (Phase 19,
connaissance directe) :
- `PaymentProvider(ABC)` + `ManualPaymentProvider` + factory + singleton : **présent**, prêt dans
  sa forme pour accueillir une seconde implémentation.
- `Payment.status` : seulement `COMPLETED`/`CANCELLED` — **aucun état `PENDING`/`FAILED`**. Un
  paiement Mobile Money réel commence `PENDING` (initié) et n'est confirmé qu'après un webhook
  asynchrone du fournisseur — le modèle actuel suppose une confirmation immédiate et synchrone,
  ce qui ne correspond pas à ce flux.
- `idempotency_key` : généré côté client (formulaire web), unique par école — **pas conçu pour
  recevoir un identifiant de transaction généré par un fournisseur externe**, ni pour dédupliquer
  une notification webhook redélivrée par ce fournisseur (scénario différent de la double-
  soumission déjà géré).
- Verrouillage de concurrence : `SELECT ... FOR UPDATE` **à l'intérieur d'une seule requête HTTP**
  — fonctionne pour un paiement guichet, ne s'applique pas tel quel à une confirmation qui arrive
  minutes/heures plus tard via un endpoint webhook séparé.
- **Aucune vérification de signature de webhook n'existe nulle part dans ce dépôt** — aucun
  précédent, aucune bibliothèque HMAC utilisée, à construire entièrement.
- **Aucun mécanisme de réconciliation** (détecter un paiement resté `PENDING` trop longtemps).
- **HTTPS absent** — recevoir un webhook contenant une référence de paiement sur un canal non
  chiffré est une faille de sécurité de base.
- Auditabilité : `recorded_by`/`cancelled_by`/`cancellation_reason` existent sur `Payment` — bonne
  base pour un futur log de transactions Mobile Money.

**Verdict : C — fondations supplémentaires nécessaires.** Manquant précisément : (1) HTTPS, (2)
cycle de vie `PENDING → COMPLETED/FAILED` sur `Payment`, (3) endpoint webhook + vérification de
signature (nouveau pattern, aucun précédent), (4) idempotence spécifique aux notifications webhook
(distincte de l'idempotence de soumission actuelle), (5) réconciliation des paiements bloqués en
`PENDING`, (6) discipline de journalisation qui masque les données provider sensibles (numéros de
téléphone, références) — aucune convention de masquage de logs financiers n'existe encore.

## 10. Analyse Communications

`EmailProvider` (Phase 9) est prouvé et stable, utilisé par exactly 2 flux métier connus
(publication de bulletin, enregistrement de paiement), tous deux via le motif
`send_email_best_effort` (lecture avant commit, envoi après, jamais bloquant). **Aucun
ordonnanceur n'existe** (`celery`/`APScheduler`/`cron`/`BackgroundTasks` : 0 occurrence dans
`apps/api`) — toute automatisation actuelle (sauvegardes) vit entièrement hors de l'application
(Planificateur de tâches Windows / crontab). **Aucune préférence de notification utilisateur**
n'existe. **Aucun modèle `Notification` générique.**

Une vraie architecture de notification (préférences, canaux multiples, historique, centre in-app)
n'est **pas justifiée maintenant** : aucun besoin documenté ne la réclame au-delà de "ce serait
utile" — construire ce système sans un ordonnanceur déjà prouvé et sans données d'usage réelles
(taux d'ouverture, pertinence) serait de la sur-ingénierie. Une extension **étroite** du motif
existant (émettre un email lors d'un nouvel événement métier déjà connu — ex. absence non
justifiée, échéance de frais approchant) est réalisable **sans nouvelle infrastructure**, mais un
vrai "rappel d'échéance" nécessite un déclenchement temporel (un ordonnanceur), ce qui manque
réellement — exactement le gap déjà identifié et volontairement reporté en Phase 19
(`PHASE_19_DISCOVERY.md §26`, `PHASE_19_IMPLEMENTATION.md §20`).

## 11. Analyse Offline

Écrans mobiles audités : Parent (Présence/Notes/Bulletins/Frais — 100% lecture, `useAsyncData` +
retry) et Teacher (classes/présence/évaluations/notes — mélange lecture ET écriture : soumission
de présence, saisie de notes). **Aucun** mécanisme de cache local, file d'attente ou synchronisation
n'existe (`AsyncStorage`/`offline`/`queue`/`sync` : 0 résultat réel dans `apps/mobile` — seul
`expo-secure-store` existe, pour les jetons JWT uniquement, pas un cache de données).

Cas où l'offline apporterait une vraie valeur : un enseignant en zone rurale à connectivité
intermittente faisant l'appel ou saisissant des notes hors ligne. C'est un besoin réel pour le
contexte africain — mais la Phase 12 a déjà tranché consciemment de ne **pas** le construire tant
qu'un mécanisme de synchronisation/résolution de conflit robuste n'existe pas (accepté GO WITH
NOTES). Rien n'a changé depuis qui justifierait de revenir sur cette décision maintenant, et le
paiement — le cas le plus sensible aux doublons — a été délibérément gardé web-only en Phase 19
précisément pour éviter ce risque. **Prioriser les cas d'usage plutôt que l'offline pour
l'offline** : si ce sujet redevient pertinent, l'attaque devrait commencer par la présence (risque
de doublon limité, déjà partiellement mitigé par la contrainte unique `(session_id, student_id)`),
jamais par les notes ou les paiements.

## 12. Analyse Admissions

Confirmé : un élève entre dans le système uniquement via `POST /students` (création directe) ou
`POST /students/import` (import CSV/Excel, dédup par matricule ou par identité, rapport d'erreurs
par ligne, un seul commit final — pas de N+1). **Aucune** trace de candidature, dossier de
candidature, ou étape de validation (`admission`/`candidate`/`application` : 0 résultat repo-wide).

Les dépendances pour un futur workflow Admissions sont maintenant réunies : `students` (cible de
conversion), `guardians` (contact du candidat), `student_documents` (pièces justificatives, déjà
un modèle générique réutilisable), `fees` (frais d'inscription — `FeeSchedule`/`Payment` peuvent
déjà représenter "frais de dossier"), `academic_years`/`classes` (année/classe visée). La valeur
reste cependant conditionnelle à un besoin réel exprimé par une école pilote : aujourd'hui, la
création manuelle/l'import suffisent pour un pilote de taille modeste — aucune preuve dans le
dépôt qu'une école ait dépassé cette capacité.

## 13. Analyse Timetable

Confirmé absent (`timetable`/`slot` : 0 résultat). `Room` existe (`academics/models.py`) mais est
un concept **mort** — utilisé dans exactement 3 fichiers (modèle, migration, CRUD basique), jamais
référencé par aucune autre logique métier (aucune session de cours, aucune contrainte horaire).
`teacher_assignments` n'a ni jour ni heure — confirmé, cohérent avec
`PHASE_8_DISCOVERY.md:81`.

Si ce sujet devient prioritaire un jour, un MVP simple et volontairement limité serait : une table
`timetable_slots` (classe, matière, enseignant, jour de semaine, heure début/fin — pas de moteur
d'optimisation, pas de détection de conflit automatique au-delà d'une contrainte unique
`(room_id, day, time_range)` si les salles sont réellement utilisées), consultation web + mobile en
lecture seule. Éviter explicitement (comme demandé) : moteur de scheduling, optimisation
automatique, gestion avancée de salles au-delà du strict nécessaire. **Non recommandé maintenant**
— score le plus bas de la matrice hors AI.

## 14. Analyse Examens

`grades/models.py` confirme : `AssessmentType` est un texte libre défini par l'école (rien
n'empêche de créer "Examen" aujourd'hui même) ; `Assessment.weight` est le seul mécanisme de
pondération (pas de champ `is_exam`) ; pas de salle d'examen, pas de convocation, pas de règle de
rattrapage. Le moteur de notes couvre déjà : création d'évaluations, saisie en masse, calcul de
moyennes pondérées, classements, appréciations, bulletins. **Un module "Examens" séparé n'est pas
nécessaire maintenant** — le gain serait marginal (essentiellement du vocabulaire/UX, pas une
nouvelle capacité), confirmé par le score le plus bas après AI/Timetable/Offline sur la plupart des
critères sauf dépendances/risque (déjà très bas, car il s'appuie sur de l'existant).

## 15. Analyse EDU AI

Aucune fondation : pas de provider, pas de dépendance, une seule mention documentaire historique
(exclusion de périmètre Phase 9, jamais un projet). Données réellement disponibles aujourd'hui :
notes, présence, frais — mais en profondeur encore limitée (un seul pilote, quelques mois de
données au mieux). Cas d'usage "sûrs" seraient purement analytiques sur des agrégats déjà calculés
(ex. "élèves à risque d'échec" à partir de `student_term_averages` + `attendance_rate`) — mais
même cela nécessiterait un historique multi-période qui n'existe pas encore en volume. Risque de
confidentialité réel si des données élèves étaient envoyées à une API externe. **Conclusion :
attendre.** Aucun cas d'usage immédiat n'apporte une valeur qui justifie le risque/coût
d'intégration maintenant — construire une couche "EDU AI" abstraite sans données ni cas d'usage
concret serait une fonction gadget, explicitement à éviter selon la consigne.

## 16. Audit sécurité

Nouveaux risques réels introduits par la Phase 19 : aucun de structurellement nouveau — les tables
`fees.*` utilisent exactement le même RLS/RBAC déjà audité et testé (y compris par un test RLS brut
dédié, voir `PHASE_19_IMPLEMENTATION.md §8/§16`). Le changement réel n'est pas un nouveau trou,
c'est une **aggravation de sévérité** des trous déjà connus : l'absence de HTTPS protégeait "avant"
des données scolaires ; elle protège maintenant aussi des montants et des méthodes de paiement.
De même, l'absence de rate limiting sur `register` permettrait, en théorie, la création en masse de
faux comptes `SCHOOL_ADMIN` qui pourraient ensuite manipuler des barèmes de frais — un chemin
d'abus qui n'existait pas avant la Phase 19. Permissions `ACCOUNTANT` vérifiées cohérentes
(`fees.read`+`payments.read`+`payments.manage`, jamais `fees.manage` — délibéré, voir
`rbac/seed.py`). Aucune permission trouvée trop large.

**Tâches de durcissement identifiées qui devraient précéder ou accompagner la Phase 20** (listées,
non codées) : compléter le rate limiting (`register`/`refresh`/`verify-by-code`), mettre en place
un reverse proxy HTTPS (même auto-signé en environnement de pilote), fermer le gap RLS
`organizations`, ajouter `updated_by` sur `StudentFee` (voir §17).

## 17. Audit traçabilité financière

`created_at`/`updated_at` : universels, confirmés sur toutes les tables `fees.*`.
`Payment.recorded_by`/`cancelled_by`/`cancellation_reason` : présents, permettent de reconstituer
qui a enregistré et qui a annulé un paiement. **Gap identifié** : `StudentFee` n'a **aucune**
colonne `updated_by` — un ajustement manuel de `amount_due` via `PATCH /student-fees/{id}` modifie
silencieusement le montant dû sans attribution obligatoire à un utilisateur (seul `note` existe, et
elle est optionnelle). C'est la seule vraie lacune de traçabilité financière trouvée par cet audit.

**Ne pas construire un audit log complet** (explicitement hors de propos ici, conforme à la
consigne) : la lacune est ponctuelle et se referme par un ajout minimal (`updated_by` +
rendre `note` obligatoire côté validation quand `amount_due` change), pas par une nouvelle
infrastructure de journalisation générale.

## 18. Audit RBAC

Rôles vérifiés dans `rbac/seed.py` (lecture complète, connaissance directe Phase 19) :
`SUPER_ADMIN`, `PLATFORM_SUPPORT`, `PARTNER_ADMIN`, `SCHOOL_ADMIN`, `DIRECTOR`, `ACCOUNTANT`,
`TEACHER`, `STAFF`, `PARENT`, `STUDENT`. Cohérence observée :
- `SCHOOL_ADMIN`/`DIRECTOR` : permissions quasi identiques partout (`fees.*`/`payments.*` inclus)
  — cohérent avec leur rôle de configuration.
- `ACCOUNTANT` : enfin doté de permissions réelles depuis la Phase 19 (`fees.read`,
  `payments.read`, `payments.manage`) — avant cela, un rôle vide depuis la Phase 1
  (`PHASE_13_DISCOVERY.md:250`). Scope jugé cohérent (peut opérer, ne configure pas les barèmes).
- `TEACHER`/`STAFF` : aucune permission financière — cohérent, aucun besoin exprimé.
- `PARENT`/`STUDENT` : zéro permission RBAC par conception (accès via lien Guardian uniquement,
  jamais via RBAC) — cohérent avec le motif déjà établi par `report_cards`/`parent`.

Aucune permission jugée trop large ou manquante par cet audit. Aucun nouveau rôle proposé (conforme
à l'interdiction de cette Discovery).

## 19. Audit RLS / multi-tenancy

**29 tables avec RLS** confirmées par grep de `ENABLE ROW LEVEL SECURITY` sur toutes les
migrations : `schools`, `user_roles` (0002) ; `academic_years`, `academic_terms`,
`education_levels`, `subjects`, `rooms`, `classes`, `class_subjects`, `teacher_assignments` (0003) ;
`students`, `guardians`, `student_guardians`, `student_enrollments`, `student_documents`,
`student_status_history` (0004) ; `assessment_types`, `assessments`, `assessment_results`,
`student_subject_averages`, `student_term_averages` (0005) ; `report_card_templates`,
`report_cards` (0006) ; `attendance_sessions`, `attendance_records` (0007) ; `fee_categories`,
`fee_schedules`, `student_fees`, `payments`, `payment_allocations` (0009).

**Sans RLS** : `organizations` (gap connu, documenté MEDIUM, non exploitable trouvé) ; `users`,
`roles`, `permissions`, `role_permissions` (tables globales/catalogue, RLS non pertinente par
nature) ; `user_sessions`, `password_reset_tokens` (scopées par `user_id` uniquement, pas de
colonne tenant). **Constat structurel** : la policy RLS ne s'applique qu'aux tables portant à la
fois `school_id`+`organization_id` — une convention cohérente, mais **NON VÉRIFIÉ** si ce choix a
jamais été formalisé comme règle explicite ailleurs que par la pratique répétée (aucun document ne
le déclare noir sur blanc, hormis le cas `organizations` qui est, lui, explicitement documenté
comme un choix/gap connu).

## 20. Audit backup/recovery

État inchangé depuis les Phases 15-17, revérifié : PostgreSQL et storage sauvegardés/restaurés
avec preuve réelle (y compris depuis la copie externe), 6 scénarios de reprise testés dans
`DISASTER_RECOVERY.md`, dont un seul incomplet (Scénario 4 — bascule complète de l'application
elle-même sur une machine neuve, jamais réellement effectuée, seulement les données). L'ajout de
données financières (Phase 19) **ne change rien** au mécanisme de sauvegarde lui-même (même
`pg_dump`, mêmes tables couvertes automatiquement) — mais **augmente l'enjeu** d'un point resté
"PASS avec réserve" : la copie externe dépend d'un disque personnel sur cette machine de
développement, pas d'une solution reproductible en production. Rien ne bloque la Phase 20 de ce
point de vue, mais ce point devrait être fermé **avant** un vrai pilote en production avec de
l'argent réel en jeu.

## 21. Audit performance

Audit ciblé (import élèves, tableau de bord, présence, notes, frais) : **aucun pattern N+1 trouvé**
nulle part. `import_students` charge les doublons potentiels en 2 requêtes puis traite tout en
mémoire ; `compute_school_completeness`/`compute_student_summary`/`compute_class_statistics`
utilisent des agrégats SQL ou une seule requête groupée en Python ; `get_dashboard_summary` reste à
~5-6 requêtes fixes indépendamment de la taille de l'école ; `fees/service.py` (Phase 19) a été
délibérément écrit avec des requêtes groupées (`_allocations_by_fee`) pour éviter cet écueil. Aucun
index spéculatif à ajouter, aucune optimisation prématurée nécessaire — conforme à la consigne.

## 22. Audit UX/produit

Web : `academics`, `grades`, `attendance`, `fees` suivent tous la **même** convention (barre
d'onglets, garde `permissions.includes(...)`, garde `!currentSchoolId`, panneaux dédiés par onglet)
— cohérence confirmée sur 4 pages distinctes, aucune dérive trouvée. Mobile : Teacher et Parent
suivent tous deux le motif `useAsyncData`+`ScreenState` de façon uniforme. Aucune incohérence UX
significative trouvée. Le tableau de bord (§2) reste volontairement minimal — pas une
incohérence, une limite de périmètre déjà connue.

## 23. Audit architecture

Saine dans l'ensemble après 19 phases : séparation modules/routers/services respectée
partout, conventions de migration et de RLS répétées à l'identique sans dérive. **Un seul
problème réel identifié** : `packages/{types,ui,validation,config}` sont du code **totalement
mort** depuis la Phase 0 — chaque `src/index.ts` ne contient que `export {};`, jamais importé par
`apps/web` ni `apps/mobile`. Cela n'a aucun impact fonctionnel (rien n'est cassé), mais représente
une dette de clarté (un futur contributeur pourrait perdre du temps à comprendre leur rôle
inexistant). **Ne pas refactoriser pour "nettoyer"** (conforme à la consigne) — à mentionner comme
tâche mineure optionnelle, jamais comme priorité.

## 24. Production readiness

**Verdict : B. PILOT READY, avec réserves explicites — pas encore C. PRODUCTION READY.**

Prêt : cœur fonctionnel complet (administration → présence → notes → bulletins → frais),
sécurité applicative (RBAC+RLS) prouvée par tests réels y compris pour les nouvelles données
financières, infrastructure de sauvegarde/restauration prouvée localement, santé/readiness réels,
Git/CI opérationnels.

Bloque un vrai lancement en production (pas un pilote contrôlé) : HTTPS absent, rate limiting
incomplet sur 3 endpoints d'authentification, livraison SMTP externe jamais prouvée, sauvegarde
externe non reproductible sur un futur hôte de production, aucune validation mobile sur
device/simulateur réel.

Peut attendre : Mobile Money (fondations manquantes, §9), toute nouvelle fonctionnalité métier
(Communications/Admissions/Timetable/Examens/AI) — aucune n'est bloquée par un défaut technique,
seulement par un choix de priorisation.

## 25. Roadmap proposée

Basée sur le score (§7) et la question stratégique (§8) — à ajuster selon le retour réel des
écoles pilotes, jamais figée a priori :

- **Phase 20 → Sécurité & durcissement pré-pilote réel** (objectif : fermer les gaps documentés
  depuis plusieurs phases avant que de l'argent réel ne transite ; valeur : rend un vrai pilote
  public défendable ; dépendances : aucune, tout le nécessaire existe déjà ; complexité : faible à
  moyenne, bornée ; pourquoi maintenant : score le plus élevé de la matrice, urgence maximale,
  aggravée par la Phase 19).
- **Phase 21 → Communications (extension ciblée, sans ordonnanceur)** (objectif : couvrir de
  nouveaux événements métier déjà connus par email best-effort ; valeur : engagement parent/école ;
  dépendances : `EmailProvider` déjà prouvé ; complexité : faible ; pourquoi maintenant : deuxième
  meilleur score, aucune fondation manquante).
- **Phase 22 → Admissions** (objectif : workflow de candidature → conversion élève, si une école
  pilote en exprime réellement le besoin ; dépendances : students/guardians/documents/fees, toutes
  prêtes ; complexité : moyenne ; pourquoi pas avant : jamais jugée urgente, à confirmer par un
  vrai besoin pilote avant de la lancer).
- **Phase 23 → Timetable MVP ou Examens (à trancher selon retour pilote)** (objectif : combler un
  gap secondaire selon ce que les écoles réclament réellement ; complexité : moyenne pour
  Timetable, faible pour Examens ; pourquoi pas avant : score le plus bas des candidats métier).
- **Phase 24 → Mobile Money (seulement après Phase 20)** (objectif : premher fournisseur réel
  derrière `PaymentProvider` ; dépendances : HTTPS + cycle `PENDING` + webhook + réconciliation,
  tous à construire en Phase 20/24 ; complexité : élevée ; pourquoi pas maintenant : fondations
  manquantes confirmées en §9, risque financier/sécurité le plus élevé de tous les candidats).

## 26. Recommandation Phase 20

> **PHASE 20 = Sécurité & Durcissement Pré-Pilote (avec fermeture du gap de traçabilité
> financière `StudentFee`)**

### Pourquoi maintenant ?
Score le plus élevé de la matrice (45/50), urgence maximale (documentée sans interruption depuis
la Phase 13, jamais traitée), et la Phase 19 vient d'augmenter concrètement l'enjeu en ajoutant de
vraies données financières sur une infrastructure qui transite encore en clair (pas de HTTPS) avec
des points d'authentification non protégés contre l'abus.

### Pourquoi pas les autres ?
Communications/Admissions/Timetable/Examens n'ont aucune fondation manquante — elles peuvent
attendre sans coût technique. Mobile Money et AI sont structurellement prématurés (§9/§15) :
les construire maintenant reviendrait à bâtir sur une base encore vulnérable. Offline a déjà été
consciemment écarté en Phase 12 et rien n'a changé qui justifie d'y revenir.

### Dépendances ?
Aucune nouvelle — `rate_limit.py`, le mécanisme RLS et le schéma `StudentFee` existent déjà ;
seul un reverse proxy HTTPS est une brique réellement nouvelle (infrastructure, pas une
dépendance applicative).

### Risques ?
Risque de scope creep vers un "grand audit sécurité" généraliste — à éviter : le périmètre doit
rester strictement les items déjà documentés et chiffrés ici, pas une redécouverte complète.

### MVP recommandé ?
(1) Rate limiting sur `register`/`refresh`/`verify-by-code` (réutiliser `rate_limit.py` tel quel) ;
(2) policy RLS sur `organizations` (migration simple, motif déjà répété 9 fois) ; (3) reverse
proxy HTTPS en local/pilote (certificat auto-signé acceptable, documenter clairement l'exigence
d'un certificat réel pour un futur hôte de production) ; (4) `StudentFee.updated_by` +
validation rendant `note` obligatoire quand `amount_due` est modifié manuellement.

### Hors périmètre ?
Tout audit de sécurité généraliste au-delà des points listés, toute nouvelle fonctionnalité
métier, tout audit log complet, toute automatisation SMTP réelle (dépend d'un compte externe hors
de cet environnement), toute amélioration de la sauvegarde externe au-delà de ce qui est déjà
documenté (dépend d'un futur hôte de production qui n'existe pas encore).

## 27. Hors périmètre (rappel global de cette Discovery)

Mobile Money réel, système de notification générique avec ordonnanceur, workflow Admissions,
Timetable, module Examens séparé, toute fonctionnalité IA, refactorisation de `packages/`,
implémentation de tout élément listé en §26 "MVP recommandé" (réservé à une future Phase 20
d'implémentation, jamais cette Discovery).

## 28. Questions nécessitant décision humaine

1. Confirmez-vous **Phase 20 = Sécurité & Durcissement** plutôt qu'une fonctionnalité métier
   visible (Communications étant le meilleur candidat alternatif si une valeur utilisateur
   immédiate est préférée à une réduction de risque) ?
2. Le reverse proxy HTTPS doit-il être scopé "preuve locale avec certificat auto-signé" (comme les
   Phases 14-17 l'ont fait pour le stockage/la sauvegarde), ou disposez-vous déjà d'un nom de
   domaine/hébergement réel qui changerait le périmètre possible ?
3. `StudentFee.note` doit-elle devenir strictement obligatoire dès qu'un `amount_due` est modifié
   manuellement, ou seulement fortement recommandée (avertissement, pas blocage) ?
4. Le rate limiting de `verify-by-code` doit-il suivre exactement les seuils déjà utilisés pour
   `forgot-password` (3 tentatives / 15 min) ou une politique différente est-elle souhaitée ?
5. Souhaitez-vous que Communications (Phase 21 proposée) commence à être cadrée en parallèle de la
   Phase 20, ou strictement après sa validation complète ?

---

# VERDICT

**GO WITH NOTES — recommandation Phase 20 = Sécurité & Durcissement Pré-Pilote**

L'audit ne révèle aucun blocage empêchant de démarrer une nouvelle phase, mais révèle une
accumulation réelle, documentée et jamais traitée de lacunes de sécurité/traçabilité dont la
sévérité vient d'augmenter avec l'arrivée de données financières (Phase 19). Cette Discovery
recommande de la traiter avant toute fonctionnalité "externe" (Mobile Money en particulier, dont
les fondations manquent objectivement — §9), tout en confirmant qu'aucune des autres
fonctionnalités métier proposées (Communications, Admissions, Timetable, Examens, AI) n'est elle-
même bloquée techniquement si une priorité différente était retenue. Les "notes" sont les 5
questions de décision humaine du §28 — aucune n'est bloquante pour valider l'orientation générale.

Aucune implémentation n'a été commencée. Le dépôt applicatif reste strictement inchangé.
