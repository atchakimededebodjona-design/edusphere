# PHASE 12 DISCOVERY REPORT

Date : 2026-09-04
Statut d'entrée : Phase 11 validée GO (notification email parent à la publication d'un bulletin).
Nature de cette phase : Discovery uniquement — aucune ligne de code de production modifiée.

---

## 1. État actuel d'EduSphere

EduSphere couvre aujourd'hui un cycle académique complet et cohérent :
bootstrap organisation/école → inscription élèves/tuteurs (+ import) → configuration académique (années, périodes, niveaux, matières, classes, affectations enseignants) → saisie de présence → saisie de notes avec moyennes/rangs calculés → génération et publication de bulletins PDF avec QR de vérification → visibilité parent (web via aucun accès direct, mobile en lecture seule) → email au tuteur à la publication (Phase 11).

L'infrastructure transverse existe et est raisonnablement soignée pour un stade pilote : RBAC à 3 couches (dépendance FastAPI + `ensure_permission` + RLS Postgres FORCE), rate limiting Redis fail-open (login + mot de passe oublié), abstraction `StorageProvider` et `EmailProvider` (implémentations locales seulement), sauvegarde/restauration Postgres testée réellement une fois, migrations Alembic linéaires (0001→0008, aucune depuis la Phase 7).

Ce qui manque structurellement, confirmé par l'audit et non par supposition :
- Aucun module finance/facturation n'existe (aucun modèle, aucune route) — le rôle `ACCOUNTANT` est un placeholder vide.
- Aucun module de communication/notification en base (pas de table `Notification`, pas de messagerie, pas d'annonces) — seul un envoi d'email sortant best-effort existe.
- L'application mobile a en réalité un volet enseignant complet (prise de présence + saisie de notes en écriture), contrairement à une lecture superficielle qui la limiterait aux parents.
- Le dépôt n'est **pas** un repository git (confirmé par l'environnement lui-même) : la CI définie dans `.github/workflows/ci.yml` n'a donc jamais tourné une seule fois depuis la Phase 0.

## 2. Ce qui fonctionne bien

- Isolation tenant à 3 couches, cohérente et testée (`test_tenant_isolation.py`), avec un piège RLS/commit bien documenté et réappliqué correctement à chaque nouvelle fonctionnalité (dernier exemple : Phase 11).
- Historique de migrations propre et linéaire, aucune divergence.
- Discipline anti-overengineering réellement respectée : aucune dépendance ajoutée sans justification sur 11 phases, aucune migration inutile, deux abstractions (`StorageProvider`, `EmailProvider`) répliquées proprement plutôt que sur-généralisées.
- Couverture de tests backend large (19 fichiers, 146 tests) et suite E2E web croissante (19 tests) sur les parcours critiques (onboarding, dashboard, reset password, wizard).
- Sauvegarde/restauration réellement vérifiée une fois (pas seulement documentée).
- L'application mobile, bien que minimale, est du code de production sérieux (pas de mock, gestion de session cohérente, réutilisation propre du refresh token) — pas un prototype jetable.

## 3. Gaps identifiés (priorisés)

