-- Phase 29 — contrôle de STRUCTURE après la migration (lecture seule, aucune écriture possible).
-- Voir docs/deployment/PHASE_29_PRODUCTION_RUNBOOK.md, étapes 4 et 5.
--
-- Usage, sur le serveur, depuis le répertoire du déploiement :
--   docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -X -v ON_ERROR_STOP=1 -f -' \
--     < scripts/release/phase29-postcheck.sql
--
-- Chaque ligne compare la valeur attendue à la valeur obtenue : toutes les lignes doivent être OK.
-- Ne contrôle que la structure, les droits et le catalogue des permissions (migrations 0024 à 0028),
-- jamais les données : il peut être relancé à tout moment. L'état des données est donné par
-- scripts/release/phase29-state.sql.

\set QUIET on
SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY;
\pset footer off

WITH
new_tables(t) AS (VALUES
    ('cash_sessions'), ('cash_movements'), ('cash_counts'), ('cash_count_lines'),
    ('subscription_price_grids'), ('subscription_price_lines'), ('subscription_invoice_number_counters'),
    ('subscription_invoices'), ('subscription_payments'), ('school_subscription_periods'),
    ('subscription_reminders')),
present AS (SELECT t, to_regclass(t) AS oid FROM new_tables WHERE to_regclass(t) IS NOT NULL),
expected_indexes(i) AS (VALUES
    -- 0024
    ('uq_user_roles_global'), ('uq_user_roles_org'), ('uq_user_roles_school'),
    -- 0026
    ('uq_cash_sessions_open_per_cashier'), ('ix_cash_sessions_school_status_opened'),
    ('ix_payments_school_cash_session'), ('ix_payments_school_recorded_by_paid_at'), ('ix_payments_school_paid_at'),
    ('ix_cash_movements_session_created'), ('ix_cash_counts_session_counted'), ('ix_cash_count_lines_count'),
    -- 0027
    ('uq_subscription_price_grids_one_active'), ('uq_subscription_invoices_one_open_per_school'),
    ('ix_subscription_invoices_school_created'), ('ix_subscription_invoices_status_created'),
    ('uq_subscription_payments_one_succeeded_per_invoice'), ('uq_subscription_payments_one_in_progress_per_invoice'),
    ('ix_subscription_payments_school_created'), ('uq_school_subscription_periods_one_free_trial'),
    ('ix_school_subscription_periods_school_starts'),
    -- 0028
    ('uq_subscription_reminders_period_stage'), ('uq_subscription_reminders_invoice_stage'),
    ('ix_subscription_reminders_school_created')),
expected_policies(p) AS (VALUES
    ('cash_sessions_tenant_isolation'), ('cash_movements_tenant_isolation'), ('cash_counts_tenant_isolation'),
    ('cash_count_lines_tenant_isolation'), ('subscription_invoices_tenant_isolation'),
    ('subscription_payments_tenant_isolation'), ('school_subscription_periods_tenant_isolation'),
    ('subscription_reminders_tenant_isolation'),
    ('subscription_price_grids_read_all'), ('subscription_price_grids_platform_write'),
    ('subscription_price_lines_read_all'), ('subscription_price_lines_platform_write')),
rbac AS (
    SELECT r.code AS role, string_agg(p.code, ', ' ORDER BY p.code COLLATE "C") AS perms
    FROM role_permissions rp
    JOIN roles r ON r.id = rp.role_id
    JOIN permissions p ON p.id = rp.permission_id
    WHERE p.code IN ('payments.cancel', 'cash.register.read', 'cash.register.manage', 'cash.register.review',
                     'subscriptions.read', 'subscriptions.pay',
                     'platform.subscriptions.read', 'platform.subscriptions.manage')
    GROUP BY r.code),
