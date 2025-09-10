#!/usr/bin/env python3
"""
Respectful Web Scraping Infrastructure
Human-like behavior, rate limiting, and ethical scraping practices
"""

import asyncio
import aiohttp
import random
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import json
import logging
from dataclasses import dataclass
from pathlib import Path
import re
from bs4 import BeautifulSoup
import hashlib

# Respectful scraping configuration
RESPECTFUL_SCRAPING_CONFIG = {
    "human_simulation": {
        "min_delay_seconds": 2,
        "max_delay_seconds": 8, 
        "random_variance": True,
        "session_duration_minutes": 30,    # Take breaks like humans
        "break_duration_minutes": 10,
        "max_pages_per_session": 20
    },
    
    "daily_limits_per_source": {
        "atlantic": 12,          # ~1 per 2 hours during waking hours
        "newyorker": 10,
        "harpers": 8,
        "lrb": 6,
        "nybooks": 6,
        "arxiv": 50,             # Papers per day
        "pubmed": 30,            # Abstracts per day
        "gutenberg": 25          # Books per day
    },
    
    "browser_simulation": {
        "user_agent_rotation": True,
        "realistic_headers": True,
        "javascript_disabled": True,      # Faster, more respectful
        "image_loading_disabled": True,   # Save bandwidth
        "css_loading_disabled": True
    },
    
    "error_handling": {
        "max_retries": 2,
        "exponential_backoff": True,
        "circuit_breaker_errors": 5,     # Stop after 5 errors
        "circuit_breaker_timeout_hours": 24
    }
}

@dataclass
class ScrapingSession:
    """Track a scraping session for human-like behavior"""
    source: str
    start_time: datetime
    pages_scraped: int = 0
    errors_encountered: int = 0
    is_active: bool = True
    last_request_time: Optional[datetime] = None


