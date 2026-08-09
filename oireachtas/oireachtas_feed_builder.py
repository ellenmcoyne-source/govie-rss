#!/usr/bin/env python3
"""
Builds an RSS feed of new documents (correspondence, opening statements,
submissions, reports) published by every Oireachtas committee.

How it works:
  1. Fetches the committees index page and discovers every currently-sitting
     committee (so this doesn't need updating when committees are renamed or
     a new Dail starts -- it re-discovers the list every run).
  2. For each committee, fetches its "documents" listing page, e.g.
     https://www.oireachtas.ie/en/committees/34/committee-of-public-accounts/documents/
  3. The actual files are hosted on a separate, less locked-down subdomain
     (data.oireachtas.ie) and their filenames embed the publish date, e.g.
     .../2026-03-24_opening-statement-dr-johnny-ryan..._en.pdf
     so instead of trying to scrape a date out of the page layout, we just
     read the date straight out of the file URL. This is far more robust to
     oireachtas.ie changing its page design.

Output: docs/oireachtas-feed.xml (RSS 2.0)

NOTE: oireachtas.ie has more aggressive bot-detection than gov.ie does, so
this uses `cloudscraper` (a requests-compatible library built to get past
basic Cloudflare challenges) instead of plain `requests`. If a run still
comes back with 0 items across the board, check docs/oireachtas-debug.txt
first -- that likely means the site is blocking GitHub Actions' IPs outright,
which would need a heavier fix (e.g. a headless browser).
"""

import re
import sys
import time
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import urljoin
from xml.sax.saxutils import escape

import cloudscraper
from bs4 import BeautifulSoup

BASE = "https://www.oireachtas.ie"
COMMITTEES_INDEX = f"{BASE}/en/committees/"

OUTPUT_PATH = Path(__file__).parent.parent / "docs" / "oireachtas-feed.xml"
DEBUG_PATH = Path(__file__).parent.parent / "docs" / "oireachtas-debug.txt"

MAX_ITEMS_IN_FEED = 400
REQUEST_DELAY_SECONDS = 1.0   # be extra polite -- this site is more sensitive
REQUEST_TIMEOUT = 25

# Matches committee homepage links like /en/committees/34/committee-of-public-accounts/
# (exactly two path segments after /en/committees/, nothing further).
COMMITTEE_LINK_RE = re.compile(r"^/en/committees/(\d+)/([a-z0-9\-]+)/?$")

# Matches the actual document files, which live on a separate subdomain and
# have the publish date baked into the filename, e.g.:
#   https://data.oireachtas.ie/ie/oireachtas/committee/dail/34/.../2026-03-24_opening-statement-....pdf
DOCUMENT_URL_RE = re.compile(
    r"https://data\.oireachtas\.ie/\S+?/(\d{4})-(\d{2})-(\d{2})_([a-z0-9\-_]+?)(?:_[a-z]{2})?\.(?:pdf|docx?|xlsx?|odt)",
    re.IGNORECASE,
)

TRAILING_FORMAT_RE = re.compile(r"\s*\((?:pdf|docx?|xlsx?|odt)?\)\s*$", re.IGNORECASE)

scraper = cloudscraper.create_scraper(browser={"custom": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})


def fetch(url: str) -> str | None:
    try:
        resp = scraper.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.text
    except Exception as exc:  # noqa: BLE001 -- log and continue, don't crash the whole run
        print(f"  ! failed to fetch {url}: {exc}", file=sys.stderr)
        return None


def discover_committees() -> list[dict]:
    html = fetch(COMMITTEES_INDEX)
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    found = {}  # (dail_no, slug) -> name

    for link in soup.find_all("a", href=True):
        href = link["href"]
        # strip domain if present so the regex only has to handle the path
        path = href.replace(BASE, "")
        match = COMMITTEE_LINK_RE.match(path)
        if not match:
            continue
        dail_no, slug = match.group(1), match.group(2)
        name = link.get_text(strip=True)
        if not name or len(name) < 3:
            continue
        found[(dail_no, slug)] = name

    if not found:
        return []

    # Only keep the current (highest-numbered) Dail's committees -- older
    # ones are historical/expired and would just add noise.
    current_dail = max(int(d) for d, _ in found)
    committees = [
        {"dail_no": d, "slug": slug, "name": name}
        for (d, slug), name in found.items()
        if int(d) == current_dail
    ]
    return sorted(committees, key=lambda c: c["name"])


