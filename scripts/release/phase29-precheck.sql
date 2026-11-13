-- Phase 29 — contrôle AVANT la mise en production (lecture seule, aucune écriture possible).
-- Voir docs/deployment/PHASE_29_PRODUCTION_RUNBOOK.md, étapes 2, 4 et 5.
--
-- Usage, sur le serveur, depuis le répertoire du déploiement :
--   docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -X -v ON_ERROR_STOP=1 -f -' \
--     < scripts/release/phase29-precheck.sql
--
-- Fonctionne sur toute révision à partir de 0023 (avant comme après la migration) : il sert aussi
-- à comparer la production et sa copie restaurée.

\set QUIET on
SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY;
\pset footer off

\echo
\echo '=== 1. Révision Alembic appliquée'
SELECT version_num AS revision FROM alembic_version;

\echo
\echo '=== 2. Objets créés par les migrations 0024 à 0028 : déjà présents ?'
\echo '    (attendu : true pour les migrations déjà appliquées, false pour les autres)'
SELECT migration, objet, to_regclass(objet) IS NOT NULL AS deja_present
FROM (VALUES
    ('0024', 'uq_user_roles_global'), ('0024', 'uq_user_roles_org'), ('0024', 'uq_user_roles_school'),
    ('0026', 'cash_sessions'), ('0026', 'cash_movements'), ('0026', 'cash_counts'), ('0026', 'cash_count_lines'),
    ('0027', 'subscription_price_grids'), ('0027', 'subscription_price_lines'),
    ('0027', 'subscription_invoice_number_counters'), ('0027', 'subscription_invoices'),
    ('0027', 'subscription_payments'), ('0027', 'school_subscription_periods'),
    ('0028', 'subscription_reminders')
) AS o(migration, objet)
ORDER BY migration, objet;

SELECT '0025' AS migration,
       (SELECT count(*) FROM roles WHERE code = 'CAISSIER') AS role_caissier,
       (SELECT count(*) FROM permissions WHERE code = 'payments.cancel') AS permission_payments_cancel;

\echo
\echo '=== 3. Doublons dans user_roles (bloquant pour 0024 si elle reste à appliquer ; attendu : 0 partout)'
SELECT 'global' AS portee, count(*) AS doublons FROM (
    SELECT user_id, role_id FROM user_roles
    WHERE organization_id IS NULL AND school_id IS NULL GROUP BY 1, 2 HAVING count(*) > 1) d
UNION ALL SELECT 'organisation', count(*) FROM (
    SELECT user_id, role_id, organization_id FROM user_roles
    WHERE organization_id IS NOT NULL AND school_id IS NULL GROUP BY 1, 2, 3 HAVING count(*) > 1) d
UNION ALL SELECT 'ecole', count(*) FROM (
    SELECT user_id, role_id, school_id FROM user_roles
    WHERE school_id IS NOT NULL GROUP BY 1, 2, 3 HAVING count(*) > 1) d;

\echo
\echo '=== 4. Table payments (0026 y ajoute une colonne et 3 index)'
SELECT count(*) AS paiements, pg_size_pretty(pg_total_relation_size('payments')) AS taille_avec_index FROM payments;

\echo
\echo '=== 5. Comptages de référence (à comparer entre la production et sa copie restaurée)'
SELECT donnees, valeur FROM (
              SELECT 1 AS n, 'organizations' AS donnees, count(*)::text AS valeur FROM organizations
    UNION ALL SELECT 2, 'schools', count(*)::text FROM schools
    UNION ALL SELECT 3, 'users', count(*)::text FROM users
    UNION ALL SELECT 4, 'user_roles', count(*)::text FROM user_roles
    UNION ALL SELECT 5, 'students', count(*)::text FROM students
    UNION ALL SELECT 6, 'student_fees', count(*)::text FROM student_fees
    UNION ALL SELECT 7, 'payments (toutes)', count(*)::text FROM payments
    UNION ALL SELECT 8, 'payments COMPLETED : nombre', count(*)::text FROM payments WHERE status = 'COMPLETED'
    UNION ALL SELECT 9, 'payments COMPLETED : somme', coalesce(sum(amount), 0)::text FROM payments WHERE status = 'COMPLETED'
    UNION ALL SELECT 10, 'notifications', count(*)::text FROM notifications
    UNION ALL SELECT 11, 'audit_logs', count(*)::text FROM audit_logs
) c ORDER BY n;
