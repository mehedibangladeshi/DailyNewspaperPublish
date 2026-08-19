from unittest.mock import MagicMock, patch

from jugantor_epub import email_sender


def test_build_message_single_entry_attachment(tmp_path):
    epub_path = tmp_path / "jugantor-2026-08-11.epub"
    epub_path.write_bytes(b"fake epub bytes")

    message = email_sender.build_message(
        [("যুগান্তর", str(epub_path))],
        "2026-08-11",
        "sender@gmail.com",
        "kindle@kindle.com",
    )

    assert message["From"] == "sender@gmail.com"
    assert message["To"] == "kindle@kindle.com"
    assert "2026-08-11" in message["Subject"]

    attachments = list(message.iter_attachments())
    assert len(attachments) == 1
    assert attachments[0].get_content_type() == "application/epub+zip"
    assert attachments[0].get_filename() == "jugantor-2026-08-11.epub"
    assert attachments[0].get_payload(decode=True) == b"fake epub bytes"


def test_build_message_multi_entry_attachments(tmp_path):
    epub_a = tmp_path / "jugantor-2026-08-11.epub"
    epub_a.write_bytes(b"paper A bytes")
    epub_b = tmp_path / "other-2026-08-11.epub"
    epub_b.write_bytes(b"paper B bytes")

    message = email_sender.build_message(
        [("যুগান্তর", str(epub_a)), ("Other Paper", str(epub_b))],
        "2026-08-11",
        "sender@gmail.com",
        "kindle@kindle.com",
    )

    attachments = list(message.iter_attachments())
    assert len(attachments) == 2
    filenames = {a.get_filename() for a in attachments}
    assert filenames == {"jugantor-2026-08-11.epub", "other-2026-08-11.epub"}
    for attachment in attachments:
        assert attachment.get_content_type() == "application/epub+zip"


def test_send_to_kindle_sends_one_message_per_entry(tmp_path):
    epub_a = tmp_path / "jugantor-2026-08-11.epub"
    epub_a.write_bytes(b"paper A bytes")
    epub_b = tmp_path / "prothomalo-2026-08-11.epub"
    epub_b.write_bytes(b"paper B bytes")

    smtp_instance = MagicMock()
    smtp_instance.__enter__.return_value = smtp_instance
    with patch("jugantor_epub.email_sender.smtplib.SMTP_SSL", return_value=smtp_instance):
        email_sender.send_to_kindle(
            [("যুগান্তর", str(epub_a)), ("প্রথম আলো", str(epub_b))],
            "2026-08-11",
        )

    assert smtp_instance.send_message.call_count == 2
    sent_filenames = set()
    for call in smtp_instance.send_message.call_args_list:
        message = call.args[0]
        attachments = list(message.iter_attachments())
        assert len(attachments) == 1
        sent_filenames.add(attachments[0].get_filename())
    assert sent_filenames == {"jugantor-2026-08-11.epub", "prothomalo-2026-08-11.epub"}


def test_send_to_kindle_skips_oversized_entry_without_raising(tmp_path):
    small_epub = tmp_path / "jugantor-2026-08-11.epub"
    small_epub.write_bytes(b"small bytes")
    huge_epub = tmp_path / "prothomalo-2026-08-11.epub"
    huge_epub.write_bytes(b"x" * (26 * 1024 * 1024))

    smtp_instance = MagicMock()
    smtp_instance.__enter__.return_value = smtp_instance
    with patch("jugantor_epub.email_sender.smtplib.SMTP_SSL", return_value=smtp_instance):
        email_sender.send_to_kindle(
            [("যুগান্তর", str(small_epub)), ("প্রথম আলো", str(huge_epub))],
            "2026-08-11",
        )

    assert smtp_instance.send_message.call_count == 1
    message = smtp_instance.send_message.call_args.args[0]
    attachments = list(message.iter_attachments())
    assert len(attachments) == 1
    assert attachments[0].get_filename() == "jugantor-2026-08-11.epub"


