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
            raise ValueError("SMTP delivery is disabled in Settings.")

        if not self.smtp.password:
            raise ValueError("SMTP password is empty. Please enter your Gmail App Password in Settings.")

        sender_addr = (self.smtp.sender_email or "").strip() or (self.smtp.user or "").strip()
        if not sender_addr:
            raise ValueError("Sender email is missing. Please configure Sender Email or SMTP Username in Settings.")

        to_email = recipient or self.smtp.recipient_email
        if not to_email:
            raise ValueError("Recipient email is empty. Please configure Primary Recipient in Settings.")

        safe_subject = str(subject).replace("\r", " ").replace("\n", " ").strip()
        safe_sender_name = str(self.smtp.sender_name).replace("\r", "").replace("\n", "").strip()
        safe_sender_addr = str(sender_addr).replace("\r", "").replace("\n", "").strip()
        safe_to_email = str(to_email).replace("\r", "").replace("\n", "").strip()

        msg = MIMEMultipart("related")
        msg["Subject"] = safe_subject
        msg["From"] = f"{safe_sender_name} <{safe_sender_addr}>"
        msg["To"] = safe_to_email

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

            if self.smtp.user and self.smtp.password:
                server.login(self.smtp.user, self.smtp.password)
            server.sendmail(safe_sender_addr, [safe_to_email], msg.as_string())
            server.quit()
            print(f"[Mailer] Successfully delivered digest to {safe_to_email}")
            return True
        except Exception as e:
            print(f"[Mailer] Failed to send email via SMTP: {e}")
            raise e

    def verify_smtp(self) -> Dict[str, Any]:
        """Test SMTP connection and credentials"""
        try:
            if not self.smtp.host:
                return {"success": False, "message": "SMTP host is empty. Please enter an SMTP server."}

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
