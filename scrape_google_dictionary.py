# requirements:
# playwright
# pydantic
# tenacity
# httpx
# psycopg[binary]
# pandas
# regex

"""Dictionary scraper using dictionaryapi.dev API.

Fetches word definitions, pronunciations (IPA), examples, and audio files from
the Free Dictionary API (dictionaryapi.dev), which sources from Wiktionary.

Usage:
    python scrape_google_dictionary.py --word serendipity
    python scrape_google_dictionary.py --words-file data/words.txt --max-words 50 \
        --out-jsonl out/google_dict.jsonl --out-csv out/google_dict.csv
    python scrape_google_dictionary.py --words-file words.txt --pg-url postgresql://user:pass@host/db

Note: Google Dictionary scraping has been removed due to frequent page layout changes.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import logging
import random
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional, Sequence
from urllib.parse import quote_plus

import httpx
import pandas as pd
import regex as regex_lib
from pydantic import BaseModel, Field
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

try:
    import psycopg
    from psycopg import sql
except ImportError:  # pragma: no cover
    psycopg = None

from playwright.async_api import (  # noqa: E402
    BrowserContext,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    async_playwright,
)

LOGGER = logging.getLogger("google_dict")
DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)"
    " Chrome/124.0.0.0 Safari/537.36"
)
STORAGE_DIR = Path(".playwright-state")
AUDIO_URL_REGEX = re.compile(r"dictionary/.*/audio|dictionary/static/sounds", re.IGNORECASE)
IPA_REGEX = regex_lib.compile(r"/[^/]+/")


class DictionaryEntry(BaseModel):
    word: str
    locale: str
    pos: List[str] = Field(default_factory=list)
    ipa: List[str] = Field(default_factory=list)
    definitions: List[str] = Field(default_factory=list)
    examples: List[str] = Field(default_factory=list)
    source: Optional[str] = None
    audio_files: List[str] = Field(default_factory=list)
    status: str = "ok"
    error: Optional[str] = None
    scraped_at: datetime


@dataclass
class ScrapeConfig:
    locale: str
    hl: str
    delay_min: float
    delay_max: float
    fallback: bool
    audio_dir: Path


class ScrapeError(Exception):
    """Raised when scraping fails with a recoverable error."""


async def ensure_context(locale: str, hl: str) -> BrowserContext:
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    storage_state = STORAGE_DIR / f"state_{hl}.json"
    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            STORAGE_DIR / f"profile_{hl}",
            headless=True,
            locale=hl,
            user_agent=DEFAULT_UA,
            viewport={"width": 1280, "height": 720},
            extra_http_headers={
                "Accept-Language": locale,
                "User-Agent": DEFAULT_UA,
            },
            storage_state=str(storage_state) if storage_state.exists() else None,
        )
    return browser


async def get_browser_context(locale: str) -> BrowserContext:
    async_play = await async_playwright().start()
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    hl = locale.split("-", 1)[0]
    context = await async_play.chromium.launch_persistent_context(
        STORAGE_DIR / f"chromium_{hl}",
        headless=True,
        locale=locale,
        user_agent=DEFAULT_UA,
        viewport={"width": 1280, "height": 720},
        extra_http_headers={
            "Accept-Language": locale,
            "User-Agent": DEFAULT_UA,
        },
    )
    return context


async def wait_for_dictionary(page: Page) -> bool:
    selectors = [
        "[data-dobid='dfn']",
        "[data-dobid='hdw'] span",
        "[data-dobid='pos']",
        "div:has-text('Definitions of')",
        "div:has-text('Oxford Languages')",
        "g-main-card",
    ]
    timeout_ms = 12000
    for selector in selectors:
        try:
            await page.wait_for_selector(selector, state="visible", timeout=timeout_ms)
            return True
        except PlaywrightTimeoutError:
            try:
                await page.wait_for_selector(selector, state="attached", timeout=timeout_ms)
                return True
            except PlaywrightTimeoutError:
                continue
    try:
        await page.wait_for_function(
            '() => document.querySelector("[data-dobid=\\"dfn\\"]") || '
            'document.querySelector("[data-dobid=\\"hdw\\"]") || '
            'document.querySelector("[data-dobid=\\"pos\\"]")',
            timeout=timeout_ms,
        )
        return True
    except PlaywrightTimeoutError:
        return False


async def extract_texts(locator) -> List[str]:
    texts = await locator.all_text_contents()
    cleaned: List[str] = []
    for text in texts:
        stripped = text.strip()
        if stripped and stripped not in cleaned:
            cleaned.append(stripped)
    return cleaned


async def extract_google_dictionary(
    page: Page,
    word: str,
    locale: str,
    audio_urls: List[str],
    audio_dir: Path,
    http_client: httpx.AsyncClient,
) -> DictionaryEntry:
    pos_candidates = await extract_texts(page.locator("span[data-dobid='pos']"))
    if not pos_candidates:
        pos_candidates = [text.lower() for text in await extract_texts(page.locator("text=/noun|verb|adjective|adverb|pronoun|preposition/i"))]
    pos_set = {text.lower() for text in pos_candidates}

    definitions = await extract_texts(page.locator("div[data-dobid='dfn']"))
    if not definitions:
        definitions = await extract_texts(page.locator("ol li"))
    examples = await extract_texts(page.locator("div[data-dobid='ex']"))

    raw_spans = await extract_texts(page.locator("span"))
    ipa = sorted({text for text in raw_spans if IPA_REGEX.fullmatch(text)})

    headword = word.lower()
    for locator_str in [
        "div[data-dobid='hdw'] span",
        "span[data-dobid='hdw']",
        "div[role='heading'] span",
    ]:
        candidates = await extract_texts(page.locator(locator_str))
        if candidates:
            headword = candidates[0].lower()
            break

    attribution_candidates = await extract_texts(page.locator("text=/Oxford Languages/i"))
    if not attribution_candidates:
        attribution_candidates = await extract_texts(page.locator("footer span"))
    source = attribution_candidates[0] if attribution_candidates else "Google Dictionary"

    audio_files = await download_audio(audio_urls, headword, locale, audio_dir, http_client)

    return DictionaryEntry(
        word=headword,
        locale=locale,
        pos=sorted(pos_set),
        ipa=ipa,
        definitions=definitions,
        examples=examples,
        source=source,
        audio_files=audio_files,
        status="ok",
        scraped_at=datetime.now(timezone.utc),
    )


async def download_audio(
    urls: List[str], word: str, locale: str, audio_dir: Path, http_client: httpx.AsyncClient
) -> List[str]:
    audio_dir.mkdir(parents=True, exist_ok=True)
    saved_paths = []
    seen = set()
    for idx, url in enumerate(urls):
        if url in seen:
            continue
        seen.add(url)
        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(3),
                wait=wait_exponential(min=1, max=10),
                retry=retry_if_exception_type(httpx.HTTPError),
            ):
                with attempt:
                    response = await http_client.get(
                        url,
                        headers={"Referer": "https://www.google.com/"},
                        timeout=30.0,
                    )
                    response.raise_for_status()
                    break
        except httpx.HTTPError as exc:
            LOGGER.warning("Failed to download audio for %s from %s: %s", word, url, exc)
            continue
        suffix = Path(url.split("?")[0]).suffix or ".mp3"
        safe_word = re.sub(r"[^a-z0-9]+", "_", word.lower())
        file_path = audio_dir / f"{safe_word}__{locale}__{idx}{suffix}"
        file_path.write_bytes(response.content)
        saved_paths.append(str(file_path))
    return saved_paths


async def scrape_google_word(
    context: BrowserContext,
    word: str,
    cfg: ScrapeConfig,
    http_client: httpx.AsyncClient,
) -> DictionaryEntry:
    hl = cfg.hl
    url = f"https://www.google.com/search?q={quote_plus(f'define:{word}')}&hl={hl}"
    audio_urls: List[str] = []
    page = await context.new_page()

    def handle_response(response):
        url = response.url
        if AUDIO_URL_REGEX.search(url):
            audio_urls.append(url)

    page.on("response", handle_response)

    try:
        response = await page.goto(url, wait_until="domcontentloaded", timeout=15000)
        if response and response.status == 429:
            raise ScrapeError("HTTP 429 Too Many Requests")
        try:
            await page.wait_for_load_state("networkidle", timeout=8000)
        except PlaywrightTimeoutError:
            LOGGER.debug("Network idle wait timed out for %s", word)
    except PlaywrightTimeoutError as exc:
        raise ScrapeError(f"Navigation timeout for word '{word}': {exc}") from exc

    found = await wait_for_dictionary(page)
    if not found:
        raise ScrapeError("Dictionary widget not found")

    try:
        entry = await extract_google_dictionary(page, word, cfg.locale, audio_urls, cfg.audio_dir, http_client)
    finally:
        await page.close()
    return entry


async def fallback_dictionaryapi(word: str, cfg: ScrapeConfig, http_client: httpx.AsyncClient) -> DictionaryEntry:
    url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}"
    try:
        response = await http_client.get(url, timeout=20.0)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise ScrapeError(f"Fallback API failed: {exc}") from exc

    try:
        data = response.json()
    except json.JSONDecodeError as exc:
        raise ScrapeError(f"Invalid JSON from fallback: {exc}") from exc

    pos_set: set[str] = set()
    ipa: set[str] = set()
    definitions: List[str] = []
    examples: List[str] = []
    audio_urls: List[str] = []

    for entry in data:
        word_text = entry.get("word", word).lower()
        phonetics = entry.get("phonetics", [])
        for phon in phonetics:
            text = phon.get("text")
            if text:
                ipa.add(text.strip())
            audio_url = phon.get("audio")
            if audio_url:
                audio_urls.append(audio_url)
        meanings = entry.get("meanings", [])
        for meaning in meanings:
            part_of_speech = meaning.get("partOfSpeech")
            if part_of_speech:
                pos_set.add(part_of_speech)
            defs = meaning.get("definitions", [])
            for definition in defs:
                def_text = definition.get("definition")
                if def_text:
                    definitions.append(def_text.strip())
                example = definition.get("example")
                if example:
                    examples.append(example.strip())
    audio_files = await download_audio(audio_urls, word, cfg.locale, cfg.audio_dir, http_client)
    return DictionaryEntry(
        word=word.lower(),
        locale=cfg.locale,
        pos=sorted(pos_set),
        ipa=sorted(ipa),
        definitions=definitions,
        examples=examples,
        source="dictionaryapi.dev",
        audio_files=audio_files,
        status="ok",
        scraped_at=datetime.now(timezone.utc),
    )


async def process_word(
    context: BrowserContext,
    word: str,
    cfg: ScrapeConfig,
    http_client: httpx.AsyncClient,
) -> DictionaryEntry:
    """Process a word using dictionaryapi.dev (primary source).

    Google scraping has been disabled due to frequent page layout changes.
    """
    try:
        entry = await fallback_dictionaryapi(word, cfg, http_client)
        entry.status = "ok"
        return entry
    except ScrapeError as exc:
        LOGGER.error("API request failed for %s: %s", word, exc)
        return DictionaryEntry(
            word=word.lower(),
            locale=cfg.locale,
            status="error",
            error=str(exc),
            scraped_at=datetime.now(timezone.utc),
        )


def load_words(args: argparse.Namespace) -> List[str]:
    words: List[str] = []
    if args.words_file:
        path = Path(args.words_file)
        if not path.exists():
            raise FileNotFoundError(f"Words file not found: {path}")
        words.extend(word.strip() for word in path.read_text(encoding="utf-8").splitlines() if word.strip())
    if args.word:
        words.extend(args.word)
    deduped: List[str] = []
    seen = set()
    for word in words:
        normalized = word.strip()
        if not normalized:
            continue
        lowered = normalized.lower()
        if lowered not in seen:
            deduped.append(normalized)
            seen.add(lowered)
    if args.max_words is not None:
        deduped = deduped[: args.max_words]
    return deduped


def write_jsonl(path: Path, entries: Iterable[DictionaryEntry]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for entry in entries:
            handle.write(entry.model_dump_json())
            handle.write("\n")


def write_csv(path: Path, entries: List[DictionaryEntry]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for entry in entries:
        rows.append(
            {
                "word": entry.word,
                "locale": entry.locale,
                "status": entry.status,
                "source": entry.source,
                "pos": entry.pos[0] if entry.pos else "",
                "ipa": entry.ipa[0] if entry.ipa else "",
                "definition": entry.definitions[0] if entry.definitions else "",
                "scraped_at": entry.scraped_at.isoformat(),
            }
        )
    df = pd.DataFrame(rows)
    df.to_csv(path, index=False, quoting=csv.QUOTE_ALL)


def upsert_postgres(url: str, entries: List[DictionaryEntry]) -> None:
    if psycopg is None:
        LOGGER.error("psycopg is required for PostgreSQL operations")
        return
    if not entries:
        return
    LOGGER.info("Upserting %d entries into PostgreSQL", len(entries))
    with psycopg.connect(url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS google_dictionary_scrapes (
                    word TEXT NOT NULL,
                    locale TEXT NOT NULL,
                    pos JSONB,
                    ipa JSONB,
                    definitions JSONB,
                    examples JSONB,
                    source TEXT,
                    audio_files JSONB,
                    status TEXT,
                    error TEXT,
                    scraped_at TIMESTAMPTZ NOT NULL,
                    PRIMARY KEY(word, locale)
                )
                """
            )
            insert_query = sql.SQL(
                """
                INSERT INTO google_dictionary_scrapes
                (word, locale, pos, ipa, definitions, examples, source, audio_files, status, error, scraped_at)
                VALUES (%s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s::jsonb, %s, %s, %s)
                ON CONFLICT (word, locale)
                DO UPDATE SET
                    pos = EXCLUDED.pos,
                    ipa = EXCLUDED.ipa,
                    definitions = EXCLUDED.definitions,
                    examples = EXCLUDED.examples,
                    source = EXCLUDED.source,
                    audio_files = EXCLUDED.audio_files,
                    status = EXCLUDED.status,
                    error = EXCLUDED.error,
                    scraped_at = EXCLUDED.scraped_at
                """
            )
            for entry in entries:
                cur.execute(
                    insert_query,
                    (
                        entry.word,
                        entry.locale,
                        json.dumps(entry.pos),
                        json.dumps(entry.ipa),
                        json.dumps(entry.definitions),
                        json.dumps(entry.examples),
                        entry.source,
                        json.dumps(entry.audio_files),
                        entry.status,
                        entry.error,
                        entry.scraped_at,
                    ),
                )


