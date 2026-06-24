"""
Gmail API email sender — uses OAuth2 refresh token (HTTPS port 443).
Works on Railway (no SMTP port restrictions).
"""
import base64
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from django.conf import settings

logger = logging.getLogger(__name__)


def _get_gmail_service():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    creds = Credentials(
        token=None,
        refresh_token=settings.GMAIL_REFRESH_TOKEN,
        client_id=settings.GMAIL_CLIENT_ID,
        client_secret=settings.GMAIL_CLIENT_SECRET,
        token_uri='https://oauth2.googleapis.com/token',
        scopes=['https://www.googleapis.com/auth/gmail.send'],
    )
    # Auto-refresh access token
    creds.refresh(Request())
    return build('gmail', 'v1', credentials=creds, cache_discovery=False)


def send_email_via_gmail_api(to: str, subject: str, html_body: str, text_body: str = '') -> None:
    """Send email using Gmail API. Raises on failure."""
    sender = getattr(settings, 'EMAIL_HOST_USER', '')

    msg = MIMEMultipart('alternative')
    msg['to'] = to
    msg['from'] = f'IMS System <{sender}>'
    msg['subject'] = subject

    if text_body:
        msg.attach(MIMEText(text_body, 'plain', 'utf-8'))
    msg.attach(MIMEText(html_body, 'html', 'utf-8'))

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()

    service = _get_gmail_service()
    service.users().messages().send(userId='me', body={'raw': raw}).execute()
    logger.info(f'Gmail API: email sent to {to}')


def gmail_api_available() -> bool:
    """Returns True if Gmail API credentials are configured."""
    return bool(
        getattr(settings, 'GMAIL_CLIENT_ID', '') and
        getattr(settings, 'GMAIL_CLIENT_SECRET', '') and
        getattr(settings, 'GMAIL_REFRESH_TOKEN', '')
    )
