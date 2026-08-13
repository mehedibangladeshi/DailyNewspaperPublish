"""PROTOTYPE — throwaway, see NOTES.md.

Question this answers: does a "rolling N-day window of built editions,
rendered as one flat OPDS acquisition feed" model hold up once you push it
through real cases — a build that fails and produces no edition, a second
newspaper source appearing, entries aging out and needing their epub files
deleted from storage, re-running the same day twice?

Pure state + transitions only. No I/O, no XML library dependency beyond
stdlib string formatting, no terminal code — the TUI in tui.py is the only
thing allowed to talk to a screen.
"""

from datetime import date, timedelta


def initial_state(today, retention_days=7):
    return {
        "today": today,
        "retention_days": retention_days,
        # source_slug -> list of edition dicts, newest first
        "sources": {},
    }


def _edition_id(source_slug, edition_date):
    return f"urn:jugantor-opds:{source_slug}:{edition_date.isoformat()}"


def register_source(state, source_slug, source_name):
    """Simulates config.SOURCES growing to include a new newspaper."""
    if source_slug in state["sources"]:
        return state
    new_sources = dict(state["sources"])
    new_sources[source_slug] = []
    return {**state, "sources": new_sources}


def add_edition(state, source_slug, source_name, title=None):
    """Simulates a successful build for `today`. Idempotent per day: building
    the same source twice on the same simulated day replaces, not duplicates —
    mirrors main.py already producing one epub per source per run.
    """
    today = state["today"]
    editions = list(state["sources"].get(source_slug, []))
    editions = [e for e in editions if e["date"] != today]
    editions.insert(
        0,
        {
            "source_slug": source_slug,
            "source_name": source_name,
            "date": today,
            "title": title or f"{source_name} — {today.isoformat()}",
            "filename": f"{source_slug}-{today.isoformat()}.epub",
        },
    )
    new_sources = dict(state["sources"])
    new_sources[source_slug] = editions
    return {**state, "sources": new_sources}


def advance_day(state):
    """Ticks the simulated clock forward one day. Does NOT expire by itself —
    call expire() separately so the TUI can show "day advanced" and
    "editions expired" as distinct, inspectable steps.
    """
    return {**state, "today": state["today"] + timedelta(days=1)}


def expire(state):
    """Drops editions older than the retention window. Returns
    (new_state, removed) where `removed` is the flat list of edition dicts
    that fell out — this is exactly the set of epub files a real
    implementation would need to delete from object storage.
    """
    today = state["today"]
    cutoff = today - timedelta(days=state["retention_days"])
    new_sources = {}
    removed = []
    for slug, editions in state["sources"].items():
        kept = [e for e in editions if e["date"] > cutoff]
        removed.extend(e for e in editions if e["date"] <= cutoff)
        new_sources[slug] = kept
    return {**state, "sources": new_sources}, removed


def all_active_editions(state):
    """Flat, newest-first, across all sources — the order the feed renders in."""
    editions = [e for editions in state["sources"].values() for e in editions]
    return sorted(editions, key=lambda e: (e["date"], e["source_slug"]), reverse=True)


BASE_URL = "https://example.github.io/jugantor-opds"  # placeholder — real hosting TBD


def render_opds_xml(state, base_url=BASE_URL):
    """One flat acquisition feed, all sources mixed together, newest first,
    each entry tagged with an atom:category for its source. This is the
    thing the prototype is testing: does a flat+category feed stay legible
    once a second source exists, or does it actually need to become a
    navigation feed (one root feed linking to a per-source acquisition feed
    each)? Render it and look.
    """
    entries_xml = []
    for e in all_active_editions(state):
        entries_xml.append(
            f"""  <entry>
    <id>{_edition_id(e['source_slug'], e['date'])}</id>
    <title>{e['title']}</title>
    <updated>{e['date'].isoformat()}T00:00:00Z</updated>
    <category term="{e['source_slug']}" label="{e['source_name']}"/>
    <link rel="http://opds-spec.org/acquisition" href="{base_url}/{e['source_slug']}/{e['filename']}" type="application/epub+zip"/>
  </entry>"""
        )
    body = "\n".join(entries_xml) if entries_xml else "  <!-- no active editions -->"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:opds="http://opds-spec.org/2010/catalog">
  <id>urn:jugantor-opds:catalog</id>
  <title>Daily Newspaper — OPDS Catalog</title>
  <updated>{state['today'].isoformat()}T00:00:00Z</updated>
  <link rel="self" href="{base_url}/catalog.xml" type="application/atom+xml;profile=opds-catalog;kind=acquisition"/>
{body}
</feed>"""