async def async_main(args: argparse.Namespace) -> None:
    random.seed(42)
    locale = args.locale
    hl = locale.split("-", 1)[0]
    cfg = ScrapeConfig(
        locale=locale,
        hl=hl,
        delay_min=args.delay_min,
        delay_max=args.delay_max,
        fallback=args.fallback,
        audio_dir=Path(args.audio_dir),
    )
    if cfg.delay_min < 0 or cfg.delay_max < 0:
        raise ValueError("Delays must be non-negative")
    if cfg.delay_min > cfg.delay_max:
        cfg.delay_min, cfg.delay_max = cfg.delay_max, cfg.delay_min
    words = load_words(args)
    if not words:
        LOGGER.error("No words provided")
        return
    LOGGER.info("Processing %d words", len(words))
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            STORAGE_DIR / f"profile_{hl}",
            headless=True,
            locale=locale,
            user_agent=DEFAULT_UA,
            viewport={"width": 1280, "height": 720},
            extra_http_headers={
                "Accept-Language": locale,
                "User-Agent": DEFAULT_UA,
            },
        )
        async with httpx.AsyncClient(headers={"User-Agent": DEFAULT_UA}) as http_client:
            entries: List[DictionaryEntry] = []
            for idx, word in enumerate(words, 1):
                LOGGER.info("[%d/%d] %s", idx, len(words), word)
                try:
                    entry = await process_word(context, word, cfg, http_client)
                except Exception as exc:  # pragma: no cover
                    LOGGER.exception("Unhandled error for %s", word)
                    entry = DictionaryEntry(
                        word=word.lower(),
                        locale=locale,
                        status="error",
                        error=str(exc),
                        scraped_at=datetime.now(timezone.utc),
                    )
                entries.append(entry)
                delay = random.uniform(cfg.delay_min, cfg.delay_max)
                LOGGER.debug("Sleeping %.2f seconds", delay)
                await asyncio.sleep(delay)
        await context.close()
    out_jsonl = Path(args.out_jsonl)
    write_jsonl(out_jsonl, entries)
    out_csv = Path(args.out_csv)
    write_csv(out_csv, entries)
    if args.pg_url:
        upsert_postgres(args.pg_url, entries)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--words-file")
    parser.add_argument("--word", action="append")
    parser.add_argument("--locale", default="en-US")
    parser.add_argument("--out-jsonl", default="out/google_dict.jsonl")
    parser.add_argument("--out-csv", default="out/google_dict.csv")
    parser.add_argument("--audio-dir", default="out/audio")
    parser.add_argument("--pg-url")
    parser.add_argument("--max-words", type=int)
    parser.add_argument("--delay-min", type=float, default=6.0)
    parser.add_argument("--delay-max", type=float, default=15.0)
    parser.add_argument("--fallback", action="store_true")
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    try:
        asyncio.run(async_main(args))
    except KeyboardInterrupt:
        LOGGER.warning("Interrupted by user")


if __name__ == "__main__":
    main()