1. **Mobile : gestion d'erreur réseau incomplète.** Plusieurs écrans (`app/(parent)/index.tsx`, `app/(teacher)/index.tsx`, `app/(teacher)/classes/[classId].tsx`) chargent leurs données sans `.catch()` : une coupure réseau laisse l'écran bloqué sur "Chargement..." indéfiniment, sans message ni retry. Ce sont les écrans d'entrée des deux rôles, utilisés quotidiennement.
2. **Mobile : désynchronisation d'état d'authentification.** Si le refresh token échoue, les tokens sont effacés côté client mais l'état `useAuth()` n'est pas mis à jour — l'utilisateur peut rester sur un écran authentifié en apparence pendant que tous les appels API échouent silencieusement.
3. **Notes modifiables après publication du bulletin, sans garde-fou.** Rien n'empêche `POST /results` / `PATCH /results/{id}` après qu'un bulletin a été publié (et un email envoyé) pour cette période — contrairement au module présence qui a un mécanisme de verrouillage (`locked`) explicite. Une correction de note post-publication ne redéclenche ni régénération ni renotification automatique.
4. **Cycle de vie utilisateur incomplet.** Aucun endpoint pour désactiver, modifier ou changer le rôle d'un utilisateur existant ; aucun changement de mot de passe pour un utilisateur déjà connecté (seulement le flux mot de passe oublié). Une école pilote aura besoin de désactiver un enseignant qui part.
5. **Publication de bulletin non groupée + résultat d'envoi invisible.** La publication reste bulletin par bulletin (pas de "Publier tout" pour une classe/période) et le clic "Publier" ne montre jamais si des emails ont été envoyés/à combien de tuteurs — aucune régression, juste une opportunité directe de suite de la Phase 11.
6. **Résidus jamais traités depuis plusieurs phases** (confirmés toujours présents) : table `organizations` sans politique RLS, absence de pagination sur `list_students` (charge tout en un appel), `IntegrityError` non interceptée sur `create_academic_term`/`create_assessment` (500 au lieu de 409), pas d'UI d'édition des tuteurs (l'endpoint `PATCH /guardians/{id}` existe côté backend mais n'est jamais exposé côté web), pas de recherche/pagination sur la liste des utilisateurs.
7. **Aucune observabilité.** Zéro logging structuré, zéro outil de suivi d'erreurs, zéro métrique — un incident réel en pilote serait invisible jusqu'à ce qu'un utilisateur se plaigne.
8. **Aucun repository git, donc aucune exécution réelle de la CI existante depuis la Phase 0.**
9. **Sauvegarde purement manuelle**, sans planification — documenté comme limite assumée depuis la Phase 7.3, jamais automatisé.
10. **`CLAUDE.md` absent, README racine obsolète** (encore signalé à la Phase 11) — friction d'onboarding pour quiconque reprend le projet.

## 4. Risques résiduels

| Niveau | Risque |
|---|---|
| **High** | Écrans mobiles sans gestion d'erreur réseau — impact direct sur l'usage quotidien des enseignants (présence, notes) et des parents. |
| **High** | Aucune exécution réelle de CI (pas de dépôt git) — aucun filet de sécurité automatisé sur 11 phases de changements. |
| **Medium** | Notes modifiables sans garde-fou après publication d'un bulletin déjà envoyé par email — risque de divergence silencieuse entre ce que le parent a reçu et la réalité. |
| **Medium** | Absence totale d'observabilité — un problème en pilote réel resterait invisible. |
| **Medium** | RLS manquante sur `organizations` — défense en profondeur absente sur une table de premier niveau (risque réel non confirmé exploitable, car la couche permission applicative gate déjà ces routes). |
| **Low-Medium** | Pas de pagination sur les listes élèves/utilisateurs — deviendra un problème de performance perceptible en grandissant, pas aujourd'hui à l'échelle d'une seule école pilote. |
| **Low** | Cycle de vie utilisateur incomplet (pas de désactivation/édition) — gênant opérationnellement mais contournable manuellement en pilote. |
| **Low** | Sauvegarde manuelle non planifiée — acceptable tant qu'un humain suit une routine, documenté comme tel. |
| **Low** | `CLAUDE.md` absent, README obsolète — friction, pas un risque fonctionnel. |

## 5. Candidats Phase 12

