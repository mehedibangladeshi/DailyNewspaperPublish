# Ittefaq Kindle-delivery size reduction

**Written:** 2026-08-24
**Status:** approved, ready for implementation plan
**Follows on from:** `HANDOFF.md` (deleted once this shipped) — the investigation that found Ittefaq's Kindle email is silently skipped every day because its epub (~21.5MB) exceeds `email_sender.py`'s Gmail-safe attachment threshold (`GMAIL_MAX_ATTACHMENT_BYTES` ≈ 17.5MB).

## Problem

Ittefaq builds successfully every run (22 sections, ~440 articles) but its epub is consistently too large to email to Kindle. The send is skipped with a logged warning; `main.py`'s exit code stays 0, so this never surfaces as a failed GitHub Actions run. The OPDS catalog has no size gate, so non-Kindle readers still get Ittefaq fine — only the Kindle email is missing, silently, every day.

Root cause: images. At `config.IMAGE_MAX_WIDTH=800`/`IMAGE_JPEG_QUALITY=75` (shared by all 5 sources), ~440 per-article images account for nearly all of the 21.5MB — text and the embedded font are negligible by comparison. Ittefaq has by far the most sections/articles of any configured source, so it's the one source that currently breaches the limit.

## Decisions

Two independent changes, combined:

### 1. Trim Ittefaq's section list

Four sections are dropped from `CORE_SECTION_SLUGS` and `FALLBACK_SECTIONS` in `jugantor_epub/sources/ittefaq.py`, as lower editorial priority for a daily Kindle read:

- `social-media` (সোশ্যাল মিডিয়া)
- `projonmo` (প্রজন্ম — youth/lifestyle)
- `probash` (প্রবাস — expat news)
- `campus` (ক্যাম্পাস)

18 sections remain (national, capital, country, politics, world-news, sports, entertainment, business, tech, education, health, literature, religion, lifestyle, opinion, news, editorial, law-and-court, environment). This reduces article/image count and therefore size, on top of the compression change below. This is a genuine content trade-off — these are real news categories, not junk like the already-excluded `video`/`photo`/`jobs`/`latest-news` — and is why it's an explicit decision here rather than folded into the "curated allowlist" rationale already documented for those.

### 2. General retry-if-oversized image compression

Rather than a permanent Ittefaq-specific quality reduction (which would degrade Ittefaq's images every day, including days it would already fit, and would also shrink the copy OPDS readers get), compression only kicks in on the rare day a source's epub actually comes in oversized — and it applies to **any** source, not just Ittefaq, so Prothom Alo or a future large source benefits the same way.

**Flow, inside `main.py`'s `build_source_edition()`:**

1. Build the epub once at the normal settings (`config.IMAGE_MAX_WIDTH`/`IMAGE_JPEG_QUALITY`), as today.
2. Check the output file's size against `email_sender.GMAIL_MAX_ATTACHMENT_BYTES` — the same constant `email_sender.py` already gates sending on, so the trigger and the actual send-skip threshold can't drift apart.
3. If over budget: re-encode every article's already-downloaded image at fallback settings (`config.IMAGE_MAX_WIDTH_FALLBACK`, `config.IMAGE_JPEG_QUALITY_FALLBACK`) and rebuild the epub in place (same `output_path`, overwritten). One retry, not a loop — this is a fallback tier, not an iterative shrink-until-it-fits search.
4. If it's still over budget after the retry, behavior is unchanged from today: `email_sender.py`'s existing size gate skips the send with a logged warning. That stays as the final backstop.

**Avoiding a second network round-trip on retry:** `jugantor_epub/images.py`'s `download_image()` currently downloads and re-encodes in one step, reading `config.IMAGE_JPEG_QUALITY` internally. It's split into:
- a raw-fetch step (network GET, decode) — unchanged cost, still cached by URL as it is today via `build_source_edition`'s `cached_download_image` closure, but the closure now caches the *raw* decoded bytes, not the final encoded JPEG.
- an encode step taking explicit `max_width`/`quality` params, callable again during the retry against the same cached raw bytes with the fallback settings — no re-download.

**New config constants** in `jugantor_epub/config.py`:
```python
IMAGE_MAX_WIDTH_FALLBACK = 500
IMAGE_JPEG_QUALITY_FALLBACK = 50
```
(Roughly halves image weight relative to the normal 800/75 settings. Not derived from a precise byte-budget calculation — treated as a reasonable starting point, tunable later against real run sizes if it turns out to be insufficient or overly aggressive.)

## Error handling

If re-encoding during the retry raises for some reason, the rebuild is caught and abandoned — the original (oversized) epub from step 1 stands, and the existing size-skip safety net in `email_sender.py` still applies. This is the same error-isolation principle used elsewhere in the codebase (one failure narrows scope rather than aborting the run): a broken retry must not turn a "send skipped" day into a "build failed" day.

## Testing

- `jugantor_epub/images.py`: unit test that encoding the same raw bytes at two different `(max_width, quality)` pairs produces different (smaller-at-tighter-settings) output, and that the raw-fetch step is unaffected by the encode params.
- `main.py`: a test that forces the first build's output over a mocked/monkeypatched size threshold and asserts a second, smaller rebuild happens using the fallback settings, without a second network fetch (assert the raw-image fetch mock was called only once per image URL).
- `jugantor_epub/sources/ittefaq.py`: existing fixture-based tests continue to pass with the trimmed `CORE_SECTION_SLUGS`; if any fixture test currently asserts the full 22-section list, it's updated to the new 18.
- No change needed to `test_build_epub_passes_epubcheck` — it's agnostic to image size/settings.

## Out of scope

- Splitting a single source into multiple epubs/emails (HANDOFF option 2) — not pursued; the retry-compression approach is simpler and was judged sufficient.
- Any workaround of Gmail's own size limit itself (HANDOFF option 5) — not pursued, too invasive for a personal project.
- A fully iterative "keep shrinking until it fits" loop — one fallback tier is judged sufficient; if real runs show even the fallback settings aren't enough, that's a follow-up, not part of this change.
