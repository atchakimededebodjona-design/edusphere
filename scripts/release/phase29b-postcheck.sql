-- Phase 29, lot B — contrôle de STRUCTURE après la migration 0029 (lecture seule, aucune écriture).
-- Voir docs/phases/PHASE_29_LOT_B_IMPLEMENTATION.md, §8.
--
-- Usage, sur le serveur, depuis le répertoire du déploiement :
--   docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -X -v ON_ERROR_STOP=1 -f -' \
--     < scripts/release/phase29b-postcheck.sql
--
-- Toutes les lignes doivent être OK. La structure des migrations 0024 à 0028 reste contrôlée par
-- scripts/release/phase29-postcheck.sql (dont la ligne « Révision Alembic » attend 0028 : après 0029,
-- seule cette ligne-là y est KO, ce qui est normal).

\set QUIET on
SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY;
\pset footer off

WITH
callbacks AS (SELECT to_regclass('payment_provider_callbacks') AS oid),
checks(n, controle, attendu, obtenu) AS (
              SELECT 1, 'Révision Alembic', '0029', (SELECT string_agg(version_num, ',') FROM alembic_version)
    UNION ALL SELECT 2, 'Table payment_provider_callbacks présente', 'true',
        (SELECT (oid IS NOT NULL)::text FROM callbacks)
    UNION ALL SELECT 3, 'Contraintes (CHECK / PK / FK)', '2 CHECK / 1 PK / 1 FK',
        (SELECT format('%s CHECK / %s PK / %s FK',
                       count(*) FILTER (WHERE contype = 'c'), count(*) FILTER (WHERE contype = 'p'),
                       count(*) FILTER (WHERE contype = 'f'))
         FROM pg_constraint WHERE conrelid = (SELECT oid FROM callbacks))
    UNION ALL SELECT 4, 'Index attendus présents', '2',
        (SELECT count(*)::text FROM unnest(ARRAY['ix_payment_provider_callbacks_received',
                                               'ix_payment_provider_callbacks_payment']) AS i
         WHERE to_regclass(i) IS NOT NULL)
    UNION ALL SELECT 5, 'RLS activée ET forcée', 'true',
        (SELECT (relrowsecurity AND relforcerowsecurity)::text FROM pg_class WHERE oid = (SELECT oid FROM callbacks))
    UNION ALL SELECT 6, 'Policies sur la table (plateforme seulement)', 'payment_provider_callbacks_platform_only',
        (SELECT string_agg(policyname, ', ' ORDER BY policyname COLLATE "C") FROM pg_policies
         WHERE schemaname = 'public' AND tablename = 'payment_provider_callbacks')
    UNION ALL SELECT 7, 'Droits edusphere_app (SELECT/INSERT/UPDATE/DELETE, testés un par un)', '4',
        (SELECT count(*)::text FROM callbacks, unnest(ARRAY['SELECT', 'INSERT', 'UPDATE', 'DELETE']) AS priv
         WHERE oid IS NOT NULL AND has_table_privilege('edusphere_app', oid, priv))
)
SELECT n AS "#", CASE WHEN attendu = obtenu THEN 'OK' ELSE 'KO' END AS resultat, controle,
       attendu, coalesce(obtenu, '(absent)') AS obtenu
FROM checks
ORDER BY n;
