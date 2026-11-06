# Runbook — Migration School Cashier Lot 3 (Alembic `0026`)

> Statut : **préparé, NON exécuté en production.** Aucune étape de ce document n'a été appliquée
> à une base de production. Rédigé à partir du code réel de `0026_cash_register_sessions.py`
> (PR #27) et de vérifications en lecture seule faites le 2026-10-18 (voir §0).

## 0. Constats vérifiés avant de commencer (lecture seule, 2026-10-18)

| Constat | Preuve | Conséquence |
|---|---|---|
| Une API publique répond sur `https://api.edulinkage.com` | `GET /api/v1/health` → `200 {"status":"ok"}`, `Server: nginx/1.28.3 (Ubuntu)`, certificat TLS valide, `Strict-Transport-Security: max-age=31536000; includeSubDomains`, `http://` → `301` vers `https://` | Le frontend de production doit être construit avec `NEXT_PUBLIC_API_URL=https://api.edulinkage.com` (déjà le cas : le CSP de `https://edulinkage.com` contient `connect-src 'self' https://api.edulinkage.com`). |
| La production n'exécute **pas** le Lot 3 | `GET /api/v1/cash/sessions/current` → `404` | Migration `0026` non appliquée (attendu). |
| La production n'exécute **pas non plus** le Lot 2 | `GET /api/v1/cashier/students/search` → `404` ; `GET /api/v1/payments` → `401` (route existante) | La version déployée est antérieure à la PR #26. **La révision Alembic de production peut être inférieure à `0025`, voire à `0024`** : non vérifié (aucun accès serveur). `alembic upgrade head` appliquerait alors plusieurs migrations d'un coup (§1). |

Aucune de ces vérifications n'a modifié la production (requêtes `GET`/`HEAD` publiques, sans
authentification).

## 1. Prérequis et vérification de la révision Alembic

1. **Gel** : annoncer une fenêtre de maintenance (aucun encaissement pendant la migration).
2. **Version applicative** : l'image API déployée APRÈS migration doit être celle du commit de la
   PR #27 (ou postérieur), l'image web construite avec `NEXT_PUBLIC_API_URL=https://api.edulinkage.com`
   (le build échoue sinon — voir `apps/web/config/apiUrl.js`). Ne jamais construire l'image de
   production avec `EDULINKAGE_NON_DEPLOYABLE_BUILD=1`.
3. **Révision actuelle** (sur le serveur, dans le conteneur API de production) :
   ```sh
   alembic current      # révision appliquée
   alembic heads        # doit afficher 0026 (head) avec le code de la PR #27
   alembic history -r current:head   # migrations qui seront appliquées
   ```
4. **Selon le résultat :**
   - `0025` → seule `0026` sera appliquée (cas nominal de ce runbook).
   - `0024` → `0025` (rôle CAISSIER, permission `payments.cancel`, description de
     `payments.manage`) puis `0026`.
   - `0023` ou moins → `0024` également. **`0024` échoue volontairement** si des doublons
     existent dans `user_roles` (elle les compte par portée et s'arrête avec un message, sans rien
     supprimer). Exécuter AVANT, en lecture seule :
     ```sql
     SELECT 'global' AS scope, count(*) FROM (SELECT user_id, role_id FROM user_roles
       WHERE organization_id IS NULL AND school_id IS NULL GROUP BY 1,2 HAVING count(*) > 1) d
     UNION ALL SELECT 'org', count(*) FROM (SELECT user_id, role_id, organization_id FROM user_roles
       WHERE organization_id IS NOT NULL AND school_id IS NULL GROUP BY 1,2,3 HAVING count(*) > 1) d
     UNION ALL SELECT 'school', count(*) FROM (SELECT user_id, role_id, school_id FROM user_roles
       WHERE school_id IS NOT NULL GROUP BY 1,2,3 HAVING count(*) > 1) d;
     ```
     Tout résultat non nul = **NO-GO** tant qu'un opérateur n'a pas décidé explicitement du
     nettoyage (décision métier, hors de ce runbook).
