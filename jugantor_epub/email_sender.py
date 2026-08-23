import logging
import os
import smtplib
import time
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


class KindleSender:
    """Sends one Kindle email per source, reusing a single SMTP connection
    across the whole run instead of reconnecting per source.

    Connects lazily: no SMTP traffic happens until the first .send() call.
    Later calls verify the connection is still alive via smtp.noop() and
    transparently reconnect if it has gone stale, since a run's sources can
    be minutes apart while each one scrapes and builds.
    """

    def __init__(self):
        self._smtp = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._smtp is not None:
            try:
                self._smtp.quit()
            except Exception:
                pass
            self._smtp = None
        return False

    def _ensure_connected(self):
        if self._smtp is not None:
            try:
                status, _ = self._smtp.noop()
                if status == 250:
                    return
            except Exception:
                pass
            try:
                self._smtp.close()
            except Exception:
                pass
            self._smtp = None

        # A fresh handshake occasionally stalls transiently (e.g. Gmail or a
        # residential connection dropping an EHLO reply) - retry a couple of
        # times before giving up, rather than failing that source's send.
        attempts = 3
        for attempt in range(attempts):
            try:
                smtp = smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30)
                smtp.login(config.GMAIL_ADDRESS, config.GMAIL_APP_PASSWORD)
                self._smtp = smtp
                return
            except Exception:
                if attempt == attempts - 1:
                    raise
                time.sleep(2**attempt)

    def send(self, source_name, epub_path, edition_date):
        """Send one source's epub as its own Kindle email.

        Returns True if sent, False if skipped for being over Gmail's
        attachment size limit. Raises on a real send failure so the caller
        can count it as a failed source.
        """
        file_size = os.path.getsize(epub_path)
        if file_size > GMAIL_MAX_ATTACHMENT_BYTES:
            logger.warning(
                "Skipping Kindle email for %s: %s is %d bytes, over Gmail's send limit",
                source_name,
                epub_path,
                file_size,
            )
            return False

        self._ensure_connected()
        message = build_message(
            [(source_name, epub_path)],
            edition_date,
            config.GMAIL_ADDRESS,
            config.KINDLE_EMAIL,
        )
        try:
            self._smtp.send_message(message)
        except Exception:
            try:
                self._smtp.close()
            except Exception:
                pass
            self._smtp = None
            raise
        return True