| # | Nom | Problème actuel | Utilisateur principal | Complexité | Migration | Nouvelles deps | Backend | Web | Mobile |
|---|---|---|---|---|---|---|---|---|---|
| A | **Mobile App Resilience Hardening** | Écrans mobiles se figent indéfiniment sur coupure réseau ; état d'auth désynchronisé après échec de refresh | Enseignants (usage quotidien), parents | Faible | Non | Non | Non | Non | Oui |
| B | **Pilot Security & Data Hardening Round 2** | RLS manquante sur `organizations`, pas de pagination `students`, `IntegrityError` non gérée (500 au lieu de 409) | Admin/plateforme (indirect pour tous) | Faible-Moyenne | Possible (RLS policy = migration légère) | Non | Oui | Non | Non |
| C | **Grade Correction Safeguard After Publication** | Une note peut être modifiée après publication d'un bulletin déjà envoyé par email, sans verrou ni renotification | Admin/Directeur, indirectement parent | Moyenne | Non (réutilise `published_at`/pattern `locked` existant) | Non | Oui | Oui (affichage du statut verrouillé) | Non |
| D | **User Account Lifecycle Completion** | Pas de désactivation/édition/changement de rôle d'un utilisateur existant, pas de changement de mot de passe connecté | Admin/Directeur | Faible-Moyenne | Non (`is_active` existe déjà) | Non | Oui | Oui | Non |
| E | **Report Card Publish UX Completion** | Publication bulletin par bulletin, aucune visibilité sur les emails envoyés à la publication | Admin/Directeur | Faible | Non | Non | Léger (retour de compteur) | Oui | Non |

Détail par candidat :

### A. Mobile App Resilience Hardening
- **Existe déjà** : logique de refresh token, pattern `ApiError`, pattern erreur/chargement/vide déjà standard côté web à répliquer.
- **Manque** : `.catch()` sur les effets de chargement initial de 3+ écrans identifiés (et vérification systématique des 11 écrans), état d'erreur + bouton "Réessayer", propagation de l'échec de refresh vers l'état d'auth global, timeout sur `fetch`.
- **Risque technique** : faible — modifications isolées, purement additives, aucun écran fonctionnel retiré.
- **Risque sécurité** : aucun.
- **Dépendances** : aucune nouvelle librairie.
- **Pourquoi maintenant** : c'est un défaut de fiabilité réel, pas hypothétique, sur la surface la plus utilisée quotidiennement (enseignants : présence + notes, tous les jours de classe). Un pilote où l'app "se bloque" sans explication mine directement l'adoption.
- **Pourquoi pas plus tôt** : n'était pas visible tant que Phase 7/7.1 n'avaient pas encore d'usage réel soutenu à auditer.

### B. Pilot Security & Data Hardening Round 2
- **Existe déjà** : RLS FORCE sur toutes les autres tables métier, pattern de policy à répliquer pour `organizations`.
- **Manque** : policy RLS `organizations`, paramètre de pagination sur `list_students`, `try/except IntegrityError` sur 2 endpoints.
- **Risque technique** : faible à moyen — une policy RLS mal écrite peut casser un accès légitime (SUPER_ADMIN cross-org), nécessite des tests d'isolation dédiés.
- **Risque sécurité** : c'est justement l'objet — réduit un risque existant.
- **Pourquoi maintenant** : signalé sans interruption depuis 4 phases (Phase 8 → 11) sans jamais être traité — pattern de dette qui s'accumule.
- **Pourquoi pas maintenant (en tant que priorité n°1)** : aucune preuve d'exploitabilité réelle (la couche permission applicative gate déjà ces routes) ; la pagination n'a pas encore d'impact mesurable à l'échelle d'une seule école pilote. Un léger risque théorique, pas un défaut vécu quotidiennement.

### C. Grade Correction Safeguard After Publication
- **Existe déjà** : pattern de verrou (`AttendanceSession.locked`) directement transposable ; `published_at` déjà réutilisé comme signal (Phase 11).
- **Manque** : vérification de l'état "publié" avant d'autoriser une modification de note, décision produit sur le comportement voulu (bloquer, avertir, ou exiger une régénération explicite), UI reflétant ce statut.
- **Risque technique** : moyen — touche `grades/service.py`, un module central avec beaucoup de tests existants à ne pas casser.
- **Risque sécurité** : aucun, question d'intégrité fonctionnelle.
- **Pourquoi maintenant** : protège directement la confiance dans la fonctionnalité phare (bulletin + notification parent) tout juste livrée en Phase 11.
- **Pourquoi pas maintenant** : aucun incident réel rapporté à ce jour, c'est un risque structurel latent plutôt qu'un défaut déjà vécu — moins urgent qu'un défaut de fiabilité déjà actif (candidat A).

