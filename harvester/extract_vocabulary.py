#!/usr/bin/env python3
"""
Flexible Vocabulary Extractor

Given a URL that contains an alphabetized (or otherwise structured) list of
terms and definitions, extract term–definition pairs and print them.

Heuristics handle common patterns:
- HTML definition lists (<dl>/<dt>/<dd>)
- Tables with Term/Definition columns
- Lists where each <li> encodes "term - definition" or "term: definition"
- Blocks with headings/bold terms followed by descriptive text
- Plain text paragraphs with delimiter patterns

Usage:
  python -m harvester.extract_vocabulary <url> [--format json|text|tsv] [--use-playwright] [--wait-selector CSS]
  python harvester/extract_vocabulary.py <url> [--format json|text|tsv] [--use-playwright] [--wait-selector CSS]
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import OrderedDict
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Tuple

import requests
from bs4 import BeautifulSoup, NavigableString, Tag
import mysql.connector
from mysql.connector import Error as MySQLError
import os
from datetime import date

# Try to load central DB config if available
try:
    from core.config import get_db_config as get_core_db_config  # type: ignore
except Exception:
    get_core_db_config = None  # Fallback to CLI/env


DELIMITERS: Sequence[str] = (
    " — ",  # em dash surrounded by spaces
    " – ",  # en dash surrounded by spaces
    " - ",
    " : ",
    ": ",
    " -",
    "- ",
    ":",
    " -",
    "—",
    "–",
)


@dataclass
class TermDef:
    term: str
    definition: str


def fetch_html_requests(url: str, timeout: int = 30) -> str:
    """Fetch HTML content from a URL with a desktop User-Agent using requests."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        )
    }
    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def fetch_html_playwright(url: str, wait_selector: Optional[str] = None, timeout_ms: int = 30000) -> str:
    """Fetch fully rendered HTML using Playwright (Chromium)."""
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except Exception as e:  # ImportError or runtime failure
        raise RuntimeError("Playwright is not installed. Install with 'pip install playwright' and run 'playwright install chromium'.") from e

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        page.goto(url, wait_until="networkidle", timeout=timeout_ms)
        if wait_selector:
            try:
                page.wait_for_selector(wait_selector, timeout=timeout_ms)
            except Exception:
                # Continue even if the selector doesn't appear
                pass
        html = page.content()
        browser.close()
        return html


def clean_text(s: str) -> str:
    """Normalize whitespace and trim common artifacts."""
    s = re.sub(r"\s+", " ", s or "").strip()
    # Remove footnote/citation brackets like [1]
    s = re.sub(r"\[\d+\]", "", s)
    return s.strip(" \t\r\n\f\v")


def clean_term(term: str) -> str:
    term = clean_text(term)
    term = re.sub(r"^\d+[\.)]\s*", "", term)  # leading numbering
    term = term.strip('"\'“”‘’.,;:!?()[]{}')
    return term


def clean_definition(defn: str) -> str:
    defn = clean_text(defn)
    # Drop leading separators
    defn = re.sub(r"^[\-:.–—]\s*", "", defn)
    # Remove leading part-of-speech abbreviations like n., v., adj.
    defn = re.sub(r"^(\(?)(n|v|adj|adv)\.?\)?\s*[:,-]?\s*", "", defn, flags=re.I)
    return defn


def looks_like_term(s: str) -> bool:
    """Heuristic: short-ish word/phrase that could be a term."""
    s = s.strip()
    if not (2 <= len(s) <= 64):
        return False
    # Allow letters, spaces, hyphens, apostrophes
    return bool(re.match(r"^[A-Za-z][A-Za-z '\-()]*[A-Za-z)]$", s))


def looks_like_definition(s: str) -> bool:
    s = s.strip()
    return len(s) >= 8 and any(ch.isalpha() for ch in s)


