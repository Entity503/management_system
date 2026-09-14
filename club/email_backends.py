import smtplib
import sys
from email.mime.base import MIMEBase

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend
from django.core.mail.backends.console import EmailBackend as _ConsoleBackend


class ResendBackend(BaseEmailBackend):
    """
    Django 邮件后端，通过 Resend HTTP API 发送邮件。
    PythonAnywhere 免费版封了 SMTP 端口，但 HTTP 443 端口开放，所以 Resend 能发。
    依赖：pip install resend
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            import resend
        except ImportError as e:
            raise ImportError(
                "ResendBackend 需要 resend SDK，请先执行: pip install resend"
            ) from e
        self._resend = resend
        self._resend.api_key = settings.RESEND_API_KEY

    def send_messages(self, email_messages):
        count = 0
        for message in email_messages:
            try:
                self._send_one(message)
                count += 1
            except Exception as exc:
                if not self.fail_silently:
                    raise
                sys.stderr.write(f"[Resend] 发送失败: {exc}\n")
        return count

    def _send_one(self, message):
        from_email = settings.DEFAULT_FROM_EMAIL
        if hasattr(message, "from_email") and message.from_email:
            from_email = message.from_email

        payload = {
            "from": from_email,
            "to": list(message.to or []),
            "subject": message.subject,
            "text": message.body,
        }

        reply_to = getattr(message, "reply_to", None)
        if reply_to:
            payload["reply_to"] = list(reply_to)

        cc = getattr(message, "cc", None)
        if cc:
            payload["cc"] = list(cc)

        bcc = getattr(message, "bcc", None)
        if bcc:
            payload["bcc"] = list(bcc)

        attachments = getattr(message, "attachments", None)
        if attachments:
            payload["attachments"] = [
                {"filename": name, "content": content, "type": mimetype}
                for name, content, mimetype in attachments
            ]

        self._resend.Emails.send(payload)


class PlainConsoleBackend(_ConsoleBackend):
    """
    Console 邮件后端，直接输出明文，方便开发调试。
    Django 默认的 console backend 会把中文邮件内容 base64 编码，
    每次查验证码都要解码，太麻烦。这个版本直接打印可读文本。
    """

    def write_message(self, message):
        msg = (
            "-------------------------------------------------------------------------------\n"
            f"Subject: {message.subject}\n"
            f"From: {message.from_email}\n"
            f"To: {', '.join(message.to)}\n"
            f"Date: {message.date}\n"
            "-------------------------------------------------------------------------------\n"
            f"{message.body}\n"
            "-------------------------------------------------------------------------------\n"
        )
        print(msg, file=self.stream)