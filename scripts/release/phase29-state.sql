-- Phase 29 — ÉTAT des données d'abonnement et de caisse (lecture seule, aucune écriture possible).
-- Voir docs/deployment/PHASE_29_PRODUCTION_RUNBOOK.md, étapes 4, 6, 9 et 10.
--
-- Usage, sur le serveur, depuis le répertoire du déploiement (base à la révision 0028) :
--   docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -X -v ON_ERROR_STOP=1 -f -' \
--     < scripts/release/phase29-state.sql
--
-- Sert à suivre le premier passage des tâches planifiées, puis à décider d'un éventuel retour
-- arrière (section 10 du runbook) : il dit si des données réelles existent déjà.

\set QUIET on
SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY;
\pset footer off

\echo
\echo '=== 1. Écoles et trimestres gratuits'
SELECT (SELECT count(*) FROM schools) AS ecoles,
       (SELECT count(*) FROM school_subscription_periods WHERE kind = 'FREE_TRIAL') AS trimestres_gratuits,
       (SELECT count(*) FROM schools s WHERE NOT EXISTS (
            SELECT 1 FROM school_subscription_periods p
            WHERE p.school_id = s.id AND p.kind = 'FREE_TRIAL')) AS ecoles_sans_trimestre,
       (SELECT count(*) FROM school_subscription_periods WHERE kind = 'PAID') AS periodes_payees;

\echo
\echo '=== 2. Trimestres gratuits par dates (20 premières lignes)'
SELECT starts_on AS debut, ends_on AS fin, count(*) AS ecoles
FROM school_subscription_periods WHERE kind = 'FREE_TRIAL'
GROUP BY 1, 2 ORDER BY 1, 2 LIMIT 20;

\echo
\echo '=== 3. Grilles de prix'
SELECT g.label, g.status, g.activated_at,
       (SELECT count(*) FROM subscription_price_lines l WHERE l.grid_id = g.id) AS lignes
FROM subscription_price_grids g ORDER BY g.created_at;

\echo
\echo '=== 4. Factures et paiements d''abonnement'
SELECT 'facture' AS objet, status AS statut, count(*) AS nombre, coalesce(sum(total_amount), 0) AS montant
FROM subscription_invoices GROUP BY status
UNION ALL
SELECT 'paiement', provider || ' / ' || status, count(*), coalesce(sum(amount), 0)
FROM subscription_payments GROUP BY provider, status
ORDER BY 1, 2;

\echo
\echo '=== 5. Rappels envoyés par palier'
SELECT stage AS palier, count(*) AS rappels, coalesce(sum(recipients_count), 0) AS destinataires
FROM subscription_reminders GROUP BY stage ORDER BY stage;

\echo
\echo '=== 6. Notifications d''abonnement (une API antérieure à la Phase 29 ne sait pas les afficher)'
SELECT type, count(*) AS nombre FROM notifications WHERE type LIKE 'SUBSCRIPTION\_%' GROUP BY type ORDER BY type;
SELECT count(*) AS total_notifications_abonnement FROM notifications WHERE type LIKE 'SUBSCRIPTION\_%';

\echo
\echo '=== 7. Caisse (lots 1 à 3)'
SELECT (SELECT count(*) FROM user_roles ur JOIN roles r ON r.id = ur.role_id WHERE r.code = 'CAISSIER') AS comptes_caissier,
       (SELECT count(*) FROM cash_sessions) AS sessions,
       (SELECT count(*) FROM cash_movements) AS mouvements,
       (SELECT count(*) FROM cash_counts) AS comptages,
       (SELECT count(*) FROM payments WHERE cash_session_id IS NOT NULL) AS paiements_rattaches;