def extract_from_definition_lists(soup: BeautifulSoup) -> List[TermDef]:
    pairs: List[TermDef] = []
    for dl in soup.find_all("dl"):
        dts = dl.find_all("dt")
        dds = dl.find_all("dd")
        if not dts or not dds or len(dds) < min(3, len(dts)):
            continue
        for i, dt in enumerate(dts):
            if i >= len(dds):
                break
            term = clean_term(dt.get_text(" ", strip=True))
            definition = clean_definition(dds[i].get_text(" ", strip=True))
            if looks_like_term(term) and looks_like_definition(definition):
                pairs.append(TermDef(term, definition))
    return pairs


def extract_from_tables(soup: BeautifulSoup) -> List[TermDef]:
    pairs: List[TermDef] = []
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue
        # Inspect header for likely columns
        header_cells = rows[0].find_all(["th", "td"]) if rows else []
        term_col = 0
        def_col = 1 if len(header_cells) > 1 else None
        header_text = "|".join(c.get_text(" ", strip=True).lower() for c in header_cells)
        if header_text:
            # Try to pick term and definition columns by name
            for idx, c in enumerate(header_cells):
                t = c.get_text(" ", strip=True).lower()
                if any(k in t for k in ("term", "word")):
                    term_col = idx
                if any(k in t for k in ("definition", "meaning", "gloss")):
                    def_col = idx
        for row in rows[1:]:
            cells = row.find_all(["td", "th"])  # some lists use <th> in body
            if not cells or (def_col is None and len(cells) < 2):
                continue
            tc = clean_term(cells[term_col].get_text(" ", strip=True)) if term_col < len(cells) else ""
            dc_idx = def_col if def_col is not None else (1 if len(cells) > 1 else 0)
            dc = clean_definition(cells[dc_idx].get_text(" ", strip=True)) if dc_idx < len(cells) else ""
            if looks_like_term(tc) and looks_like_definition(dc):
                pairs.append(TermDef(tc, dc))
    return pairs


def split_by_delimiters(text: str) -> Optional[Tuple[str, str]]:
    for delim in DELIMITERS:
        if delim in text:
            left, right = text.split(delim, 1)
            return left.strip(), right.strip()
    return None


def extract_from_lists(soup: BeautifulSoup) -> List[TermDef]:
    pairs: List[TermDef] = []
    for ul in soup.find_all(["ul", "ol"]):
        items = ul.find_all("li")
        if len(items) < 3:
            continue
        for li in items:
            # Prefer bold/strong term patterns
            strong = li.find(["strong", "b"]) or li.find(["em"])  # sometimes italics
            if strong and strong.get_text(strip=True):
                term = clean_term(strong.get_text(" ", strip=True))
                # Remove that node's text from the rest
                strong_text = strong.get_text(" ", strip=True)
                full_text = li.get_text(" ", strip=True)
                rem = full_text.replace(strong_text, "", 1)
                definition = clean_definition(rem)
                if looks_like_term(term) and looks_like_definition(definition):
                    pairs.append(TermDef(term, definition))
                    continue
            # Fallback: split the list item text by common delimiters
            text = li.get_text(" ", strip=True)
            maybe = split_by_delimiters(text)
            if maybe:
                term, definition = clean_term(maybe[0]), clean_definition(maybe[1])
                if looks_like_term(term) and looks_like_definition(definition):
                    pairs.append(TermDef(term, definition))
    return pairs


def extract_from_div_blocks(soup: BeautifulSoup) -> List[TermDef]:
    pairs: List[TermDef] = []
    # Target common class names that hint at vocab/glossary content only
    classes = re.compile(r"(vocab|vocabulary|glossary|term|definition|word[-_ ]list)", re.I)
    candidates = soup.find_all(class_=classes)
    seen: set[int] = set()
    for div in candidates:
        if not isinstance(div, Tag) or id(div) in seen:
            continue
        seen.add(id(div))
        header = div.find(["h1", "h2", "h3", "h4", "h5"]) or div.find(["strong", "b"])  # term-like
        if not header:
            continue
        term = clean_term(header.get_text(" ", strip=True))
        # Definition: text in the same div excluding header
        header.extract()
        definition = clean_definition(div.get_text(" ", strip=True))
        if looks_like_term(term) and looks_like_definition(definition):
            pairs.append(TermDef(term, definition))
    return pairs


