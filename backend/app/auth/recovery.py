import logging
import os
import secrets
import smtplib
import ssl
from email.message import EmailMessage
from urllib.parse import urlencode

from fastapi import HTTPException

from app.auth.security import digest, hasher, identity_active
from app.auth.store import audit, execute, identity_query, revoke_reset_tokens, revoke_sessions, row


logger = logging.getLogger(__name__)


def mail_enabled() -> bool:
    return bool(os.getenv("SKNET_SMTP_HOST") and os.getenv("SKNET_SMTP_FROM"))


def send_access_link(recipient, origin, token, purpose):
    verification = purpose == "verify"
    url = f"{origin}/recover#{urlencode({'token': token, 'purpose': purpose})}"
    message = EmailMessage()
    message["From"] = os.environ["SKNET_SMTP_FROM"]
    message["To"] = recipient
    message["Subject"] = "Confirma tu correo en SKNet" if verification else "Recupera tu acceso a SKNet"
    action = "confirmar tu dirección" if verification else "elegir una nueva contraseña"
    message.set_content(f"Usa este enlace para {action}. Expira en 30 minutos.\n\n{url}\n")
    try:
        context = ssl.create_default_context()
        port = int(os.getenv("SKNET_SMTP_PORT", "587"))
        host = os.environ["SKNET_SMTP_HOST"]
        connection = smtplib.SMTP_SSL(host, port, timeout=8, context=context) if port == 465 else (
            smtplib.SMTP(host, port, timeout=8)
        )
        with connection as smtp:
            if port != 465:
                smtp.starttls(context=context)
            if username := os.getenv("SKNET_SMTP_USER"):
                smtp.login(username, os.environ["SKNET_SMTP_PASSWORD"])
            smtp.send_message(message)
    except (OSError, ValueError, KeyError, smtplib.SMTPException):
        logger.warning("No se pudo entregar un mensaje de acceso de SKNet.")


def issue_link(db, user_id, purpose):
    token = secrets.token_urlsafe(32)
    execute(db, """
        UPDATE core.password_reset_tokens SET revoked_at = now()
        WHERE user_id = :user AND purpose = :purpose AND revoked_at IS NULL AND used_at IS NULL
    """, user=user_id, purpose=purpose)
    execute(db, """
        INSERT INTO core.password_reset_tokens(user_id, token_hash, purpose, expires_at)
        VALUES (:user, :hash, :purpose, now() + interval '30 minutes')
    """, user=user_id, hash=digest(token), purpose=purpose)
    return token


def consume_link(db, realm, token, purpose, password=None):
    record = row(db, """
        SELECT t.id, t.user_id FROM core.password_reset_tokens t JOIN core.users u ON u.id = t.user_id
        WHERE t.token_hash = :hash AND t.purpose = :purpose AND t.used_at IS NULL AND t.revoked_at IS NULL
          AND t.expires_at > now() AND u.account_scope = :scope
    """, hash=digest(token), purpose=purpose, scope=realm.code)
    user = row(db, identity_query(realm) + " AND u.id = :id", id=record["user_id"], scope=realm.code) if record else None
    if not identity_active(user):
        raise HTTPException(400, "El enlace no es válido o ha expirado.")
    execute(db, "UPDATE core.password_reset_tokens SET used_at = now() WHERE id = :id", id=record["id"])
    execute(db, "UPDATE core.users SET email_verified_at = now(), updated_at = now() WHERE id = :id",
            id=user["id"])
    if password is not None:
        execute(db, """
            UPDATE core.users SET password_hash = :hash, must_change_password = false,
                temporary_password_expires_at = NULL, temporary_password_used_at = NULL
            WHERE id = :id
        """, hash=hasher.hash(password), id=user["id"])
        revoke_sessions(db, user["id"])
        revoke_reset_tokens(db, user["id"])
    audit(db, "password.recover" if password is not None else "email.verify", "user", user["id"],
          actor=user["id"], company=user["company_id"])
