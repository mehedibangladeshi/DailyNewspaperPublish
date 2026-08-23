"""Temporary diagnostic: send already-built epubs in output/ via KindleSender,
without scraping/building anything. Delete once the SMTP issue is diagnosed.
"""
import glob
import logging
import os

from jugantor_epub import email_sender

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

edition_date = "2026-08-23"
epub_paths = sorted(glob.glob("/app/output/*.epub"))

with email_sender.KindleSender() as sender:
    for path in epub_paths:
        source_name = os.path.basename(path).split("-")[0]
        try:
            sent = sender.send(source_name, path, edition_date)
            logger.info("send(%s) -> sent=%s", source_name, sent)
        except Exception as exc:
            logger.error("Failed to send %s: %s", source_name, exc)
