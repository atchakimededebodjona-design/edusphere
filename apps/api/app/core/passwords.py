"""Règle unique d'un NOUVEAU mot de passe (2026-11-17, revue de sécurité).

Avant : 8 caractères minimum, sans autre contrôle. Désormais, pour tout mot de passe choisi
(réinitialisation, premier administrateur d'une organisation ou d'une école) :
- 12 à 128 caractères ;
- ni un mot de passe très courant, ni un seul caractère répété.

Les mots de passe existants ne sont pas touchés : la règle s'applique au prochain changement. Depuis la
connexion sans internet (le mot de passe protège aussi les données gardées sur l'appareil), la
longueur compte encore plus.
"""

from typing import Annotated

from pydantic import AfterValidator, Field

PASSWORD_MIN_LENGTH = 12
PASSWORD_MAX_LENGTH = 128

# Mots de passe parmi les plus essayés par les robots (formes de 12 caractères et plus), et variantes
# évidentes du nom du service. Comparaison sans tenir compte des majuscules.
_COMMON_PASSWORDS = frozenset(
    {
        "123456789012",
        "1234567890123",
        "12345678901234",
        "123456123456",
        "000000000000",
        "azertyuiop12",
        "azertyuiop123",
        "azertyuiopqs",
        "qwertyuiop12",
        "qwertyuiop123",
        "qwertyuiopas",
        "password1234",
        "password12345",
        "passwordpassword",
        "motdepasse12",
        "motdepasse123",
        "motdepasse1234",
        "motdepasseadmin",
        "administrateur",
        "administrator",
        "edulinkage123",
        "edulinkage2026",
        "edulinkage2027",
        "edulinkage1234",
        "edusphere123",
        "edusphere2026",
        "bienvenue1234",
        "bienvenue2026",
        "iloveyou1234",
        "abcdefghijkl",
        "abcd1234abcd",
    }
)


def password_problem(password: str) -> str | None:
    """Raison pour laquelle `password` est refusé comme nouveau mot de passe, ou None."""
    if not PASSWORD_MIN_LENGTH <= len(password) <= PASSWORD_MAX_LENGTH:
        return f"The password must contain {PASSWORD_MIN_LENGTH} to {PASSWORD_MAX_LENGTH} characters"
    if len(set(password)) == 1 or password.lower() in _COMMON_PASSWORDS:
        return "This password is too common: choose another one"
    return None


def _check_new_password(password: str) -> str:
    problem = password_problem(password)
    if problem:
        raise ValueError(problem)
    return password


# Champ de schéma pour un nouveau mot de passe (422 en cas de refus).
NewPassword = Annotated[str, Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH), AfterValidator(_check_new_password)]