def test_send_to_kindle_returns_count_of_entries_actually_sent(tmp_path):
    small_epub = tmp_path / "jugantor-2026-08-11.epub"
    small_epub.write_bytes(b"small bytes")
    huge_epub = tmp_path / "prothomalo-2026-08-11.epub"
    huge_epub.write_bytes(b"x" * (26 * 1024 * 1024))

    smtp_instance = MagicMock()
    smtp_instance.__enter__.return_value = smtp_instance
    with patch("jugantor_epub.email_sender.smtplib.SMTP_SSL", return_value=smtp_instance):
        sent_count = email_sender.send_to_kindle(
            [("যুগান্তর", str(small_epub)), ("প্রথম আলো", str(huge_epub))],
            "2026-08-11",
        )

    assert sent_count == 1


def test_send_to_kindle_continues_after_one_entry_fails_to_send(tmp_path):
    import smtplib

    epub_a = tmp_path / "jugantor-2026-08-11.epub"
    epub_a.write_bytes(b"paper A bytes")
    epub_b = tmp_path / "prothomalo-2026-08-11.epub"
    epub_b.write_bytes(b"paper B bytes")

    smtp_instance = MagicMock()
    smtp_instance.__enter__.return_value = smtp_instance
    smtp_instance.send_message.side_effect = [
        smtplib.SMTPException("transient server error"),
        None,
    ]
    with patch("jugantor_epub.email_sender.smtplib.SMTP_SSL", return_value=smtp_instance):
        sent_count = email_sender.send_to_kindle(
            [("যুগান্তর", str(epub_a)), ("প্রথম আলো", str(epub_b))],
            "2026-08-11",
        )

    assert smtp_instance.send_message.call_count == 2
    assert sent_count == 1


def test_send_to_kindle_raises_when_every_entry_is_oversized(tmp_path):
    huge_epub = tmp_path / "prothomalo-2026-08-11.epub"
    huge_epub.write_bytes(b"x" * (26 * 1024 * 1024))

    smtp_instance = MagicMock()
    smtp_instance.__enter__.return_value = smtp_instance
    with patch("jugantor_epub.email_sender.smtplib.SMTP_SSL", return_value=smtp_instance):
        try:
            email_sender.send_to_kindle(
                [("প্রথম আলো", str(huge_epub))],
                "2026-08-11",
            )
        except email_sender.NoEditionsSentError:
            pass
        else:
            raise AssertionError("expected NoEditionsSentError")

    smtp_instance.send_message.assert_not_called()


import smtplib as _smtplib


def test_kindle_sender_does_not_connect_until_first_send(tmp_path):
    epub_path = tmp_path / "jugantor-2026-08-19.epub"
    epub_path.write_bytes(b"fake epub bytes")

    with patch("jugantor_epub.email_sender.smtplib.SMTP_SSL") as smtp_ssl_cls:
        with email_sender.KindleSender():
            pass  # never called .send()

    smtp_ssl_cls.assert_not_called()


def test_kindle_sender_connects_and_sends_on_first_send(tmp_path):
    epub_path = tmp_path / "jugantor-2026-08-19.epub"
    epub_path.write_bytes(b"fake epub bytes")

    smtp_instance = MagicMock()
    with patch(
        "jugantor_epub.email_sender.smtplib.SMTP_SSL", return_value=smtp_instance
    ) as smtp_ssl_cls:
        with email_sender.KindleSender() as sender:
            sent = sender.send("যুগান্তর", str(epub_path), "2026-08-19")

    assert sent is True
    smtp_ssl_cls.assert_called_once_with("smtp.gmail.com", 465)
    smtp_instance.login.assert_called_once()
    assert smtp_instance.send_message.call_count == 1
    message = smtp_instance.send_message.call_args.args[0]
    attachments = list(message.iter_attachments())
    assert attachments[0].get_filename() == "jugantor-2026-08-19.epub"


def test_kindle_sender_reuses_connection_across_multiple_sends(tmp_path):
    epub_a = tmp_path / "jugantor-2026-08-19.epub"
    epub_a.write_bytes(b"paper A bytes")
    epub_b = tmp_path / "prothomalo-2026-08-19.epub"
    epub_b.write_bytes(b"paper B bytes")

    smtp_instance = MagicMock()
    smtp_instance.noop.return_value = (250, b"OK")
    with patch(
        "jugantor_epub.email_sender.smtplib.SMTP_SSL", return_value=smtp_instance
    ) as smtp_ssl_cls:
        with email_sender.KindleSender() as sender:
            sender.send("যুগান্তর", str(epub_a), "2026-08-19")
            sender.send("প্রথম আলো", str(epub_b), "2026-08-19")

    smtp_ssl_cls.assert_called_once()
    assert smtp_instance.login.call_count == 1
    assert smtp_instance.send_message.call_count == 2