class RespectfulWebScraper:
    """Ethical web scraper with human-like behavior patterns"""
    
    def __init__(self):
        self.config = RESPECTFUL_SCRAPING_CONFIG
        self.sessions: Dict[str, ScrapingSession] = {}
        self.circuit_breakers: Dict[str, datetime] = {}
        self.daily_counts = self._load_daily_counts()
        self.logger = logging.getLogger(__name__)
        
        # Rotating user agents for different "users"
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:89.0) Gecko/20100101 Firefox/89.0",
        ]
        
    def _load_daily_counts(self) -> Dict[str, Dict[str, int]]:
        """Load daily scraping counts from file"""
        counts_file = Path("scraping_counts.json")
        today = datetime.now().strftime("%Y-%m-%d")
        
        try:
            if counts_file.exists():
                with open(counts_file, 'r') as f:
                    all_counts = json.load(f)
                return all_counts.get(today, {})
            else:
                return {}
        except Exception:
            return {}
    
    def _save_daily_counts(self):
        """Save daily scraping counts to file"""
        counts_file = Path("scraping_counts.json")
        today = datetime.now().strftime("%Y-%m-%d")
        
        try:
            all_counts = {}
            if counts_file.exists():
                with open(counts_file, 'r') as f:
                    all_counts = json.load(f)
            
            all_counts[today] = self.daily_counts
            
            # Keep only last 7 days
            cutoff_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
            all_counts = {k: v for k, v in all_counts.items() if k >= cutoff_date}
            
            with open(counts_file, 'w') as f:
                json.dump(all_counts, f, indent=2)
                
        except Exception as e:
            self.logger.warning(f"Failed to save daily counts: {e}")
    
    async def fetch_article_content(self, url: str, source_name: str) -> Optional[str]:
        """Fetch article content with respectful rate limiting"""
        
        # Check circuit breaker
        if self._is_circuit_broken(source_name):
            self.logger.info(f"Circuit breaker active for {source_name}, skipping")
            return None
        
        # Check daily limits
        if not self._can_scrape_today(source_name):
            self.logger.info(f"Daily limit reached for {source_name}")
            return None
        
        # Ensure we have an active session
        await self._ensure_active_session(source_name)
        session = self.sessions.get(source_name)
        
        if not session or not session.is_active:
            self.logger.info(f"No active session for {source_name}")
            return None
        
        try:
            # Human-like delay before request
            await self._human_like_delay(source_name)
            
            # Make the request
            content = await self._make_respectful_request(url, source_name)
            
            if content:
                # Update session tracking
                session.pages_scraped += 1
                session.last_request_time = datetime.now()
                self.daily_counts[source_name] = self.daily_counts.get(source_name, 0) + 1
                
                self._save_daily_counts()
                return content
            else:
                session.errors_encountered += 1
                return None
                
        except Exception as e:
            self.logger.error(f"Error fetching {url}: {e}")
            if session:
                session.errors_encountered += 1
            self._handle_scraping_error(source_name)
            return None
    
    async def _make_respectful_request(self, url: str, source_name: str) -> Optional[str]:
        """Make a single respectful HTTP request"""
        
        headers = {
            'User-Agent': random.choice(self.user_agents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Cache-Control': 'max-age=0'
        }
        
        # Add source-specific headers if needed
        if 'gutenberg' in source_name.lower():
            headers['User-Agent'] = f"VocabularyResearchBot/1.0 (Educational; {headers['User-Agent']})"
        
        timeout = aiohttp.ClientTimeout(total=30, connect=10)
        
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            try:
                async with session.get(url) as response:
                    if response.status == 200:
                        content = await response.text()
                        return content
                    elif response.status == 429:  # Rate limited
                        self.logger.warning(f"Rate limited by {source_name}, backing off")
                        await asyncio.sleep(random.uniform(300, 600))  # 5-10 minute backoff
                        return None
                    elif response.status >= 400:
                        self.logger.warning(f"HTTP {response.status} from {url}")
                        return None
                    else:
                        return None
                        
            except asyncio.TimeoutError:
                self.logger.warning(f"Timeout fetching {url}")
                return None
            except Exception as e:
                self.logger.error(f"Request error for {url}: {e}")
                return None
    
    async def _ensure_active_session(self, source_name: str):
        """Ensure we have an active scraping session for the source"""
        
        if source_name not in self.sessions:
            # Start new session
            self.sessions[source_name] = ScrapingSession(
                source=source_name,
                start_time=datetime.now()
            )
            self.logger.info(f"Started new scraping session for {source_name}")
        else:
            session = self.sessions[source_name]
            
            # Check if session needs a break
            session_duration = (datetime.now() - session.start_time).total_seconds() / 60
            config = self.config['human_simulation']
            
            if (session_duration > config['session_duration_minutes'] or
                session.pages_scraped >= config['max_pages_per_session']):
                
                self.logger.info(f"Taking break for {source_name} session")
                session.is_active = False
                
                # Wait for break duration
                break_time = random.uniform(
                    config['break_duration_minutes'] * 0.8,
                    config['break_duration_minutes'] * 1.2
                ) * 60
                
                await asyncio.sleep(break_time)
                
                # Start fresh session
                self.sessions[source_name] = ScrapingSession(
                    source=source_name,
                    start_time=datetime.now()
                )
                self.logger.info(f"Resumed scraping session for {source_name}")
    
    async def _human_like_delay(self, source_name: str):
        """Add human-like delay between requests"""
        session = self.sessions.get(source_name)
        
        if session and session.last_request_time:
            # Calculate time since last request
            time_since_last = (datetime.now() - session.last_request_time).total_seconds()
            
            config = self.config['human_simulation']
            min_delay = config['min_delay_seconds']
            max_delay = config['max_delay_seconds']
            
            # Add random variance
            if config['random_variance']:
                min_delay *= random.uniform(0.8, 1.2)
                max_delay *= random.uniform(0.8, 1.2)
            
            required_delay = random.uniform(min_delay, max_delay)
            
            if time_since_last < required_delay:
                sleep_time = required_delay - time_since_last
                self.logger.debug(f"Human-like delay: {sleep_time:.1f}s for {source_name}")
                await asyncio.sleep(sleep_time)
    
    def _can_scrape_today(self, source_name: str) -> bool:
        """Check if we can still scrape from this source today"""
        daily_limit = self.config['daily_limits_per_source'].get(source_name, 100)
        current_count = self.daily_counts.get(source_name, 0)
        return current_count < daily_limit
    
    def _is_circuit_broken(self, source_name: str) -> bool:
        """Check if circuit breaker is active for this source"""
        if source_name not in self.circuit_breakers:
            return False
        
        break_time = self.circuit_breakers[source_name]
        timeout_hours = self.config['error_handling']['circuit_breaker_timeout_hours']
        
        if datetime.now() - break_time < timedelta(hours=timeout_hours):
            return True
        else:
            # Reset circuit breaker
            del self.circuit_breakers[source_name]
            return False
    
    def _handle_scraping_error(self, source_name: str):
        """Handle scraping errors and activate circuit breaker if needed"""
        session = self.sessions.get(source_name)
        if not session:
            return
        
        max_errors = self.config['error_handling']['circuit_breaker_errors']
        
        if session.errors_encountered >= max_errors:
            self.logger.warning(f"Circuit breaker activated for {source_name}")
            self.circuit_breakers[source_name] = datetime.now()
            session.is_active = False
    
    def extract_text_content(self, html: str, source_name: str) -> str:
        """Extract clean text content from HTML"""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Remove script and style elements
            for script in soup(["script", "style", "nav", "footer", "aside"]):
                script.decompose()
            
            # Source-specific extraction rules
            if 'atlantic' in source_name.lower():
                # Atlantic-specific selectors
                content = soup.find('div', class_='article-body') or soup.find('section', class_='l-article__container')
            elif 'newyorker' in source_name.lower():
                content = soup.find('div', class_='ArticleBodyWrapper') or soup.find('div', class_='content')
            elif 'harpers' in source_name.lower():
                content = soup.find('div', class_='entry-content') or soup.find('article')
            elif 'lrb' in source_name.lower():
                content = soup.find('div', class_='article-body') or soup.find('div', class_='content')
            elif 'nybooks' in source_name.lower():
                content = soup.find('div', class_='article__body') or soup.find('div', class_='content')
            else:
                # Generic extraction
                content = (soup.find('article') or 
                          soup.find('div', class_=re.compile(r'content|article|body')) or
                          soup.find('main') or 
                          soup)
            
            if content:
                # Extract paragraphs
                paragraphs = content.find_all('p')
                text_parts = [p.get_text().strip() for p in paragraphs if p.get_text().strip()]
                
                if text_parts:
                    return '\n\n'.join(text_parts)
            
            # Fallback: get all text
            return soup.get_text()
            
        except Exception as e:
            self.logger.error(f"Error extracting text from {source_name}: {e}")
            return ""
    
    def get_session_stats(self) -> Dict[str, Dict]:
        """Get current session statistics"""
        stats = {}
        
        for source_name, session in self.sessions.items():
            stats[source_name] = {
                'pages_scraped': session.pages_scraped,
                'errors': session.errors_encountered,
                'session_duration_minutes': (datetime.now() - session.start_time).total_seconds() / 60,
                'is_active': session.is_active,
                'daily_count': self.daily_counts.get(source_name, 0),
                'daily_limit': self.config['daily_limits_per_source'].get(source_name, 100),
                'circuit_broken': self._is_circuit_broken(source_name)
            }
        
        return stats