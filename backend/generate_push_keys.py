"""Afficher une nouvelle paire VAPID à copier dans Render ; ne jamais la commiter."""
import base64
import secrets
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization

key = ec.generate_private_key(ec.SECP256R1())
encode = lambda b: base64.urlsafe_b64encode(b).rstrip(b'=').decode()
print('VAPID_PRIVATE_KEY=' + encode(key.private_numbers().private_value.to_bytes(32, 'big')))
print('VAPID_PUBLIC_KEY=' + encode(key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)))
print('CRON_SECRET=' + secrets.token_urlsafe(32))
