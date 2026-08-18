import logging
import os
import smtplib
from email.message import EmailMessage

from . import config

logger = logging.getLogger(__name__)

# Gmail rejects outgoing messages over 25MB (encoded). Base64 attachment
# encoding inflates raw bytes by ~4/3, so gate on raw file size with margin
# for that overhead plus MIME headers/boundaries.
GMAIL_MAX_MESSAGE_BYTES = 25 * 1024 * 1024
GMAIL_MAX_ATTACHMENT_BYTES = int(GMAIL_MAX_MESSAGE_BYTES * 0.7)


class NoEditionsSentError(Exception):
    """Raised when every entry was skipped or failed, so nothing was sent."""


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
    """Send each built epub as its own message to the configured Kindle address.

    One oversized or failing epub shouldn't block delivery of the others, so
    each entry is sent as a separate email: entries too large for Gmail's
    send limit are skipped with a warning, and a send failure for one entry
    is logged and skipped rather than aborting the remaining entries.

    Returns the number of entries actually sent.
    """
    sent = 0
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(config.GMAIL_ADDRESS, config.GMAIL_APP_PASSWORD)
        for source_name, epub_path in epub_entries:
            file_size = os.path.getsize(epub_path)
            if file_size > GMAIL_MAX_ATTACHMENT_BYTES:
                logger.warning(
                    "Skipping Kindle email for %s: %s is %d bytes, over Gmail's send limit",
                    source_name,
                    epub_path,
                    file_size,
                )
                continue

            try:
                message = build_message(
                    [(source_name, epub_path)],
                    edition_date,
                    config.GMAIL_ADDRESS,
                    config.KINDLE_EMAIL,
                )
                smtp.send_message(message)
            except Exception as exc:
                logger.warning("Failed to send Kindle email for %s: %s", source_name, exc)
                continue
            sent += 1

    if sent == 0:
        raise NoEditionsSentError("No editions were sent: all entries were skipped or failed")

    return sent
