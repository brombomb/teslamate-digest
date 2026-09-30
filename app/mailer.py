import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from typing import Dict, Any, List, Optional
from app.config import SMTPSettings


class Mailer:
    def __init__(self, smtp: SMTPSettings):
        self.smtp = smtp

    def send_email(
        self,
        subject: str,
        html_content: str,
        inline_images: Optional[Dict[str, bytes]] = None,
        recipient: Optional[str] = None
    ) -> bool:
        if not self.smtp.enabled:
            print("[Mailer] SMTP delivery is disabled in config.")
            return False

        if not self.smtp.password:
            print("[Mailer] SMTP password is empty. Cannot send email.")
            return False

        to_email = recipient or self.smtp.recipient_email
        msg = MIMEMultipart("related")
        msg["Subject"] = subject
        msg["From"] = f"{self.smtp.sender_name} <{self.smtp.sender_email}>"
        msg["To"] = to_email

        # HTML body
        msg_alternative = MIMEMultipart("alternative")
        msg.attach(msg_alternative)

        # Plaintext fallback
        text_content = f"{subject}\n\nPlease view this email in an HTML-compatible client."
        msg_alternative.attach(MIMEText(text_content, "plain"))
        msg_alternative.attach(MIMEText(html_content, "html"))

        # Inline CID attachments
        if inline_images:
            for cid, img_bytes in inline_images.items():
                img_part = MIMEImage(img_bytes)
                img_part.add_header("Content-ID", f"<{cid}>")
                img_part.add_header("Content-Disposition", "inline", filename=f"{cid}.png")
                msg.attach(img_part)

        try:
            if self.smtp.use_ssl:
                server = smtplib.SMTP_SSL(self.smtp.host, self.smtp.port, timeout=30)
            else:
                server = smtplib.SMTP(self.smtp.host, self.smtp.port, timeout=30)
                if self.smtp.use_tls:
                    server.starttls()

            server.login(self.smtp.user, self.smtp.password)
            server.sendmail(self.smtp.sender_email, [to_email], msg.as_string())
            server.quit()
            print(f"[Mailer] Successfully delivered digest to {to_email}")
            return True
        except Exception as e:
            print(f"[Mailer] Failed to send email via SMTP: {e}")
            raise e

    def verify_smtp(self) -> Dict[str, Any]:
        """Test SMTP connection and credentials"""
        try:
            if self.smtp.use_ssl:
                server = smtplib.SMTP_SSL(self.smtp.host, self.smtp.port, timeout=15)
            else:
                server = smtplib.SMTP(self.smtp.host, self.smtp.port, timeout=15)
                if self.smtp.use_tls:
                    server.starttls()

            if self.smtp.user and self.smtp.password:
                server.login(self.smtp.user, self.smtp.password)

            server.quit()
            return {"success": True, "message": "SMTP connection & authentication successful!"}
        except Exception as e:
            return {"success": False, "message": str(e)}
