"""Tengeneza VAPID keys za Web Push.

Matumizi:
    python manage.py gen_vapid_keys

Weka matokeo kwenye environment ya production:
    VAPID_PUBLIC_KEY=...
    VAPID_PRIVATE_KEY=...
    VAPID_ADMIN_EMAIL=support@utumishi.go.tz

ONYO: Uki-regenerate keys, walimu wote waliojiandikisha watalazimika
kujiandikisha upya (subscriptions za zamani zitakoma kufanya kazi).
"""
import base64

from django.core.management.base import BaseCommand


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode()


class Command(BaseCommand):
    help = 'Tengeneza VAPID public/private keys kwa Web Push.'

    def handle(self, *args, **options):
        try:
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.asymmetric import ec
        except Exception as exc:  # pragma: no cover
            self.stderr.write('cryptography haipo: %s' % exc)
            return

        private = ec.generate_private_key(ec.SECP256R1())
        public = private.public_key()
        pub_bytes = public.public_bytes(
            serialization.Encoding.X962,
            serialization.PublicFormat.UncompressedPoint)
        priv_bytes = private.private_numbers().private_value.to_bytes(32, 'big')

        self.stdout.write('VAPID_PUBLIC_KEY=%s' % _b64(pub_bytes))
        self.stdout.write('VAPID_PRIVATE_KEY=%s' % _b64(priv_bytes))
        self.stdout.write('VAPID_ADMIN_EMAIL=support@utumishi.go.tz')
