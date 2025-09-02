-- User Management Tables for Vocabulary Application
-- Creates users table and related structures for authentication and authorization

USE vocab;

-- Users table
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    full_name VARCHAR(255),
    password_hash VARCHAR(255) NOT NULL,
    role ENUM('user', 'admin') DEFAULT 'user',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    last_login_at TIMESTAMP NULL,
    
    INDEX idx_username (username),
    INDEX idx_email (email),
    INDEX idx_role (role),
    INDEX idx_active (is_active)
);

-- User quiz statistics table (for future use)
CREATE TABLE IF NOT EXISTS user_quiz_stats (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    total_quizzes INT DEFAULT 0,
    total_questions INT DEFAULT 0,
    correct_answers INT DEFAULT 0,
    accuracy_percentage DECIMAL(5,2) DEFAULT 0.00,
    streak_current INT DEFAULT 0,
    streak_best INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_user_id (user_id)
);

-- User word interactions table (for tracking which words users have studied)
CREATE TABLE IF NOT EXISTS user_word_interactions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    word_id INT NOT NULL,
    interaction_type ENUM('viewed', 'quizzed_correct', 'quizzed_incorrect', 'favorited') NOT NULL,
    interaction_count INT DEFAULT 1,
    first_interaction_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_interaction_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (word_id) REFERENCES defined(id) ON DELETE CASCADE,
    UNIQUE KEY unique_user_word_type (user_id, word_id, interaction_type),
    INDEX idx_user_id (user_id),
    INDEX idx_word_id (word_id),
    INDEX idx_interaction_type (interaction_type)
);

-- Insert a default admin user (password: admin123)
-- Password hash for 'admin123' using bcrypt
INSERT IGNORE INTO users (username, email, full_name, password_hash, role) 
VALUES ('admin', 'admin@vocab.local', 'System Administrator', 
        '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBVdTJP9M9k.6e', 'admin');