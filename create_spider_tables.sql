-- Spider URL visit tracking table with 120-day expiration
CREATE TABLE IF NOT EXISTS spider_visited_urls (
    id INT AUTO_INCREMENT PRIMARY KEY,
    url VARCHAR(2000) NOT NULL,
    url_hash VARCHAR(64) NOT NULL UNIQUE, -- SHA-256 hash for fast lookups
    source_type ENUM('wikipedia', 'arxiv', 'gutenberg', 'pubmed', 'news_api') NOT NULL,
    first_visited TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_visited TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    visit_count INT DEFAULT 1,
    success_count INT DEFAULT 0,
    candidates_found INT DEFAULT 0,
    status ENUM('success', 'failed', 'error', 'blocked') DEFAULT 'success',
    
    INDEX idx_url_hash (url_hash),
    INDEX idx_source_visited (source_type, last_visited),
    INDEX idx_expiration (last_visited)
);

-- Spider session tracking 
CREATE TABLE IF NOT EXISTS spider_sessions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    session_id VARCHAR(100) NOT NULL UNIQUE,
    start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    end_time TIMESTAMP NULL,
    total_urls_visited INT DEFAULT 0,
    total_candidates_found INT DEFAULT 0,
    sources_used TEXT, -- JSON array of sources
    session_config TEXT, -- JSON config
    status ENUM('running', 'completed', 'terminated', 'error') DEFAULT 'running',
    
    INDEX idx_session_time (start_time),
    INDEX idx_session_status (status)
);

-- Source performance tracking for adaptive balancing
CREATE TABLE IF NOT EXISTS spider_source_performance (
    id INT AUTO_INCREMENT PRIMARY KEY,
    source_type ENUM('wikipedia', 'arxiv', 'gutenberg', 'pubmed', 'news_api') NOT NULL,
    date_tracked DATE NOT NULL,
    urls_visited INT DEFAULT 0,
    success_rate DECIMAL(5,2) DEFAULT 0.00,
    avg_candidates_per_url DECIMAL(8,2) DEFAULT 0.00,
    avg_response_time_ms INT DEFAULT 0,
    error_count INT DEFAULT 0,
    
    UNIQUE KEY unique_source_date (source_type, date_tracked),
    INDEX idx_source_performance (source_type, date_tracked)
);

-- Clean up expired URLs (older than 120 days)
-- This can be run as a scheduled job
-- DELETE FROM spider_visited_urls WHERE last_visited < DATE_SUB(NOW(), INTERVAL 120 DAY);