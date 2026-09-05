# Pilot Readiness Checklist

Phase 18. Chaque élément est marqué **PASS** (vérifié réellement, avec preuve dans un rapport de
phase), **NOT VERIFIED** (jamais testé, ni positivement ni négativement), ou **BLOCKED**
(dépend d'une ressource externe non disponible). Aucun élément non testé n'est marqué PASS par
convenance — voir les rapports de phase cités pour la preuve exacte de chaque PASS.

## INFRASTRUCTURE

- [x] Docker — **PASS** (`docker compose build`/`up`/`ps` réellement exécutés cette phase,
      4/4 services `(healthy)`)
- [x] PostgreSQL — **PASS** (en service, migrations à jour, RLS testée)
- [x] Redis — **PASS** (en service, fail-open testé réellement — Phase 14/16)
- [x] Storage — **PASS** (bind mount persistant, testé réellement après recréation de
      conteneur — Phase 14)
- [x] Health — **PASS** (`GET /health` réel, `200`, testé cette phase)
- [x] Readiness — **PASS** (`GET /ready` réel, panne DB et Redis simulées et détectées,
      récupération observée — Phase 16)
- [x] Backups — **PASS** (PostgreSQL + storage, automatisés, Phase 15)
- [x] Restore — **PASS** (PostgreSQL et storage, restauration réelle testée à plusieurs
      reprises — Phases 15, 17)
- [ ] Backup externe (hors machine) — **PASS, avec réserve explicite** : mécanisme prouvé de
      bout en bout (copie + vérification SHA-256 + restauration depuis l'externe + simulation de
      perte de machine — Phase 17), mais **sur un disque appartenant à une autre personne, sur
      cette seule machine de développement** — pas une solution reproductible telle quelle en
      production. Une vraie destination externe de production reste à établir séparément avant
      un pilote réel.

## SECURITY

- [x] Secrets — **PASS** (audit réel Phase 18 : aucun secret dans le suivi Git, `.env` exclu,
      un seul motif de correspondance trouvé et identifié comme un placeholder dev connu, pas un
      secret réel)
- [x] JWT — **PASS** (implémenté, testé, timing side-channel corrigé — Phase 13)
- [x] RBAC — **PASS** (implémenté et testé extensivement depuis la Phase 1, audité à nouveau en
      Phase 13/14 — aucune fuite cross-tenant trouvée)
- [x] RLS — **PASS** (implémenté et testé depuis la Phase 1, audité à plusieurs reprises,
      `organizations` reste sans policy RLS dédiée — MEDIUM, documenté, non exploitable trouvé)
- [ ] Rate limiting — **PASS partiel** : login et mot de passe oublié testés réellement
      (Phases 7.2, 10.1). `register`/`refresh`/`verify-by-code` **NOT VERIFIED** — jamais
      protégés, gap MEDIUM connu depuis la Phase 13, jamais traité.
- [ ] HTTPS — **NOT VERIFIED** — aucun reverse proxy/terminaison TLS configuré
      (`infrastructure/nginx/` ne contient qu'un placeholder Phase 0), confirmé absent.
- [x] Logs — **PASS** (logging minimal réel, aucun secret trouvé dans les logs — Phase 16)

## EMAIL

- [x] EmailProvider — **PASS** (abstraction implémentée et testée — Phase 9, 16)
- [x] Configuration SMTP — **PASS** (mécanisme de sélection/validation/timeout testé
      réellement — Phase 16, avec un vrai socket TCP pour connexion refusée/timeout)
- [ ] Livraison externe réelle — **BLOCKED** — aucun compte SMTP réel disponible dans cet
      environnement (Phases 16, 17). `REAL EXTERNAL SMTP DELIVERY NOT VERIFIED`.

## APPLICATION

- [x] Authentication — **PASS** (Phase 1, durcie Phase 7.2/13)
- [x] Organization — **PASS** (Phase 1)
- [x] School — **PASS** (Phase 2)
- [x] Academic year — **PASS** (Phase 2)
- [x] Classes — **PASS** (Phase 2)
- [x] Students — **PASS** (Phase 3)
- [x] Teachers — **PASS** (rôle RBAC + écrans mobile enseignant, Phase 7)
- [x] Attendance — **PASS** (Phase 6, web + mobile)
- [x] Grades — **PASS** (Phase 4) — note : aucun garde-fou n'empêche une correction de note
      après publication d'un bulletin déjà envoyé (gap data integrity MEDIUM, documenté Phase 13,
      non traité)
- [x] Report cards — **PASS** (Phase 5, SSTI corrigé Phase 7.2, notification parent Phase 11)
- [x] Parent mobile — **PASS** (Phases 7, 7.1, résilience réseau Phase 12)

## TESTING

- [x] pytest — **PASS** (183/183, réexécuté réellement cette phase)
- [x] ruff — **PASS** (réexécuté réellement cette phase)
- [x] mypy — **PASS** (réexécuté réellement cette phase, 72 fichiers)
- [x] Web — **PASS** (lint + type-check + build, les 3 réexécutés réellement cette phase)
- [ ] Mobile — **PASS partiel** : type-check réexécuté réellement cette phase (0 erreur). Aucun
      test runtime n'existe pour le mobile (pas de Jest, confirmé Phase 12) et **aucune
      validation sur simulateur/appareil réel n'a jamais été faite** (Phase 12, GO WITH NOTES
      précisément pour cette raison, toujours vrai) — marqué **NOT VERIFIED** pour le
      comportement runtime, distinct du type-check qui lui est PASS.
- [x] Docker — **PASS** (`config`/`build`/`ps` réexécutés réellement cette phase)

## Résumé

Aucun `BLOCKED` ne concerne le code ou l'infrastructure du projet lui-même — les deux éléments
`BLOCKED`/`NOT VERIFIED` les plus significatifs (livraison SMTP réelle, validation mobile
runtime, HTTPS) dépendent soit d'une ressource externe non disponible dans cet environnement,
soit d'un environnement (simulateur, hébergement de production) qui n'existe pas encore ici — pas
d'un défaut de code découvert et non corrigé. Le rate limiting incomplet et l'absence de
garde-fou sur les notes après publication restent des dettes MEDIUM connues, documentées à
travers plusieurs phases, jamais traitées faute de priorité suffisante face à des risques plus
importants (voir Phases 13-15 pour la justification de chaque priorisation).
