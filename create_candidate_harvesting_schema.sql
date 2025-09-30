-- Wiktionary Harvester Database Schema
-- Schema for candidate word harvesting and review system

-- Primary candidate words table
CREATE TABLE IF NOT EXISTS candidate_words (
    id INT AUTO_INCREMENT PRIMARY KEY,
    term VARCHAR(100) NOT NULL,
    source_type ENUM('wiktionary', 'gutenberg', 'arxiv', 'other') NOT NULL,
    source_reference VARCHAR(255), -- Wiktionary URL or page title
    context_snippet TEXT, -- Definition or usage example
    raw_definition TEXT, -- Full definition from source
    etymology_preview TEXT, -- Basic etymology if available
    part_of_speech VARCHAR(50),
    utility_score DECIMAL(5,3) DEFAULT 0, -- 0-10 scoring
    rarity_indicators JSON, -- Store tags like "archaic", "obsolete", frequency estimates
    date_discovered DATE DEFAULT (CURRENT_DATE),
    review_status ENUM('pending', 'approved', 'rejected', 'needs_info') DEFAULT 'pending',
    rejection_reason VARCHAR(255),
    notes TEXT, -- For manual reviewer notes
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    UNIQUE KEY unique_term_source (term, source_type),
    INDEX idx_review_status (review_status),
    INDEX idx_utility_score (utility_score DESC),
    INDEX idx_date_discovered (date_discovered),
    INDEX idx_source_type (source_type),
    INDEX idx_term (term)
);

-- Configuration table for harvester settings
CREATE TABLE IF NOT EXISTS harvester_config (
    id INT AUTO_INCREMENT PRIMARY KEY,
    source_type VARCHAR(50) NOT NULL,
    config_key VARCHAR(100) NOT NULL,
    config_value TEXT,
    description TEXT,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY unique_source_key (source_type, config_key)
);

-- Harvesting session log
CREATE TABLE IF NOT EXISTS harvesting_sessions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    source_type VARCHAR(50) NOT NULL,
    session_start TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    session_end TIMESTAMP NULL,
    total_processed INT DEFAULT 0,
    candidates_found INT DEFAULT 0,
    candidates_accepted INT DEFAULT 0,
    avg_utility_score DECIMAL(5,3) DEFAULT 0,
    categories_processed TEXT, -- JSON array of categories processed
    status ENUM('running', 'completed', 'failed') DEFAULT 'running',
    error_message TEXT,
    notes TEXT
);

-- Insert initial configuration
INSERT IGNORE INTO harvester_config (source_type, config_key, config_value, description) VALUES
('wiktionary', 'last_processed_page', '0', 'Track progress through category pages'),
('wiktionary', 'target_tags', '["archaic", "obsolete", "dated", "historical"]', 'Tags that indicate target words'),
('wiktionary', 'min_utility_score', '3.0', 'Minimum utility score to accept candidates'),
('wiktionary', 'batch_size', '100', 'Number of pages to process per batch'),
('wiktionary', 'rate_limit_delay', '0.1', 'Delay in seconds between API calls'),
('wiktionary', 'target_categories', '["English archaic terms", "English obsolete terms", "English dated terms", "English historical terms"]', 'Wiktionary categories to harvest'),
('general', 'max_word_length', '20', 'Maximum word length to consider'),
('general', 'min_word_length', '3', 'Minimum word length to consider'),
('general', 'preferred_pos', '["noun", "verb", "adjective", "adverb"]', 'Preferred parts of speech');

-- View for review interface
CREATE OR REPLACE VIEW candidate_review_queue AS
SELECT 
    id,
    term,
    source_type,
    part_of_speech,
    utility_score,
    rarity_indicators,
    context_snippet,
    raw_definition,
    etymology_preview,
    date_discovered,
    review_status,
    DATEDIFF(CURRENT_DATE, date_discovered) as days_pending
FROM candidate_words
WHERE review_status = 'pending'
ORDER BY utility_score DESC, date_discovered ASC;

-- View for harvesting statistics
CREATE OR REPLACE VIEW harvesting_stats AS
SELECT 
    source_type,
    COUNT(*) as total_candidates,
    COUNT(CASE WHEN review_status = 'pending' THEN 1 END) as pending,
    COUNT(CASE WHEN review_status = 'approved' THEN 1 END) as approved,
    COUNT(CASE WHEN review_status = 'rejected' THEN 1 END) as rejected,
    AVG(utility_score) as avg_score,
    MAX(date_discovered) as last_discovery,
    MIN(date_discovered) as first_discovery
FROM candidate_words
GROUP BY source_type;