def extract_from_paragraphs(soup: BeautifulSoup) -> List[TermDef]:
    pairs: List[TermDef] = []
    for p in soup.find_all(["p", "section"]):
        text = p.get_text("\n", strip=True)
        for line in filter(None, (ln.strip() for ln in text.split("\n"))):
            # First try explicit delimiters
            maybe = split_by_delimiters(line)
            if maybe:
                term, definition = clean_term(maybe[0]), clean_definition(maybe[1])
                if looks_like_term(term) and looks_like_definition(definition):
                    pairs.append(TermDef(term, definition))
                    continue
            # Try POS pattern: "term n. definition" / "term adj. definition"
            m = re.match(r"^\s*([A-Za-z][A-Za-z '\-]{0,60}?)\s+(?:\((n|v|adj|adv|interj|prep|pron|conj)\)|(?:(n|v|adj|adv|interj|prep|pron|conj)\.))\s*[:\-–—]?\s*(.+)$", line, flags=re.I)
            if m:
                term = clean_term(m.group(1))
                definition = clean_definition(m.group(4))
                if looks_like_term(term) and looks_like_definition(definition):
                    pairs.append(TermDef(term, definition))
    return pairs


def extract_from_br_line_blocks(soup: BeautifulSoup) -> List[TermDef]:
    """Handle pages that use <br> delimiters with bold/linked terms.

    Many older glossary pages (including Phrontistery) present entries as lines
    separated by <br>. We reconstruct lines from child nodes and parse patterns
    like:
      <b>Term</b> n. Definition
      <a><b>Term</b></a> — Definition
      Term – Definition
    """
    pairs: List[TermDef] = []

    # Candidate containers: areas with many <br> tags
    containers = []
    for tag in soup.find_all(["div", "p", "td", "section", "blockquote"]):
        brs = tag.find_all("br")
        if len(brs) >= 10:  # likely a real list block
            containers.append(tag)

    def flush_line(buf: List[str]):
        text = clean_text("".join(buf))
        if not text:
            return
        # Prefer delimiter split
        maybe = split_by_delimiters(text)
        if maybe:
            term, definition = clean_term(maybe[0]), clean_definition(maybe[1])
            if looks_like_term(term) and looks_like_definition(definition):
                pairs.append(TermDef(term, definition))
                return
        # Try POS pattern
        m = re.match(r"^\s*([A-Za-z][A-Za-z '\-]{0,60}?)\s+(?:\((n|v|adj|adv|interj|prep|pron|conj)\)|(?:(n|v|adj|adv|interj|prep|pron|conj)\.))\s*[:\-–—]?\s*(.+)$", text, flags=re.I)
        if m:
            term = clean_term(m.group(1))
            definition = clean_definition(m.group(4))
            if looks_like_term(term) and looks_like_definition(definition):
                pairs.append(TermDef(term, definition))

    best_pairs: List[TermDef] = []
    for cont in containers:
        line_buf: List[str] = []
        for node in cont.children:
            if isinstance(node, NavigableString):
                line_buf.append(str(node))
                continue
            if isinstance(node, Tag):
                if node.name == "br":
                    flush_line(line_buf)
                    line_buf = []
                    continue
                # If bold/strong/anchor early, treat as term followed by remaining
                if node.name in {"b", "strong"}:
                    # If buffer already has text, keep it; append term tokenized
                    term_text = clean_term(node.get_text(" ", strip=True))
                    if term_text:
                        # Represent as "<TERM> rest..." in buffer
                        if line_buf:
                            # If buffer is empty, better to place at start with a space
                            line_buf.append(term_text + " ")
                        else:
                            line_buf.append(term_text + " ")
                    continue
                if node.name == "a":
                    # Some pages wrap term in <a><b>Term</b></a>
                    term_child = node.find(["b", "strong"]) or node
                    term_text = clean_term(term_child.get_text(" ", strip=True))
                    if term_text:
                        line_buf.append(term_text + " ")
                    continue
                # Generic tag: append its text
                line_buf.append(node.get_text(" ", strip=True) + " ")
        # Flush last line if any text
        flush_line(line_buf)

        # Score container by number of pairs and consistency of first-letter
        if pairs:
            # Compute majority initial
            initials = [td.term[0].lower() for td in pairs if td.term]
            if initials:
                from collections import Counter

                counts = Counter(initials)
                common_initial, freq = counts.most_common(1)[0]
                ratio = freq / len(initials)
                # Prefer containers where most terms share an initial (as on letter pages)
                if ratio >= 0.6 and len(pairs) >= 10 and len(pairs) > len(best_pairs):
                    best_pairs = pairs[:]

        # Reset for next container
        pairs = []

    return best_pairs


