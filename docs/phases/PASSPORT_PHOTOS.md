# Photos d'identité — enseignants et élèves

- **Demande** (2026-11-19) : « la photo passeport dans l'espace enseignant pour les enseignants et aussi pour les élèves ».
- **Choix de l'exploitant** :
  - **élèves** : l'enseignant **voit** la photo de ses élèves ; seule l'administration la met, comme avant ;
  - **enseignant** : il met sa photo lui-même (« Mon profil »), et l'administration peut aussi la mettre ;
  - **prise de vue** : les deux façons, appareil photo avec cadrage passeport, ou fichier déjà prêt.
- **Migration** `0036` : `users.photo_path`. Les élèves avaient déjà `students.photo_path` (Phase 3).

## 1. Mettre une photo

Partout où l'on met une photo, deux boutons sont proposés (`components/photos/PassportPhotoPicker.tsx`).

- **« 📷 Prendre une photo »** ouvre l'appareil photo du téléphone. Sur ordinateur, c'est un choix de fichier.
  - Une fenêtre de **cadrage au format passeport (35 × 45)** s'ouvre, avec un ovale pour le visage.
  - On fait glisser la photo et on l'agrandit avec « Zoom ».
  - « Valider la photo » envoie la partie cadrée, en JPEG de 700 × 900 pixels. « Reprendre » et « Annuler » sont aussi proposés.
- **« Choisir un fichier »** envoie une image déjà prête **telle quelle** : JPEG, PNG ou WebP, 5 Mio au plus.
  - Le site vérifie le fichier avant l'envoi, et l'API refuse tout ce qui n'est pas une vraie image.
- Le calcul du cadrage est dans `lib/photos/passport.mjs` et testé par `passport.test.mjs`. L'image couvre toujours le cadre, sans bord vide, et le zoom garde le même point au centre.

## 2. Où elle apparaît

**Espace enseignant :**
- **« Mon profil »** : sa photo (ou ses initiales), les deux boutons et « Retirer ma photo ».
  - À l'ouverture, le profil reprend l'état du serveur : une photo mise entre-temps par l'administration apparaît sans se reconnecter.
- **En-tête** : sa photo à côté de son nom ; elle mène à « Mon profil ». Elle change aussitôt après un envoi ou un retrait, sans recharger la page.
- **« Mes élèves »** :
  - une vignette par élève (photo ou initiales), chargée seulement quand elle devient visible ;
  - sur téléphone, le matricule passe sous le nom pour que la liste tienne dans l'écran.
- **Fiche élève** : la photo en grand. **Aucun bouton** : l'enseignant voit seulement.

**Administration :**
- **« Utilisateurs »** : une vignette par membre du personnel, et un bouton « Photo » qui ouvre un panneau avec les deux boutons et « Retirer la photo ». La caméra arrière est utilisée, puisque l'administration photographie la personne.
- **Fiche élève** : les deux boutons remplacent l'ancien « Changer la photo ». « Supprimer la photo » reste.

**Hors connexion** : une photo déjà vue avec internet reste affichable sans réseau. C'est la copie que `apiFetch` garde déjà pour chaque lecture.

## 3. API

**Sa propre photo** (tout compte connecté) :
- `POST /api/v1/auth/me/photo` (fichier) ;
- `GET /api/v1/auth/me/photo` ;
- `DELETE /api/v1/auth/me/photo`.

**Photo d'un membre du personnel** (administration de l'école) :
- `POST /api/v1/users/{id}/photo` (formulaire : `school_id`, fichier) ;
- `GET /api/v1/users/{id}/photo?school_id=…` ;
- `DELETE /api/v1/users/{id}/photo?school_id=…`.

**Indication de photo** : `has_photo` est ajouté au compte (`/auth/me`, liste des utilisateurs, `/teacher/me`) et aux élèves de l'espace enseignant (`/teacher/students`, `/teacher/classes/{id}/students`, `/teacher/students/{id}`).

**Inchangé** : la photo élève (`/students/{id}/photo`). L'enseignant la lit seulement pour les élèves de ses classes.

## 4. Garde-fous

- **Formats** : ceux de la photo élève (`validate_photo_upload`). L'API ouvre réellement l'image avant de la garder.
- **Personnel** : `users.read` pour lire, `users.manage` pour mettre ou retirer.
  - Le compte doit appartenir au personnel de **cette** école, au même sens que la liste des utilisateurs ; sinon 404, sans révéler s'il existe ailleurs.
  - Pour modifier, l'administrateur doit couvrir tous les rôles du compte (sinon 409) : mêmes règles que la modification d'un compte (`load_school_member`).
  - Son propre compte reste modifiable : une photo n'ouvre aucun droit.
- **Remplacement sûr** : le nouveau fichier est référencé avant l'effacement de l'ancien. Un échec ne laisse jamais un compte sans photo, au pire un fichier orphelin, signalé dans les journaux.
- **Lecture** : `Cache-Control: private, no-store`, c'est une donnée personnelle.
- **Suppression d'un compte par la plateforme** : sa photo est effacée avec ses autres données personnelles (`platform/accounts.py`).

## 5. Vérifications (2026-11-19 et 2026-11-22)

- **Migration** `0036` appliquée, annulée, puis réappliquée sur PostgreSQL 16.
- **API** : 6 tests (`tests/test_user_photos.py`).
  - Sa photo : mise, lecture, remplacement (ancien fichier effacé), retrait, retrait répété sans erreur ; fichiers refusés (faux JPEG, PDF, GIF) ; refus sans session.
  - Personnel : photo mise et retirée par l'administration ; l'enseignant la retrouve dans son espace.
  - Personnel : refusé pour un enseignant, pour une autre école et pour un compte inconnu.
  - Élèves : indications `has_photo` dans les listes et la fiche de l'enseignant, lecture permise, envoi et retrait refusés.
  - Suppression d'un compte : photo effacée.
- **Site** : vérification des types, analyse du code, `test:config` (25 tests, dont 5 pour le cadrage).
- **Parcours de bout en bout** : build de production, **vraie API** sur PostgreSQL, Chromium, téléphone et ordinateur. 29 vérifications :
  - fichier refusé ; fichier envoyé tel quel (600 × 800) ; profil et en-tête mis à jour aussitôt ;
  - cadrage au format 35 × 45, zoom, déplacement, photo finale en JPEG 700 × 900 ;
  - retrait ;
  - vignettes des élèves (avec et sans photo), fiche sans bouton, lien « Fiche » visible sur téléphone, pas de défilement horizontal ;
  - photo de l'enseignant mise par l'administration et retrouvée dans son espace ;
  - photo d'un élève cadrée par l'administration ;
  - aucune erreur de page ni de politique de contenu (CSP).
- **Non-régression** : bandeaux du bas, appel et notes hors connexion, connexion sans internet, consultation hors connexion, annonces, CSP des pages enseignant et administration.
