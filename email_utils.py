import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os


def send_email(to_email, subject, body):
    host = os.environ.get("GMAIL_SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("GMAIL_SMTP_PORT", "587"))
    user = os.environ.get("GMAIL_SMTP_USER")
    password = os.environ.get("GMAIL_SMTP_PASS")

    if not user or not password:
        raise RuntimeError("GMAIL_SMTP_USER and GMAIL_SMTP_PASS must be set")

    msg = MIMEMultipart()
    msg["From"] = user
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "html"))

    server = smtplib.SMTP(host, port)
    server.starttls()
    server.login(user, password)
    server.sendmail(user, to_email, msg.as_string())
    server.quit()
    return True