def test_kindle_sender_reconnects_when_noop_fails(tmp_path):
    epub_a = tmp_path / "jugantor-2026-08-19.epub"
    epub_a.write_bytes(b"paper A bytes")
    epub_b = tmp_path / "prothomalo-2026-08-19.epub"
    epub_b.write_bytes(b"paper B bytes")

    first_conn = MagicMock()
    first_conn.noop.side_effect = _smtplib.SMTPServerDisconnected("gone")
    second_conn = MagicMock()
    second_conn.noop.return_value = (250, b"OK")

    with patch(
        "jugantor_epub.email_sender.smtplib.SMTP_SSL",
        side_effect=[first_conn, second_conn],
    ) as smtp_ssl_cls:
        with email_sender.KindleSender() as sender:
            sender.send("যুগান্তর", str(epub_a), "2026-08-19")
            sender.send("প্রথম আলো", str(epub_b), "2026-08-19")

    assert smtp_ssl_cls.call_count == 2
    assert first_conn.send_message.call_count == 1
    assert second_conn.send_message.call_count == 1


def test_kindle_sender_skips_oversized_epub_without_connecting_or_raising(tmp_path):
    huge_epub = tmp_path / "prothomalo-2026-08-19.epub"
    huge_epub.write_bytes(b"x" * (26 * 1024 * 1024))

    with patch("jugantor_epub.email_sender.smtplib.SMTP_SSL") as smtp_ssl_cls:
        with email_sender.KindleSender() as sender:
            sent = sender.send("প্রথম আলো", str(huge_epub), "2026-08-19")

    assert sent is False
    smtp_ssl_cls.assert_not_called()


def test_kindle_sender_raises_on_send_failure(tmp_path):
    epub_path = tmp_path / "jugantor-2026-08-19.epub"
    epub_path.write_bytes(b"fake epub bytes")

    smtp_instance = MagicMock()
    smtp_instance.send_message.side_effect = _smtplib.SMTPException("boom")
    with patch("jugantor_epub.email_sender.smtplib.SMTP_SSL", return_value=smtp_instance):
        with email_sender.KindleSender() as sender:
            try:
                sender.send("যুগান্তর", str(epub_path), "2026-08-19")
            except _smtplib.SMTPException:
                pass
            else:
                raise AssertionError("expected SMTPException")


def test_kindle_sender_closes_connection_on_exit(tmp_path):
    epub_path = tmp_path / "jugantor-2026-08-19.epub"
    epub_path.write_bytes(b"fake epub bytes")

    smtp_instance = MagicMock()
    with patch("jugantor_epub.email_sender.smtplib.SMTP_SSL", return_value=smtp_instance):
        with email_sender.KindleSender() as sender:
            sender.send("যুগান্তর", str(epub_path), "2026-08-19")

    smtp_instance.quit.assert_called_once()


def test_kindle_sender_exit_does_not_raise_if_never_connected():
    with email_sender.KindleSender():
        pass  # no assertion needed - just must not raise


def test_kindle_sender_reconnects_after_a_send_failure(tmp_path):
    epub_a = tmp_path / "jugantor-2026-08-19.epub"
    epub_a.write_bytes(b"paper A bytes")
    epub_b = tmp_path / "prothomalo-2026-08-19.epub"
    epub_b.write_bytes(b"paper B bytes")

    first_conn = MagicMock()
    first_conn.send_message.side_effect = _smtplib.SMTPException("boom")
    second_conn = MagicMock()
    second_conn.noop.return_value = (250, b"OK")

    with patch(
        "jugantor_epub.email_sender.smtplib.SMTP_SSL",
        side_effect=[first_conn, second_conn],
    ) as smtp_ssl_cls:
        with email_sender.KindleSender() as sender:
            try:
                sender.send("যুগান্তর", str(epub_a), "2026-08-19")
            except _smtplib.SMTPException:
                pass
            else:
                raise AssertionError("expected SMTPException")

            sent = sender.send("প্রথম আলো", str(epub_b), "2026-08-19")

    assert sent is True
    assert smtp_ssl_cls.call_count == 2
    second_conn.send_message.assert_called_once()
