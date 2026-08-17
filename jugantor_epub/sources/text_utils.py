import unicodedata


def extract_text(tag, default=""):
    """Extract normalized text from a BeautifulSoup tag. News sites commonly
    mix NFC/NFD forms for Bengali nukta characters (e.g. ড় vs ড়)
    across different fields, so normalize to NFC for consistent
    rendering/comparison."""
    if tag is None:
        return default
    return unicodedata.normalize("NFC", tag.get_text(" ", strip=True))


def normalize_text(text):
    return unicodedata.normalize("NFC", text or "")
