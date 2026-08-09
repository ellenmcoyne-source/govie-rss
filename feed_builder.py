#!/usr/bin/env python3
"""
Builds an RSS feed of new publications from Irish government department
websites (gov.ie's central publications listing + every department's own
listing page + any external department sites configured in sources.py).

Run it directly:      python feed_builder.py
Output:                docs/feed.xml  (RSS 2.0)

Designed to be run on a schedule (see .github/workflows/update-feed.yml).
Each run re-scrapes the "newest first" listing pages and regenerates the
feed from scratch -- your RSS reader is what remembers which items you've
already seen, so there's no local state to manage.
"""

import hashlib
import re
import sys
import time
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from xml.sax.saxutils import escape

import requests
from bs4 import BeautifulSoup

from sources import ALL_SOURCES

OUTPUT_PATH = Path(__file__).parent / "docs" / "feed.xml"
DEBUG_PATH = Path(__file__).parent / "docs" / "last_run_debug.txt"

MAX_ITEMS_IN_FEED = 300
PAGES_PER_SOURCE = 2          # how many "?page=N" pages to check per source
REQUEST_DELAY_SECONDS = 0.5   # be polite to gov.ie's servers
REQUEST_TIMEOUT = 20

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; GovIEPublicationsRSSBot/1.0; "
        "personal RSS feed generator, not for commercial use)"
    )
}

MONTHS = (
    "January|February|March|April|May|June|July|August|"
    "September|October|November|December"
)
DATE_RE = re.compile(r"\b(\d{1,2} (?:" + MONTHS + r") \d{4})\b")

# A "content item" link on gov.ie looks like:
#   /en/<department-or-org-slug>/<content-type>/<item-slug>/
# where content-type is one of these. Anything else (nav links, filters,
# pagination, the department's own homepage) gets skipped.
CONTENT_TYPES = (
    "publications|publication|press-releases|press-release|speeches|"
    "speech|news|collections|collection|circulars|circular|"
    "consultations|consultation|policies|policy"
)
ITEM_PATH_RE = re.compile(
    r"/en/[a-z0-9\-]+/(?:" + CONTENT_TYPES + r")/[a-z0-9\-%]+/?$", re.IGNORECASE
)


def fetch(url: str) -> str | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as exc:
        print(f"  ! failed to fetch {url}: {exc}", file=sys.stderr)
        return None


def resolve_url(href: str, base: str) -> str | None:
    if href.startswith("http"):
        return href.split("#")[0]
    if href.startswith("/"):
        return (base.rstrip("/") + href).split("#")[0]
    return None


def find_nearby_date(link_tag) -> str | None:
    """Walk up the DOM from a title link looking for a nearby date string
    like '7 August 2026', stopping once the surrounding text block gets too
    large (a sign we've walked out of the individual list-item container)."""
    node = link_tag
    for _ in range(6):
        node = node.parent
        if node is None:
            return None
        text = node.get_text(" ", strip=True)
        match = DATE_RE.search(text)
        if match:
            return match.group(1)
        if len(text) > 500:
            return None
    return None


def extract_items(html: str, source_name: str, base: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    items = []
    seen_on_page = set()

    for link in soup.find_all("a", href=True):
        full_url = resolve_url(link["href"], base)
        if not full_url or not ITEM_PATH_RE.search(full_url):
            continue
        title = link.get_text(strip=True)
        if not title or len(title) < 4:
            continue
        if full_url in seen_on_page:
            continue
        seen_on_page.add(full_url)

        date_str = find_nearby_date(link)
        items.append(
            {
                "title": title,
                "url": full_url,
                "date_str": date_str,
                "source": source_name,
            }
        )
    return items


def parse_date(date_str: str | None) -> datetime | None:
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%d %B %Y").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def collect_all_items() -> list[dict]:
    all_items = {}  # url -> item, for dedup across sources/pages
    debug_lines = []

    for source in ALL_SOURCES:
        found_this_source = 0
        for page in range(1, PAGES_PER_SOURCE + 1):
            sep = "&" if "?" in source["url"] else "?"
            page_url = source["url"] if page == 1 else f"{source['url']}{sep}page={page}"

            html = fetch(page_url)
            time.sleep(REQUEST_DELAY_SECONDS)
            if not html:
                continue

            page_items = extract_items(html, source["name"], source["base"])
            if not page_items and page == 1:
                debug_lines.append(f"[warn] 0 items parsed from {page_url}")
            for item in page_items:
                if item["url"] not in all_items:
                    all_items[item["url"]] = item
                    found_this_source += 1

        print(f"  {source['name']}: {found_this_source} items")
        debug_lines.append(f"{source['name']}: {found_this_source} items from {source['url']}")

    DEBUG_PATH.parent.mkdir(parents=True, exist_ok=True)
    DEBUG_PATH.write_text(
        f"Last run: {datetime.now(timezone.utc).isoformat()}\n\n" + "\n".join(debug_lines),
        encoding="utf-8",
    )

    return list(all_items.values())


def build_rss(items: list[dict]) -> str:
    now = datetime.now(timezone.utc)

    def sort_key(item):
        d = parse_date(item["date_str"])
        return d or datetime(1970, 1, 1, tzinfo=timezone.utc)

    items_sorted = sorted(items, key=sort_key, reverse=True)[:MAX_ITEMS_IN_FEED]

    rss_items = []
    for item in items_sorted:
        pub_date = parse_date(item["date_str"]) or now
        guid = hashlib.sha1(item["url"].encode("utf-8")).hexdigest()
        rss_items.append(
            f"""    <item>
      <title>{escape(item['title'])}</title>
      <link>{escape(item['url'])}</link>
      <guid isPermaLink="false">{guid}</guid>
      <pubDate>{format_datetime(pub_date)}</pubDate>
      <source>{escape(item['source'])}</source>
      <description>{escape(item['source'])} — published {escape(item['date_str'] or 'date unknown')}</description>
    </item>"""
        )

    channel = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Irish Government Publications</title>
    <link>https://www.gov.ie/en/publications/</link>
    <description>New publications and documents from gov.ie and individual Irish government department websites.</description>
    <language>en-ie</language>
    <lastBuildDate>{format_datetime(now)}</lastBuildDate>
{chr(10).join(rss_items)}
  </channel>
</rss>
"""
    return channel


def main():
    print(f"Checking {len(ALL_SOURCES)} sources...")
    items = collect_all_items()
    print(f"Total unique items found: {len(items)}")

    rss_xml = build_rss(items)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(rss_xml, encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH} with {min(len(items), MAX_ITEMS_IN_FEED)} items")


if __name__ == "__main__":
    main()