def extract_documents(html: str, committee_name: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    items = []
    seen = set()

    for link in soup.find_all("a", href=True):
        href = link["href"]
        match = DOCUMENT_URL_RE.search(href)
        if not match:
            continue
        if href in seen:
            continue
        seen.add(href)

        year, month, day, filename_slug = match.groups()
        try:
            pub_date = datetime(int(year), int(month), int(day), tzinfo=timezone.utc)
        except ValueError:
            continue

        title = link.get_text(strip=True)
        title = TRAILING_FORMAT_RE.sub("", title).strip()
        if not title or len(title) < 4:
            # fall back to turning the filename into a readable title
            title = filename_slug.replace("-", " ").strip().capitalize()

        items.append(
            {
                "title": title,
                "url": href,
                "pub_date": pub_date,
                "committee": committee_name,
            }
        )
    return items


def collect_all_items() -> list[dict]:
    committees = discover_committees()
    debug_lines = [f"Discovered {len(committees)} committees"]

    if not committees:
        debug_lines.append(
            "[warn] Could not discover any committees -- the committees index "
            "page probably came back blocked or empty. Check network access."
        )

    all_items = {}  # url -> item, dedup across committees (rare overlaps)

    for committee in committees:
        doc_url = f"{BASE}/en/committees/{committee['dail_no']}/{committee['slug']}/documents/"
        html = fetch(doc_url)
        time.sleep(REQUEST_DELAY_SECONDS)

        if not html:
            debug_lines.append(f"[warn] fetch failed: {committee['name']} ({doc_url})")
            continue

        items = extract_documents(html, committee["name"])
        if not items:
            debug_lines.append(f"[warn] 0 items parsed: {committee['name']} ({doc_url})")
        else:
            debug_lines.append(f"{committee['name']}: {len(items)} items")

        for item in items:
            all_items.setdefault(item["url"], item)

    DEBUG_PATH.parent.mkdir(parents=True, exist_ok=True)
    DEBUG_PATH.write_text(
        f"Last run: {datetime.now(timezone.utc).isoformat()}\n\n" + "\n".join(debug_lines),
        encoding="utf-8",
    )

    return list(all_items.values())


def build_rss(items: list[dict]) -> str:
    now = datetime.now(timezone.utc)
    items_sorted = sorted(items, key=lambda i: i["pub_date"], reverse=True)[:MAX_ITEMS_IN_FEED]

    rss_items = []
    for item in items_sorted:
        import hashlib

        guid = hashlib.sha1(item["url"].encode("utf-8")).hexdigest()
        rss_items.append(
            f"""    <item>
      <title>{escape(item['committee'])}: {escape(item['title'])}</title>
      <link>{escape(item['url'])}</link>
      <guid isPermaLink="false">{guid}</guid>
      <pubDate>{format_datetime(item['pub_date'])}</pubDate>
      <source>{escape(item['committee'])}</source>
      <description>{escape(item['committee'])} — published {item['pub_date'].strftime('%d %B %Y')}</description>
    </item>"""
        )

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Oireachtas Committee Publications</title>
    <link>{BASE}/en/committees/</link>
    <description>New correspondence, opening statements, submissions and reports published by every Oireachtas committee.</description>
    <language>en-ie</language>
    <lastBuildDate>{format_datetime(now)}</lastBuildDate>
{chr(10).join(rss_items)}
  </channel>
</rss>
"""


def main():
    items = collect_all_items()
    print(f"Total unique documents found: {len(items)}")

    rss_xml = build_rss(items)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(rss_xml, encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH} with {min(len(items), MAX_ITEMS_IN_FEED)} items")


if __name__ == "__main__":
    main()