5. **Rôle d'exécution** : lancer Alembic avec le MÊME rôle propriétaire que les migrations
   précédentes (celui de `DATABASE_URL`). Les droits du rôle applicatif `edusphere_app` sur les 4
   nouvelles tables proviennent des `ALTER DEFAULT PRIVILEGES` posés par `0002` pour ce
   propriétaire : un autre rôle créerait des tables inaccessibles à l'API (contrôle §4.5).

## 2. Sauvegarde et vérification de la sauvegarde

**Une sauvegarde n'est valide qu'après une restauration réussie et vérifiée.**

1. Produire un dump juste avant la migration avec l'outil du dépôt (non modifié par le Lot 3) :
   `scripts/db-backup.sh` (dump `pg_dump -Fc`). Noter le fichier, sa taille, son horodatage.
2. Restaurer ce dump **dans un environnement isolé** (autre machine / autre instance Postgres —
   pas l'instance de production, même si `scripts/db-restore-test.sh` sait restaurer dans une
   base `edusphere_restore_test` de la même instance) :
   ```sh
   pg_restore -d <base_isolée> --no-owner <dump>
   psql -d <base_isolée> -f scripts/db-verify-counts.sql
   psql -d <base_isolée> -c "SELECT version_num FROM alembic_version;"
   psql -d <base_isolée> -c "SELECT count(*), sum(amount) FROM payments WHERE status = 'COMPLETED';"
   ```
3. Comparer ces chiffres avec la production (mêmes requêtes en lecture seule). Écart = **NO-GO**.
4. Sauvegarder aussi le stockage (reçus PDF) : `scripts/storage-backup.sh` (non modifié).
5. Conserver le dump hors du serveur de production jusqu'à la fin de la période d'observation (§8).

## 3. Application en préproduction (obligatoire avant la production)

1. Préproduction = **copie restaurée de la sauvegarde de production** (§2), avec le code de la PR #27.
2. Vérifier `alembic current` (doit être identique à la production).
3. `alembic upgrade head` — durée attendue courte : `0026` crée 4 tables vides, ajoute une colonne
   **nullable sans valeur par défaut** à `payments` (pas de réécriture de table) et crée 3 index sur
   `payments` (`CREATE INDEX` non concurrent : **verrouille les écritures sur `payments` pendant la
   construction** — d'où la fenêtre de maintenance ; mesurer cette durée en préproduction sur le
   volume réel).
4. Exécuter les contrôles §4 puis les tests fonctionnels §5.
5. **Tester le retour arrière** sur cette préproduction (§6.3) puis ré-appliquer `upgrade head`,
   et noter les durées.

## 4. Contrôles post-migration (préproduction, puis production)

### 4.1 Révision
```sql
SELECT version_num FROM alembic_version;   -- attendu : 0026
```

### 4.2 Tables, colonne, index (résultat attendu : `4 | 1 | 8`)
```sql
SELECT
  (SELECT count(*) FROM information_schema.tables
     WHERE table_name IN ('cash_sessions','cash_movements','cash_counts','cash_count_lines')) AS tables,
  (SELECT count(*) FROM information_schema.columns
     WHERE table_name = 'payments' AND column_name = 'cash_session_id') AS payment_column,
  (SELECT count(*) FROM pg_indexes WHERE indexname IN (
     'uq_cash_sessions_open_per_cashier','ix_cash_sessions_school_status_opened',
     'ix_payments_school_cash_session','ix_payments_school_recorded_by_paid_at','ix_payments_school_paid_at',
     'ix_cash_movements_session_created','ix_cash_counts_session_counted','ix_cash_count_lines_count')) AS indexes;
```

### 4.3 Contraintes métier (attendu : 14 lignes)
```sql
SELECT conrelid::regclass AS table_name, conname FROM pg_constraint
WHERE conname IN (
  'ck_cash_session_status','ck_cash_session_opening_non_negative','ck_cash_session_closed_complete',
  'ck_cash_session_variance_formula','ck_cash_session_variance_justified',
  'ck_cash_movement_amount_positive','ck_cash_movement_type','ck_cash_movement_direction',
  'ck_cash_movement_reason_present','uq_cash_movement_idempotency',
  'ck_cash_count_total_non_negative','uq_cash_count_line_denomination',
  'ck_cash_count_line_total','fk_payments_cash_session_id')
ORDER BY 1, 2;
```

