import os
import smtplib
from email.message import EmailMessage

from . import config


def build_message(epub_entries, edition_date, from_addr, to_addr):
    """Build a MIME message with one epub attachment per (source_name, epub_path) entry."""
    message = EmailMessage()
    message["Subject"] = f"Daily reading — {edition_date}"
    message["From"] = from_addr
    message["To"] = to_addr
    message.set_content(f"Attached: {len(epub_entries)} edition(s) for {edition_date}.")

    for _source_name, epub_path in epub_entries:
        with open(epub_path, "rb") as epub_file:
            data = epub_file.read()
        message.add_attachment(
            data,
            maintype="application",
            subtype="epub+zip",
            filename=os.path.basename(epub_path),
        )

    return message


def send_to_kindle(epub_entries, edition_date):
    """Send every built epub as one combined message to the configured Kindle address."""
    message = build_message(
        epub_entries, edition_date, config.GMAIL_ADDRESS, config.KINDLE_EMAIL
    )
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(config.GMAIL_ADDRESS, config.GMAIL_APP_PASSWORD)
        smtp.send_message(message)
