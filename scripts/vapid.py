#!/usr/bin/env python3
"""Clé de notifications (VAPID) dérivée du secret ALERT_SECRET : aucun secret de plus à gérer.
La clé privée n'existe qu'en mémoire pendant le passage du robot ; la clé publique est dans le site."""
import base64, hashlib, os
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization

N = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551  # ordre de la courbe P-256


def private_key(secret=None):
    s = (secret if secret is not None else os.environ.get("ALERT_SECRET", "")).strip()
    if len(s) < 32: raise ValueError("secret ALERT_SECRET absent ou trop court")
    d = int.from_bytes(hashlib.sha256(("le-brief-vapid:" + s).encode()).digest(), "big") % (N - 1) + 1
    return ec.derive_private_key(d, ec.SECP256R1())


def public_b64(key=None):
    key = key or private_key()
    raw = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


if __name__ == "__main__":
    print("VAPID_PUBLIC=" + public_b64())
