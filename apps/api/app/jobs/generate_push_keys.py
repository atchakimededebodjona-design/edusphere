"""Génère la paire de clés VAPID des notifications téléphone (2026-11-17).

Usage sur le serveur (les lignes produites vont DIRECTEMENT dans le .env, jamais à l'écran) :

    docker compose run --rm --no-deps -T api python -m app.jobs.generate_push_keys >> .env

Si les clés existent déjà (variables présentes), rien n'est écrit sur la sortie standard : la commande
peut être relancée sans risque de doublon. La clé privée ne doit jamais être publiée ; la changer
obligerait chaque appareil à réactiver les notifications.
"""

import base64
import os
import sys

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def generate_key_pair() -> tuple[str, str]:
    """(clé publique, clé privée) au format attendu : point public non compressé (65 octets) et
    scalaire privé brut (32 octets), en base64url sans remplissage."""
    key = ec.generate_private_key(ec.SECP256R1())
    private_raw = key.private_numbers().private_value.to_bytes(32, "big")
    public_raw = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return _b64url(public_raw), _b64url(private_raw)


def main() -> int:
    if os.environ.get("WEB_PUSH_VAPID_PUBLIC_KEY", "").strip() or os.environ.get("WEB_PUSH_VAPID_PRIVATE_KEY", "").strip():
        print("Clés de notification déjà présentes : rien n'a été ajouté.", file=sys.stderr)
        return 0
    public_key, private_key = generate_key_pair()
    # Ligne vide d'abord : si le .env ne finit pas par un retour à la ligne, la première clé ne se
    # colle pas à la dernière ligne existante.
    print("")
    print("# Notifications téléphone (Web Push) — ne jamais publier la clé privée")
    print(f"WEB_PUSH_VAPID_PUBLIC_KEY={public_key}")
    print(f"WEB_PUSH_VAPID_PRIVATE_KEY={private_key}")
    print("Clés de notification générées et ajoutées.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
