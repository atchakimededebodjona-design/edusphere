-- Vérification post-restauration (Phase 7.3) — comptage des tables métier clés.
-- Utilisé par scripts/db-restore-test.sh pour confirmer que la base restaurée contient
-- des données cohérentes avec la base source (pas de comparaison exacte automatisée ici :
-- la comparaison des nombres avec la base source se fait manuellement lors du test).
SELECT 'organizations' AS table_name, count(*) FROM organizations
UNION ALL SELECT 'schools', count(*) FROM schools
UNION ALL SELECT 'users', count(*) FROM users
UNION ALL SELECT 'students', count(*) FROM students
UNION ALL SELECT 'assessment_results', count(*) FROM assessment_results
UNION ALL SELECT 'attendance_records', count(*) FROM attendance_records
UNION ALL SELECT 'report_cards', count(*) FROM report_cards
ORDER BY table_name;