### 4.4 RLS (attendu : 4 lignes, `relrowsecurity` et `relforcerowsecurity` à `true`, 1 policy chacune)
```sql
SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity,
       (SELECT count(*) FROM pg_policies p WHERE p.tablename = c.relname
          AND p.policyname = c.relname || '_tenant_isolation') AS policies
FROM pg_class c
WHERE c.relname IN ('cash_sessions','cash_movements','cash_counts','cash_count_lines');
```

### 4.5 Droits du rôle applicatif (attendu : `true` dans les 3 colonnes, 4 lignes)
Chaque droit est testé séparément : `has_table_privilege` avec plusieurs droits séparés par des
virgules renvoie `true` dès qu'UN SEUL est accordé, ce qui masquerait un droit manquant.
```sql
SELECT t,
       has_table_privilege('edusphere_app', t, 'SELECT') AS can_select,
       has_table_privilege('edusphere_app', t, 'INSERT') AS can_insert,
       has_table_privilege('edusphere_app', t, 'UPDATE') AS can_update
FROM unnest(ARRAY['cash_sessions','cash_movements','cash_counts','cash_count_lines']) AS t;
```

### 4.6 Permissions RBAC (attendu : CAISSIER → read, manage ; ACCOUNTANT, DIRECTOR, SCHOOL_ADMIN, SUPER_ADMIN → read, manage, review)
```sql
SELECT r.code AS role, string_agg(p.code, ', ' ORDER BY p.code) AS permissions
FROM role_permissions rp JOIN roles r ON r.id = rp.role_id JOIN permissions p ON p.id = rp.permission_id
WHERE p.code LIKE 'cash.register.%' GROUP BY r.code ORDER BY r.code;
```

### 4.7 Rattachement des paiements (attendu : aucun paiement historique rattaché)
```sql
SELECT count(*) AS payments_total,
       count(cash_session_id) AS attached_to_a_session      -- attendu : 0 juste après migration
FROM payments;
```
Les paiements existants gardent `cash_session_id = NULL` : `0026` ne rattache jamais rien
rétroactivement, et aucune route ne le permet.

## 5. Tests fonctionnels avant ouverture aux utilisateurs (préproduction)

Avec des comptes de test d'une école de test (jamais une école réelle) :
1. **CAISSIER sans caisse ouverte** : un encaissement espèces est refusé (`409`, bandeau
   « Aucune caisse ouverte » sur `/cashier`).
2. **Ouverture** (`/cashier/cash-register`) avec un fonds initial ; une 2e ouverture est refusée.
3. **Encaissement espèces** depuis `/cashier` : il apparaît dans « Encaissements de la session »,
   le solde théorique augmente ; un paiement non espèces par un CAISSIER reste refusé (`403`).
4. **Mouvement** (ex. versement banque) : le théorique diminue ; une sortie supérieure aux espèces
   disponibles est refusée ; un double envoi ne crée qu'un mouvement.
5. **Comptage** par coupures, **écart** non nul → motif + justification exigés → **clôture**.
6. **Après clôture** : plus d'encaissement espèces ni de mouvement dans cette session ;
   l'annulation d'un paiement de la session clôturée est refusée (`409`, message affiché sur
   `/payments`).
7. **Supervision** (`/cashier/supervision`, DIRECTOR/ACCOUNTANT/SCHOOL_ADMIN) : rapport du jour,
   par caissier, par méthode, export CSV.
8. **Non-régression** : paiement par un ACCOUNTANT/SCHOOL_ADMIN sans caisse (inchangé), annulation
   d'un paiement sans session (inchangée), journal d'audit (`payment.recorded`, `cash.*`).
9. **Isolation** : un compte d'une autre école/organisation ne voit aucune caisse (`403`/`404`).

## 6. Stratégie de retour arrière

### 6.1 Retour arrière applicatif (recommandé, non destructif)
`0026` est **additive et compatible avec l'ancienne version de l'API** : l'ancien code ignore les
4 nouvelles tables et n'écrit jamais `payments.cash_session_id` (colonne nullable). En cas de
problème, **redéployer l'image API/web précédente SANS downgrade** : aucune donnée n'est perdue,
les sessions/mouvements/comptages restent en base, inactifs, jusqu'à la correction.

