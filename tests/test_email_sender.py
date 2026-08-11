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
