import socket
from django.core.mail.backends.smtp import EmailBackend


class IPv4EmailBackend(EmailBackend):
    """Force IPv4 connection to SMTP server - fixes Railway IPv6 issue."""

    def open(self):
        original_getaddrinfo = socket.getaddrinfo

        def ipv4_only(host, port, *args, **kwargs):
            results = original_getaddrinfo(host, port, socket.AF_INET, *args[1:], **kwargs)
            if results:
                return results
            return original_getaddrinfo(host, port, *args, **kwargs)

        socket.getaddrinfo = ipv4_only
        try:
            result = super().open()
        finally:
            socket.getaddrinfo = original_getaddrinfo
        return result