def unique_in_order(pairs: Iterable[TermDef]) -> List[TermDef]:
    dedup: "OrderedDict[str, TermDef]" = OrderedDict()
    for td in pairs:
        key = td.term.lower()
        if key not in dedup and looks_like_term(td.term) and looks_like_definition(td.definition):
            dedup[key] = td
    return list(dedup.values())


def extract_terms_and_definitions(html: str) -> List[TermDef]:
    """Run multiple strategies and return unique term–definition pairs."""
    soup = BeautifulSoup(html, "html.parser")

    # Remove scripts/styles for cleaner text
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    # Site-specific: Phrontistery-style table (class="words")
    def extract_phrontistery_table() -> List[TermDef]:
        pairs: List[TermDef] = []
        table = soup.find("table", class_=re.compile(r"^words$", re.I))
        if not table:
            return pairs
        # This site uses malformed table rows/cells; parse by splitting on raw <td> tags
        table_html = str(table)
        # Split on <td ...> boundaries, capturing content until next <td>
        parts = re.split(r"(?i)<td[^>]*>", table_html)
        # parts[0] is before the first <td>; actual cells start from index 1
        cell_texts: List[str] = []
        for frag in parts[1:]:
            # Stop at the next <td or end of fragment
            # We already split at <td>, so this fragment is up to next <td>
            # Clean HTML tags within this fragment to plain text
            txt = BeautifulSoup(frag, "html.parser").get_text(" ", strip=True)
            if txt:
                cell_texts.append(txt)
        if len(cell_texts) < 10:
            return pairs
        # Skip header if present
        start_idx = 0
        if cell_texts and cell_texts[0].strip().lower() == "word":
            start_idx = 2 if len(cell_texts) > 1 else 0
        # Pair subsequent cells as term/definition
        for i in range(start_idx, len(cell_texts) - 1, 2):
            term = clean_term(cell_texts[i])
            definition = clean_definition(cell_texts[i + 1])
            if looks_like_term(term) and looks_like_definition(definition):
                pairs.append(TermDef(term, definition))
        # Heuristic: require a reasonable number of rows
        if len(pairs) >= 10:
            return pairs
        return []

    phr_pairs = extract_phrontistery_table()
    if phr_pairs:
        return unique_in_order(phr_pairs)

    # Try <br>-line blocks first; if strong match, return immediately
    br_pairs = extract_from_br_line_blocks(soup)
    if len(br_pairs) >= 10:
        return unique_in_order(br_pairs)

    strategies = (
        extract_from_definition_lists,
        extract_from_tables,
        extract_from_lists,
        extract_from_div_blocks,
        extract_from_paragraphs,
    )

    all_pairs: List[TermDef] = []
    for strat in strategies:
        try:
            pairs = strat(soup)
            if pairs:
                all_pairs.extend(pairs)
        except Exception:
            continue

    return unique_in_order(all_pairs)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Extract vocabulary terms from a URL")
    parser.add_argument("url", help="URL to examine for term–definition pairs")
    parser.add_argument(
        "--format",
        choices=("text", "json", "tsv"),
        default="text",
        help="Output format",
    )
    parser.add_argument(
        "--use-playwright",
        action="store_true",
        help="Use Playwright (Chromium) to render the page before extraction.",
    )
    parser.add_argument(
        "--wait-selector",
        help="Optional CSS selector to wait for when using Playwright.",
    )
    parser.add_argument(
        "--crawl-az",
        action="store_true",
        help="For phrontistery.info, crawl letter pages a.html through z.html.",
    )
    # Database options
    parser.add_argument("--db-host", help="MySQL host (overrides core config)")
    parser.add_argument("--db-port", type=int, help="MySQL port (overrides core config)")
    parser.add_argument("--db-name", help="MySQL database name (overrides core config)")
    parser.add_argument("--db-user", help="MySQL user (overrides core config)")
    parser.add_argument("--db-password", help="MySQL password (overrides core config)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not write to DB; just show what would be inserted.",
    )
    parser.add_argument(
        "--source-label",
        default=None,
        help="definition_source label to store (default auto-detects phrontistery).",
    )
    parser.add_argument(
        "--include-existing",
        action="store_true",
        help="Include terms already present in the database in the output (annotated). By default, outputs new terms only.",
    )
    parser.add_argument(
        "--print-terms",
        action="store_true",
        help="Print the list of extracted terms. By default only the summary is shown.",
    )
    args = parser.parse_args(argv)

    def fetch_and_extract(url: str) -> List[TermDef]:
        if args.use_playwright:
            html = fetch_html_playwright(url, wait_selector=args.wait_selector)
        else:
            html = fetch_html_requests(url)
        return extract_terms_and_definitions(html)

    # Crawl or single page
    from urllib.parse import urlparse, urlunparse
    try:
        parsed = urlparse(args.url)
        pairs: List[TermDef] = []
        if args.crawl_az and 'phrontistery.info' in parsed.netloc:
            base = f"{parsed.scheme}://{parsed.netloc}"
            letters = [chr(c) for c in range(ord('a'), ord('z') + 1)]
            seen: set[str] = set()
            for ch in letters:
                url = f"{base}/{ch}.html"
                try:
                    page_pairs = fetch_and_extract(url)
                except Exception as e:
                    print(f"Warning: failed to fetch {url}: {e}", file=sys.stderr)
                    continue
                for td in page_pairs:
                    k = td.term.lower()
                    if k not in seen:
                        seen.add(k)
                        pairs.append(td)
        else:
            pairs = fetch_and_extract(args.url)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    # Database filtering -------------------------------------------------------
    def resolve_db_config() -> Optional[dict]:
        cfg = None
        if get_core_db_config:
            try:
                cfg = get_core_db_config()
            except Exception:
                cfg = None
        # Allow env overrides
        env_cfg = {
            'host': os.getenv('DB_HOST'),
            'port': int(os.getenv('DB_PORT')) if os.getenv('DB_PORT') else None,
            'database': os.getenv('DB_NAME'),
            'user': os.getenv('DB_USER'),
            'password': os.getenv('DB_PASSWORD'),
        }
        # Apply CLI overrides
        cli_cfg = {
            'host': args.db_host,
            'port': args.db_port,
            'database': args.db_name,
            'user': args.db_user,
            'password': args.db_password,
        }
        # Merge priority: core < env < cli
        base = cfg or {}
        for k, v in env_cfg.items():
            if v is not None:
                base[k] = v
        for k, v in cli_cfg.items():
            if v is not None:
                base[k] = v
        # Validate minimal keys
        required = ('host', 'port', 'database', 'user', 'password')
        if all(k in base and base[k] not in (None, '') for k in required):
            return base
        return None

    def check_existing_terms(terms: List[str], db_cfg: dict) -> set[str]:
        existing: set[str] = set()
        try:
            conn = mysql.connector.connect(
                host=db_cfg['host'],
                port=db_cfg['port'],
                database=db_cfg['database'],
                user=db_cfg['user'],
                password=db_cfg['password'],
            )
            cursor = conn.cursor()
            # Chunk IN queries to avoid oversized packets
            chunk = 500
            for i in range(0, len(terms), chunk):
                batch = [t.lower() for t in terms[i:i+chunk]]
                placeholders = ','.join(['%s'] * len(batch))
                cursor.execute(
                    f"SELECT LOWER(term) FROM defined WHERE LOWER(term) IN ({placeholders})",
                    batch,
                )
                for (t,) in cursor.fetchall():
                    existing.add(t)
            cursor.close()
            conn.close()
        except MySQLError as e:
            print(f"Warning: DB check failed: {e}", file=sys.stderr)
        return existing

    db_cfg = resolve_db_config()
    statuses: dict[str, str] = {}
    existing: set[str] = set()
    if db_cfg:
        term_list = [td.term for td in pairs]
        existing = check_existing_terms(term_list, db_cfg)
        for td in pairs:
            statuses[td.term.lower()] = 'EXISTS' if td.term.lower() in existing else 'NEW'
        # Optionally filter to new only (default)
        if not args.include_existing:
            pairs = [td for td in pairs if statuses.get(td.term.lower()) == 'NEW']

    # Diagnostics summary (no secrets)
    total_found = len(statuses) if statuses else len(pairs)
    total_existing = sum(1 for k, v in statuses.items() if v == 'EXISTS') if statuses else 0
    total_new = sum(1 for k, v in statuses.items() if v == 'NEW') if statuses else len(pairs)

    # Insert new terms into defined -------------------------------------------
    inserted = 0
    if db_cfg and pairs and not args.dry_run:
        source_label = (
            args.source_label
            if args.source_label
            else ("phrontistery" if "phrontistery.info" in (urlparse(args.url).netloc) else "web")
        )
        today = date.today()
        try:
            conn = mysql.connector.connect(
                host=db_cfg['host'],
                port=db_cfg['port'],
                database=db_cfg['database'],
                user=db_cfg['user'],
                password=db_cfg['password'],
            )
            cur = conn.cursor()
            sql = (
                "INSERT INTO defined (term, definition, date_added, definition_source) "
                "VALUES (%s, %s, %s, %s)"
            )
            data = [(td.term, td.definition, today, source_label) for td in pairs]
            # Batch insert
            batch = 500
            for i in range(0, len(data), batch):
                cur.executemany(sql, data[i:i+batch])
                conn.commit()
            # We only insert NEW terms (filtered above), so this is reliable
            inserted = len(data)
            cur.close()
            conn.close()
        except MySQLError as e:
            print(f"Error inserting into DB: {e}", file=sys.stderr)
    elif not db_cfg:
        print("Warning: No DB configuration resolved; skipping insert. Pass --db-host/--db-user/--db-password or set env vars.", file=sys.stderr)
    elif args.dry_run:
        print("Dry run: DB insert skipped by --dry-run.", file=sys.stderr)

    # Output -------------------------------------------------------------------
    if args.format == "json":
        import json

        summary = {
            "db_target": (f"{db_cfg['host']}:{db_cfg['port']}/{db_cfg['database']} as {db_cfg['user']}" if db_cfg else None),
            "found": total_found,
            "existing": total_existing,
            "new": total_new,
            "inserted": inserted,
        }
        if args.print_terms:
            out = [summary]
            for td in pairs:
                item = {"term": td.term, "definition": td.definition}
                if db_cfg and args.include_existing:
                    item["status"] = statuses.get(td.term.lower(), 'NEW')
                out.append(item)
            print(json.dumps(out, ensure_ascii=False, indent=2))
        else:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
    elif args.format == "tsv":
        # Header line with summary as comments
        if db_cfg:
            print(f"# db_target\t{db_cfg['host']}:{db_cfg['port']}/{db_cfg['database']} as {db_cfg['user']}")
        print(f"# found\t{total_found}")
        print(f"# existing\t{total_existing}")
        print(f"# new\t{total_new}")
        print(f"# inserted\t{inserted}")
        if args.print_terms:
            for td in pairs:
                if db_cfg and args.include_existing:
                    print(f"{td.term}\t{td.definition}\t{statuses.get(td.term.lower(), 'NEW')}")
                else:
                    print(f"{td.term}\t{td.definition}")
    else:
        # Default: pretty text
        if db_cfg:
            print(f"DB: {db_cfg['host']}:{db_cfg['port']}/{db_cfg['database']} as {db_cfg['user']}")
        print(f"Found: {total_found}  Existing: {total_existing}  New: {total_new}  Inserted: {inserted}")
        if args.print_terms:
            for td in pairs:
                prefix = ""
                if db_cfg and args.include_existing:
                    prefix = f"[{statuses.get(td.term.lower(), 'NEW')}] "
                print(f"- {prefix}{td.term}: {td.definition}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