checks(n, controle, attendu, obtenu) AS (
              SELECT 1, 'Révision Alembic', '0028', (SELECT string_agg(version_num, ',') FROM alembic_version)
    UNION ALL SELECT 2, 'Nouvelles tables présentes', '11', (SELECT count(*)::text FROM present)
    UNION ALL SELECT 3, 'Colonne payments.cash_session_id', '1',
        (SELECT count(*)::text FROM information_schema.columns
         WHERE table_schema = 'public' AND table_name = 'payments' AND column_name = 'cash_session_id')
    UNION ALL SELECT 4, 'Index attendus présents', (SELECT count(*)::text FROM expected_indexes),
        (SELECT count(*)::text FROM expected_indexes WHERE to_regclass(i) IS NOT NULL)
    UNION ALL SELECT 5, 'Contraintes des nouvelles tables', '51 CHECK / 9 UNIQUE / 11 PK / 37 FK',
        (SELECT format('%s CHECK / %s UNIQUE / %s PK / %s FK',
                       count(*) FILTER (WHERE contype = 'c'), count(*) FILTER (WHERE contype = 'u'),
                       count(*) FILTER (WHERE contype = 'p'), count(*) FILTER (WHERE contype = 'f'))
         FROM pg_constraint WHERE conrelid IN (SELECT oid FROM present))
    UNION ALL SELECT 6, 'Clé étrangère payments.cash_session_id', '1',
        (SELECT count(*)::text FROM pg_constraint WHERE conname = 'fk_payments_cash_session_id')
    UNION ALL SELECT 7, 'Tables avec RLS activée ET forcée', '10',
        (SELECT count(*)::text FROM present JOIN pg_class c ON c.oid = present.oid
         WHERE c.relrowsecurity AND c.relforcerowsecurity)
    UNION ALL SELECT 8, 'Compteur de numérotation sans RLS (voulu)', 'false',
        (SELECT relrowsecurity::text FROM pg_class WHERE oid = to_regclass('subscription_invoice_number_counters'))
    UNION ALL SELECT 9, 'Policies attendues présentes', (SELECT count(*)::text FROM expected_policies),
        (SELECT count(*)::text FROM expected_policies e
         JOIN pg_policies p ON p.schemaname = 'public' AND p.policyname = e.p)
    UNION ALL SELECT 10, 'Policies inattendues sur les nouvelles tables', '0',
        (SELECT count(*)::text FROM pg_policies p
         WHERE p.schemaname = 'public' AND p.tablename IN (SELECT t FROM new_tables)
           AND p.policyname NOT IN (SELECT e.p FROM expected_policies e))
    UNION ALL SELECT 11, 'Droits edusphere_app (11 tables x SELECT/INSERT/UPDATE/DELETE, testés un par un)', '44',
        (SELECT count(*)::text FROM present, unnest(ARRAY['SELECT', 'INSERT', 'UPDATE', 'DELETE']) AS priv
         WHERE has_table_privilege('edusphere_app', present.oid, priv))
    UNION ALL SELECT 12, 'Rôle CAISSIER', '1', (SELECT count(*)::text FROM roles WHERE code = 'CAISSIER')
    UNION ALL SELECT 13, 'Permissions complètes du CAISSIER',
        'cash.register.manage, cash.register.read, fees.read, payments.manage, payments.read',
        (SELECT coalesce(string_agg(p.code, ', ' ORDER BY p.code COLLATE "C"), '(aucune)')
         FROM role_permissions rp JOIN roles r ON r.id = rp.role_id JOIN permissions p ON p.id = rp.permission_id
         WHERE r.code = 'CAISSIER')
    UNION ALL SELECT 14, 'Rôles détenant les permissions caisse / abonnement',
        'ACCOUNTANT, CAISSIER, DIRECTOR, PLATFORM_OWNER, SCHOOL_ADMIN, SUPER_ADMIN',
        (SELECT string_agg(role, ', ' ORDER BY role COLLATE "C") FROM rbac)
    UNION ALL SELECT 15, 'ACCOUNTANT',
        'cash.register.manage, cash.register.read, cash.register.review, payments.cancel, subscriptions.read',
        (SELECT coalesce(perms, '(aucune)') FROM (SELECT 1) one LEFT JOIN rbac ON rbac.role = 'ACCOUNTANT')
    UNION ALL SELECT 16, 'DIRECTOR',
        'cash.register.manage, cash.register.read, cash.register.review, payments.cancel, subscriptions.read',
        (SELECT coalesce(perms, '(aucune)') FROM (SELECT 1) one LEFT JOIN rbac ON rbac.role = 'DIRECTOR')
    UNION ALL SELECT 17, 'SCHOOL_ADMIN',
        'cash.register.manage, cash.register.read, cash.register.review, payments.cancel, subscriptions.pay, subscriptions.read',
        (SELECT coalesce(perms, '(aucune)') FROM (SELECT 1) one LEFT JOIN rbac ON rbac.role = 'SCHOOL_ADMIN')
    UNION ALL SELECT 18, 'PLATFORM_OWNER',
        'platform.subscriptions.manage, platform.subscriptions.read',
        (SELECT coalesce(perms, '(aucune)') FROM (SELECT 1) one LEFT JOIN rbac ON rbac.role = 'PLATFORM_OWNER')
    UNION ALL SELECT 19, 'SUPER_ADMIN',
        'cash.register.manage, cash.register.read, cash.register.review, payments.cancel, '
        || 'platform.subscriptions.manage, platform.subscriptions.read, subscriptions.pay, subscriptions.read',
        (SELECT coalesce(perms, '(aucune)') FROM (SELECT 1) one LEFT JOIN rbac ON rbac.role = 'SUPER_ADMIN')
    UNION ALL SELECT 20, 'Description de platform.subscriptions.read (mise à jour par 0027)',
        'Consulter les abonnements des écoles (états, factures, grilles de prix)',
        (SELECT description FROM permissions WHERE code = 'platform.subscriptions.read')
)
SELECT n AS "#", CASE WHEN attendu = obtenu THEN 'OK' ELSE 'KO' END AS resultat, controle,
       attendu, coalesce(obtenu, '(absent)') AS obtenu
FROM checks
ORDER BY n;
