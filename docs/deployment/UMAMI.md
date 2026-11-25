# Mesure d'audience Umami — installation sur le serveur

Choix de l'exploitant (2026-11-24) : **Umami hébergé sur le serveur**, sans cookie, avec un bandeau de consentement.

Le site ne charge le script qu'après « Accepter », et seulement sur les pages publiques : l'accueil, la politique de confidentialité, les CGU et les CGV. L'espace connecté des écoles n'est jamais mesuré.

- **Version** : Umami 3.5.0 (12 novembre 2026). L'image `ghcr.io/umami-software/umami` est figée par son **empreinte** (`UMAMI_IMAGE=…@sha256:…`), relevée lors de l'installation.
- **Base de données** : une base `umami`, avec son propre rôle, dans le même PostgreSQL que l'application. Umami n'a aucun accès aux données des écoles.
- **Adresse** : `https://stats.edulinkage.com` (nginx et certificat Let's Encrypt). Le conteneur écoute sur `127.0.0.1:3010`.
- **Secrets** : `UMAMI_DB_PASSWORD` et `UMAMI_APP_SECRET` sont générés sur le serveur, dans `.env`, et jamais affichés.

## Étapes (console du serveur, en root, dans /opt/edusphere)

1. **DNS** (hPanel, Domaines, edulinkage.com, Zone DNS) : ajouter un enregistrement `A`, nom `stats`, valeur `82.25.116.196`.
2. **Secrets et image** : ajouter à `.env` deux secrets aléatoires et l'empreinte de l'image téléchargée.
3. **Base** : créer le rôle `umami` avec ce mot de passe, puis la base `umami` qui lui appartient.
4. **Démarrage** : `docker compose --profile analytics up -d umami`, puis attendre que `http://127.0.0.1:3010/api/heartbeat` réponde.
5. **nginx et certificat** : un bloc `server` pour `stats.edulinkage.com`, mandataire vers `127.0.0.1:3010`, puis `certbot --nginx -d stats.edulinkage.com`.
6. **Premier accès** (`https://stats.edulinkage.com`) :
   - connexion avec `admin` / `umami` ;
   - **changement immédiat du mot de passe** (Umami 3.5 l'exige) ;
   - ajout du site `edulinkage.com` ;
   - copie de son identifiant (UUID).
7. **Site** : ajouter à `.env` `NEXT_PUBLIC_UMAMI_SRC=https://stats.edulinkage.com/script.js` et `NEXT_PUBLIC_UMAMI_WEBSITE_ID=<UUID>`, puis reconstruire le site (`docker compose build web`). La CSP s'ouvre alors à cette seule origine.

Les commandes exactes sont données à l'exploitant au moment de l'installation, avec des vérifications à chaque étape.

## Retour en arrière

- Retirer les deux lignes `NEXT_PUBLIC_UMAMI_*` de `.env` et reconstruire le site : plus de bandeau ni de script.
- Puis `docker compose --profile analytics stop umami`.