### D. User Account Lifecycle Completion
- **Existe déjà** : champ `User.is_active`, module `users` avec create+list.
- **Manque** : `PATCH`/désactivation, changement de mot de passe authentifié, UI correspondante.
- **Risque technique** : faible.
- **Risque sécurité** : faible, à condition de bien re-vérifier les permissions sur les nouvelles routes.
- **Pourquoi maintenant** : besoin opérationnel réel et prévisible pour toute école (rotation de personnel).
- **Pourquoi pas maintenant** : contournable manuellement en pilote (un seul admin, peu d'utilisateurs) ; moins urgent qu'un défaut déjà actif.

### E. Report Card Publish UX Completion
- **Existe déjà** : endpoint `/publish` (Phase 11), best-effort email déjà en place.
- **Manque** : action de publication groupée, retour visible du nombre d'emails envoyés/échoués dans l'UI.
- **Risque technique** : faible.
- **Risque sécurité** : aucun.
- **Pourquoi maintenant** : suite naturelle et peu coûteuse de la Phase 11, sur le modèle Phase 10 → 10.1.
- **Pourquoi pas maintenant** : confort plutôt que correction d'un défaut ; moins urgent que A.

## 6. Score

| Candidat | Valeur pilote | Impact utilisateur | Fréquence | Urgence | Réutilisation existant | Simplicité | Risque faible | Cohérence architecture | **Score global** |
|---|---|---|---|---|---|---|---|---|---|
| A — Mobile Resilience | 8 | 8 | 9 | 7 | 9 | 9 | 9 | 9 | **8.5** |
| E — Report Card Publish UX | 6 | 6 | 5 | 4 | 9 | 8 | 9 | 8 | 6.9 |
| B — Security & Data Hardening R2 | 7 | 4 | 3 | 6 | 9 | 8 | 8 | 9 | 6.75 |
| D — User Lifecycle | 7 | 7 | 4 | 5 | 7 | 7 | 8 | 8 | 6.6 |
| C — Grade Correction Safeguard | 8 | 7 | 5 | 6 | 7 | 6 | 6 | 8 | 6.6 |

Le candidat A se détache nettement, non pas parce qu'il est le plus "intéressant", mais parce qu'il combine une fréquence d'usage quotidienne réelle, un impact utilisateur direct, un risque d'implémentation quasi nul et une réutilisation à 100% des patterns déjà en place — sans toucher ni au backend ni au web. Les candidats B et C touchent des risques réels mais latents (jamais vécus comme un incident concret) ; D et E sont des compléments de confort légitimes mais non urgents.

## 7. Analyse stratégique

**Q1 — Fonctions minimales pour un usage quotidien pilote ?**
Oui pour la boucle académique centrale (inscription → présence → notes → bulletin → visibilité parent), qui est complète et testée de bout en bout. Non pour la complétude opérationnelle : pas de désactivation d'utilisateur, pas de visibilité sur les échecs d'envoi d'email, et surtout une fiabilité mobile pas encore prouvée sous conditions réseau imparfaites — précisément les conditions d'un contexte scolaire réel.

**Q2 — Plus gros workflow encore trop manuel ?**
La publication de bulletins reste unitaire (un clic par élève) et la correction de note après publication n'a aucun garde-fou ni processus formel de re-régénération/re-notification — c'est un process manuel qui repose entièrement sur la mémoire de l'admin.

**Q3 — Plus gros manque pour les enseignants ?**
Pas une fonctionnalité manquante (présence et notes existent déjà en écriture sur mobile) mais un défaut de fiabilité : l'app peut se figer silencieusement sur une coupure réseau, sans message ni retry, sur les deux écrans qu'un enseignant utilise chaque jour.

**Q4 — Plus gros manque pour les parents ?**
Le même défaut de robustesse existe côté écran parent (`app/(parent)/index.tsx`). Au-delà de ça, pas de manque fonctionnel criant : lecture des enfants, présence, notes, bulletins PDF, email de notification — la couverture est déjà bonne pour un pilote.

**Q5 — Plus gros manque pour l'administration ?**
Une accumulation de petites incomplétudes (pas de désactivation utilisateur, pas d'édition de tuteur, pas de pagination, pas de visibilité sur les notifications envoyées) — aucune n'est bloquante isolément, mais leur somme représente un vrai coût de "travail de contournement manuel".

**Q6 — Le module financier doit-il devenir prioritaire maintenant ?**
Non. Aucune fondation n'existe (aucun modèle, aucune route, le rôle `ACCOUNTANT` est vide), et rien dans l'historique des 4 dernières Discovery ne montre un besoin pilote concret exprimé — seulement un besoin générique "logiciel scolaire classique". Construire la finance avant d'avoir stabilisé la fiabilité mobile et le cycle de vie utilisateur serait prématuré. À réévaluer si une école pilote réelle exprime un besoin explicite de facturation.

**Q7 — L'offline doit-il devenir prioritaire maintenant ?**
Non, pas l'offline-first complet. Le workflow qui en bénéficierait le plus (prise de présence en classe avec réseau instable) n'a même pas encore la résilience de base (retry, message d'erreur) — un pré-requis moins coûteux et plus urgent que de construire une file de synchronisation locale. Réévaluer l'offline seulement si un pilote réel rapporte une perte de données due à une coupure réseau après ce durcissement.

**Q8 — EDU AI doit-il être introduit maintenant ?**
Non. Aucune donnée d'usage réelle n'existe encore (pas de pilote en production), et il n'y a aucune observabilité pour mesurer l'impact d'une fonctionnalité IA une fois introduite. Les fondations manquantes sont : volume de données réelles, observabilité, et un besoin concret identifié par un usage réel — pas des lacunes techniques d'intégration LLM.

**Q9 — Un problème technique/sécurité doit-il passer avant toute nouvelle fonctionnalité ?**
Deux éléments méritent d'être nommés sans devenir la priorité choisie ici : l'absence totale de dépôt git (donc de CI réellement exécutée) et l'absence totale d'observabilité. Ni l'un ni l'autre n'empêche un usage quotidien quotidien quotidien du produit — ils empêchent de détecter/prévenir un problème futur, ce qui est différent d'un blocage immédiat. Ils sont documentés ici comme candidats sérieux pour un futur "Phase 12.x" de durcissement (sur le modèle Phase 10 → 10.1), mais le défaut de fiabilité mobile déjà actif (candidat A) est plus urgent car déjà vécu, pas seulement théorique.

## 8. Recommandation

**RECOMMANDATION PHASE 12 : Mobile App Resilience Hardening**

**Pourquoi** : c'est le seul candidat qui corrige un défaut déjà actif (pas latent) sur la surface la plus utilisée quotidiennement du produit, avec un risque d'implémentation quasi nul, zéro dépendance nouvelle, zéro migration, et sans toucher ni au backend ni au web.

**Pour qui** : enseignants (prise de présence et saisie de notes quotidiennes) et parents (consultation quotidienne/hebdomadaire), c'est-à-dire les deux rôles qui vivent dans l'app mobile.

**Quel problème** : plusieurs écrans mobiles chargent leurs données sans gestion d'erreur — une coupure réseau (réaliste en contexte scolaire) laisse l'écran figé sur "Chargement..." indéfiniment, sans message ni moyen de réessayer ; et un échec de rafraîchissement de token laisse l'utilisateur dans un état d'authentification apparente pendant que tous les appels échouent silencieusement.

**Valeur pilote** : directement liée à l'adoption — un enseignant qui pense que l'app "ne marche pas" pendant la prise de présence en classe abandonnera l'usage mobile, ce qui invaliderait une partie du travail déjà livré en Phase 7/7.1.

**Périmètre minimal** :
- Ajouter `.catch()` + état d'erreur explicite (réutilisant `ApiError`) sur tous les effets de chargement initial des 11 écrans mobiles, avec vérification systématique (pas seulement les 3 déjà repérés).
- Ajouter un bouton "Réessayer" sur l'état d'erreur, cohérent avec le pattern déjà utilisé côté web.
- Propager l'échec de `refreshTokens()` vers l'état d'authentification global pour forcer une redirection vers `/login` au lieu de laisser une coquille authentifiée obsolète.
- Ajouter un timeout raisonnable sur les appels `fetch` (aucun timeout n'existe actuellement).

**Ce qui existe déjà** : `apiFetch`, `ApiError`, la logique de refresh 401→retry, le pattern visuel loading/error/empty déjà standardisé côté web à répliquer côté mobile.

**Ce qui devra être créé** : uniquement de la logique de gestion d'erreur et d'état, aucune nouvelle architecture, aucune nouvelle dépendance.

**Risques** : très faibles — modifications additives et isolées à `apps/mobile`, ne touchant aucun contrat d'API ni aucune donnée.

**Pourquoi les autres candidats attendent** :
- **B (RLS `organizations` + pagination + IntegrityError)** reste un risque réel mais latent (jamais vécu comme incident), et une policy RLS mal calibrée est plus risquée à tester correctement qu'un correctif mobile purement additif — à traiter en Phase 12.1 selon le même schéma que 10 → 10.1.
- **C (garde-fou notes après publication)** touche un module central (`grades`) avec une décision produit à trancher (bloquer vs avertir) — mérite sa propre Discovery ciblée plutôt que d'être bricolé dans cette phase.
- **D (cycle de vie utilisateur)** est contournable manuellement le temps d'un pilote à effectif réduit.
- **E (UX publication bulletin)** est un confort, pas un défaut actif — bon candidat pour une phase courte de type 10.1 juste après celle-ci.

## 9. Scope proposé (pour la future Phase 12 Implementation — non commencée ici)

### IN SCOPE
- `apps/mobile/app/(parent)/index.tsx`, `app/(teacher)/index.tsx`, `app/(teacher)/classes/[classId].tsx`, et tout autre écran confirmé avec le même défaut lors de l'implémentation : ajout de `.catch()` + état d'erreur + retry.
- `apps/mobile/lib/api/client.ts` : timeout sur `fetch`, propagation de l'échec de refresh vers l'état d'authentification global.
- Vérification manuelle systématique (coupure réseau simulée / arrêt du conteneur `api`) sur les 11 écrans, documentée dans le rapport d'implémentation.

### OUT OF SCOPE
- Offline-first, file de synchronisation locale, cache persistant.
- Notifications push.
- Toute nouvelle fonctionnalité écran ou nouveau flux métier mobile.
- Tout changement backend ou web.
- Mise en place d'un framework de test mobile complet (Jest/Detox) — l'app n'en a aucun aujourd'hui ; l'introduire serait une nouvelle dépendance non strictement nécessaire pour ce correctif ciblé. Vérification par test manuel réaliste, comme documenté et accepté dans les phases précédentes pour des cas similaires.
- Sélecteur multi-écoles côté mobile.
- Les candidats B, C, D, E ci-dessus (réservés à de futures phases).

## 10. Critères de réussite (pour déclarer la future Phase 12 Implementation GO)

- Sur les 11 écrans mobiles, une coupure réseau simulée (arrêt du conteneur `api`) produit systématiquement un message d'erreur visible + bouton "Réessayer", jamais un blocage silencieux sur "Chargement...".
- Un échec de rafraîchissement de token redirige l'utilisateur vers `/login` en une interaction, sans coquille authentifiée obsolète.
- Aucun fichier backend ou web modifié (vérifiable par la liste des fichiers touchés).
- Aucune nouvelle dépendance ajoutée à `apps/mobile/package.json`.
- Les flux existants (prise de présence, saisie de notes, consultation parent, téléchargement PDF) fonctionnent sans régression après modification — vérifié manuellement faute de suite de tests mobile existante, et documenté honnêtement comme tel dans le rapport (pas de test automatisé fabriqué).

## 11. Conclusion

DISCOVERY GO