### 6.2 Conséquences exactes d'un `alembic downgrade 0025`
Le downgrade de `0026`, dans cet ordre :
1. supprime les attributions puis les permissions `cash.register.read|manage|review` ;
2. supprime les index `ix_payments_school_paid_at`, `ix_payments_school_recorded_by_paid_at`,
   `ix_payments_school_cash_session`, puis **la colonne `payments.cash_session_id`** : le lien
   paiement → session est **perdu définitivement** (les paiements eux-mêmes, leurs montants,
   allocations, statuts et reçus sont conservés) ;
3. supprime les policies RLS puis **les tables `cash_count_lines`, `cash_counts`,
   `cash_movements`, `cash_sessions`** : **toutes les sessions, fonds initiaux, mouvements,
   comptages, écarts et justifications sont perdus définitivement** ;
4. ne touche PAS `audit_logs` : les événements `cash.*` et `payment.recorded` restent, mais
   pointent vers des entités qui n'existent plus.

Le downgrade exige que l'API ne tourne plus avec le code du Lot 3 (redéployer l'ancienne image
d'abord), sinon chaque requête de caisse échouerait.

### 6.3 Quand le downgrade est acceptable
Uniquement si **aucune opération réelle** n'a été enregistrée. À vérifier juste avant :
```sql
SELECT (SELECT count(*) FROM cash_sessions) AS sessions,
       (SELECT count(*) FROM cash_movements) AS movements,
       (SELECT count(*) FROM cash_counts) AS counts,
       (SELECT count(*) FROM payments WHERE cash_session_id IS NOT NULL) AS attached_payments;
```
Tout chiffre non nul → **ne pas faire de downgrade** (§7).

## 7. Si des opérations réelles ont déjà été enregistrées

Ne jamais lancer de downgrade destructif. Dans l'ordre de préférence :
1. **Retour arrière applicatif** (§6.1) : ancienne image, schéma conservé, données de caisse
   intactes ; correctif livré ensuite par une nouvelle version (migration `0027` additive si un
   changement de schéma est nécessaire).
2. **Correctif avant nouvelle migration** : corriger le code sur une branche, le valider en
   préproduction restaurée depuis une sauvegarde postérieure aux opérations réelles.
3. **Restauration contrôlée** : en dernier recours seulement, restaurer la sauvegarde §2 dans une
   base isolée, extraire et exporter d'abord les sessions/mouvements/comptages enregistrés depuis
   (ils seraient sinon perdus), et faire valider le plan par un responsable avant toute bascule.

## 8. Critères GO / NO-GO pour la production

**GO** seulement si TOUS les points sont vrais :
- [ ] `alembic current` de production connu et la liste exacte des migrations à appliquer validée (§1) ;
- [ ] contrôle des doublons `user_roles` à zéro si `0024` est en attente (§1.4) ;
- [ ] sauvegarde produite **et restaurée avec succès dans un environnement isolé**, chiffres
      identiques à la production (§2) ;
- [ ] migration appliquée sur une préproduction restaurée depuis cette sauvegarde, durée mesurée
      et compatible avec la fenêtre de maintenance (§3) ;
- [ ] contrôles §4 conformes en préproduction ;
- [ ] tests fonctionnels §5 conformes en préproduction ;
- [ ] retour arrière testé en préproduction (§6) ;
- [ ] image web construite avec `NEXT_PUBLIC_API_URL=https://api.edulinkage.com`, sans
      `EDULINKAGE_NON_DEPLOYABLE_BUILD` ;
- [ ] caissiers informés : ouverture de caisse obligatoire avant tout encaissement espèces ;
- [ ] CI GitHub verte sur le commit exact déployé.

**NO-GO** si un seul point est faux, inconnu ou non prouvé.

## 9. Après la mise en production

- Refaire §4 sur la production.
- Surveiller les erreurs `409` sur `POST /payments` (caissiers sans caisse ouverte) et les
  rapports de caisse pendant les premiers jours.
- Conserver la sauvegarde pré-migration jusqu'à la validation par les responsables financiers.
