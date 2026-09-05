"""Tests de sécurité — Phase 13, HIGH #2 (canal de fuite temporelle sur /auth/login et
/auth/forgot-password).

Conformément à la consigne de cette phase, ces tests ne mesurent PAS de latence murale (un
micro-benchmark local est trop bruité pour prouver quoi que ce soit de fiable sur une seule
machine/CI, et ne doit jamais servir à affirmer qu'un timing leak est "résolu définitivement").
Ils vérifient à la place les deux propriétés que le correctif garantit réellement :

1. **Parité fonctionnelle** : les réponses externes (code HTTP, forme du corps) sont identiques
   entre un compte inexistant et un compte existant avec un mauvais mot de passe (déjà vrai avant
   cette phase, reconfirmé ici comme garde non-régression).
2. **Parité de travail effectué** : le même nombre d'opérations coûteuses (vérification bcrypt
   pour le login, génération+hachage de token pour forgot-password) est exécuté dans les deux
   branches — c'est la propriété que Phase 13 a réellement changée (avant, la branche "compte
   inexistant" court-circuitait ce travail), et qui réduit concrètement l'écart de latence.
"""

import app.modules.auth.service as auth_service_module
from httpx import AsyncClient

from app.core.config import settings
from tests.conftest import register_school, unique_email


async def test_login_unknown_email_and_wrong_password_return_identical_response(client: AsyncClient) -> None:
    data = await register_school(client, "timingshape")
    email = data["user"]["email"]

    unknown = await client.post(
        "/api/v1/auth/login", json={"email": unique_email("ghost.timingshape"), "password": "whatever123"}
    )
    wrong_password = await client.post("/api/v1/auth/login", json={"email": email, "password": "WrongPassword"})

    assert unknown.status_code == wrong_password.status_code == 401
    assert unknown.json() == wrong_password.json()


async def test_login_unknown_and_wrong_password_perform_the_same_number_of_bcrypt_verifications(
    client: AsyncClient, monkeypatch
) -> None:
    """Preuve directe de la correction Phase 13 : avant le correctif, `verify_password` n'était
    jamais appelé pour un compte inexistant (court-circuit `user is None or ...`), mais exactement
    une fois pour un mauvais mot de passe sur un compte existant — l'écart de coût bcrypt
    (~100ms) était le signal exploitable. Ce test constate que les deux branches appellent
    désormais `verify_password` exactement une fois chacune."""
    calls: list[None] = []
    original_verify_password = auth_service_module.verify_password

    def counting_verify_password(password: str, hashed: str) -> bool:
        calls.append(None)
        return original_verify_password(password, hashed)

    monkeypatch.setattr(auth_service_module, "verify_password", counting_verify_password)

    data = await register_school(client, "timingcalls")
    email = data["user"]["email"]

    calls.clear()
    unknown = await client.post(
        "/api/v1/auth/login", json={"email": unique_email("ghost.timingcalls"), "password": "whatever123"}
    )
    assert unknown.status_code == 401
    calls_for_unknown = len(calls)

    calls.clear()
    wrong_password = await client.post("/api/v1/auth/login", json={"email": email, "password": "WrongPassword"})
    assert wrong_password.status_code == 401
    calls_for_wrong_password = len(calls)

    assert calls_for_unknown == calls_for_wrong_password == 1


async def test_login_valid_credentials_still_authenticate(client: AsyncClient) -> None:
    """Non-régression explicite : le chemin nominal (compte actif, bon mot de passe) doit
    continuer à réussir exactement comme avant ce correctif."""
    data = await register_school(client, "timingvalid")
    email = data["user"]["email"]

    response = await client.post("/api/v1/auth/login", json={"email": email, "password": "SuperSecret123"})
    assert response.status_code == 200
    assert response.json()["access_token"]


async def test_forgot_password_unknown_and_known_email_return_identical_response_shape(client: AsyncClient) -> None:
    unknown = await client.post("/api/v1/auth/forgot-password", json={"email": unique_email("ghost.fpshape")})
    assert unknown.status_code == 202
    assert unknown.json()["dev_token"] is None

    data = await register_school(client, "fpshapeknown")
    known = await client.post("/api/v1/auth/forgot-password", json={"email": data["user"]["email"]})
    assert known.status_code == 202
    # Seul le contenu du token diffère (comportement de dev déjà existant, hors production) —
    # jamais la forme de la réponse elle-même.
    assert set(unknown.json().keys()) == set(known.json().keys())


async def test_forgot_password_unknown_and_known_email_perform_the_same_number_of_token_generations(
    client: AsyncClient, monkeypatch
) -> None:
    """Même principe que pour le login : avant Phase 13, un email inexistant retournait avant
    toute génération de token ; un email existant en générait un (+ hachage + écriture en base).
    Ce test constate la parité désormais introduite sur la partie CPU de ce travail (génération de
    token) — voir le rapport d'implémentation pour la part NON équilibrée (écriture en base,
    envoi d'email), documentée comme limitation résiduelle assumée."""
    calls: list[None] = []
    original_generate = auth_service_module.generate_opaque_token

    def counting_generate() -> str:
        calls.append(None)
        return original_generate()

    monkeypatch.setattr(auth_service_module, "generate_opaque_token", counting_generate)

    calls.clear()
    unknown = await client.post("/api/v1/auth/forgot-password", json={"email": unique_email("ghost.fpcalls")})
    assert unknown.status_code == 202
    calls_for_unknown = len(calls)

    data = await register_school(client, "fpcallsknown")
    calls.clear()
    known = await client.post("/api/v1/auth/forgot-password", json={"email": data["user"]["email"]})
    assert known.status_code == 202
    calls_for_known = len(calls)

    assert calls_for_unknown == calls_for_known == 1


async def test_forgot_password_rate_limiting_still_works(client: AsyncClient) -> None:
    """Non-régression explicite : la limitation de débit Phase 10.1 (3 tentatives/15 min par
    email) n'a pas été affectée par ce correctif."""
    email = unique_email("ghost.fpratelimit")
    for _ in range(settings.forgot_password_rate_limit_max_attempts):
        response = await client.post("/api/v1/auth/forgot-password", json={"email": email})
        assert response.status_code == 202

    limited = await client.post("/api/v1/auth/forgot-password", json={"email": email})
    assert limited.status_code == 429
