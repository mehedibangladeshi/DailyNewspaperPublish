import json


def select_by_type(soup, type_name):
    """Parse every <script type="application/ld+json"> block on a page and
    return the first one whose "@type" matches type_name, or {} if none do.

    Picking "the first ld+json block" isn't safe in general - several sites
    put an Organization/Website/BreadcrumbList block before the one that
    actually holds the article metadata - so callers that need a specific
    schema.org type should select by @type explicitly instead."""
    for tag in soup.select('script[type="application/ld+json"]'):
        try:
            # strict=False: some sites embed raw literal newlines inside
            # JSON string values (e.g. multi-line headlines), which breaks
            # strict JSON parsing.
            data = json.loads(tag.string or "{}", strict=False)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(data, dict):
            continue
        if data.get("@type") == type_name:
            return data
        # Some sites (e.g. Daily Star's Drupal setup) bundle every entity
        # for the page into one block via a schema.org "@graph" array
        # instead of emitting separate <script> blocks per type.
        for item in data.get("@graph") or []:
            if isinstance(item, dict) and item.get("@type") == type_name:
                return item
    return {}
