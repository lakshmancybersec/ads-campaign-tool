import smtplib
import ssl
from email.message import EmailMessage
from app.config import get_settings
from app.services.meta_client import MetaError, configured


def validate_email():
    s = get_settings()
    if not all(configured(v) for v in (s.smtp_host, s.smtp_username, s.smtp_password, s.owner_email)):
        raise MetaError("Save SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD and OWNER_EMAIL in .env, then restart the application.")
    if s.smtp_port not in (465, 587):
        raise MetaError("Use SMTP port 587 (STARTTLS) or 465 (TLS).")
    if any('\n' in v or '\r' in v or '@' not in v for v in (s.smtp_username, s.owner_email)):
        raise MetaError("Configure valid sender and owner email addresses.")
    return s


def send_payment_email(message):
    s = validate_email()
    mail = EmailMessage()
    mail['Subject'] = 'Lakshiya Dhotis — approved campaign payment request'
    mail['From'] = s.smtp_username
    mail['To'] = s.owner_email
    mail.set_content(message)
    try:
        context = ssl.create_default_context()
        connection = (smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, timeout=20, context=context)
                      if s.smtp_port == 465 else smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=20))
        with connection as smtp:
            if s.smtp_port == 587:
                smtp.ehlo()
                smtp.starttls(context=context)
                smtp.ehlo()
            smtp.login(s.smtp_username, s.smtp_password.replace(' ', '') if s.smtp_host == 'smtp.gmail.com' else s.smtp_password)
            if smtp.send_message(mail):
                raise MetaError("Email recipient was refused.")
    except (smtplib.SMTPException, OSError):
        raise MetaError("Email sending was not confirmed. Check Gmail settings and Sent mail before retrying.") from None
