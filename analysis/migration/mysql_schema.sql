-- MySQL dump 10.13  Distrib 8.0.43, for Linux (x86_64)
--
-- Host: 10.0.0.160    Database: vocab
-- ------------------------------------------------------
-- Server version	8.4.6-0ubuntu0.25.04.1

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Temporary view structure for view `candidate_review_queue`
--

DROP TABLE IF EXISTS `candidate_review_queue`;
/*!50001 DROP VIEW IF EXISTS `candidate_review_queue`*/;
SET @saved_cs_client     = @@character_set_client;
/*!50503 SET character_set_client = utf8mb4 */;
/*!50001 CREATE VIEW `candidate_review_queue` AS SELECT 
 1 AS `id`,
 1 AS `term`,
 1 AS `source_type`,
 1 AS `part_of_speech`,
 1 AS `utility_score`,
 1 AS `rarity_indicators`,
 1 AS `context_snippet`,
 1 AS `raw_definition`,
 1 AS `etymology_preview`,
 1 AS `date_discovered`,
 1 AS `review_status`,
 1 AS `days_pending`*/;
SET character_set_client = @saved_cs_client;

--
-- Table structure for table `candidate_words`
--

DROP TABLE IF EXISTS `candidate_words`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `candidate_words` (
  `id` int NOT NULL AUTO_INCREMENT,
  `term` varchar(100) NOT NULL,
  `source_type` enum('wiktionary','gutenberg','arxiv','pubmed','wikipedia','news_api','academic_journals','literary_classics','historical_documents','multi_source','other') NOT NULL,
  `source_reference` varchar(255) DEFAULT NULL,
  `context_snippet` text,
  `raw_definition` text,
  `etymology_preview` text,
  `part_of_speech` varchar(50) DEFAULT NULL,
  `utility_score` decimal(5,3) DEFAULT '0.000',
  `rarity_indicators` json DEFAULT NULL,
  `date_discovered` date DEFAULT (curdate()),
  `review_status` enum('pending','approved','rejected','needs_info') DEFAULT 'pending',
  `rejection_reason` varchar(255) DEFAULT NULL,
  `notes` text,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `unique_term_source` (`term`,`source_type`),
  KEY `idx_review_status` (`review_status`),
  KEY `idx_utility_score` (`utility_score` DESC),
  KEY `idx_date_discovered` (`date_discovered`),
  KEY `idx_source_type` (`source_type`),
  KEY `idx_term` (`term`)
) ENGINE=InnoDB AUTO_INCREMENT=1973 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `defined`
--

DROP TABLE IF EXISTS `defined`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `defined` (
  `id` int NOT NULL AUTO_INCREMENT,
  `term` varchar(100) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `part_of_speech` varchar(50) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `definition` text COLLATE utf8mb4_general_ci,
  `quizzed` int DEFAULT NULL,
  `correct2` int DEFAULT NULL,
  `date_added` date DEFAULT NULL,
  `frequency` double DEFAULT NULL,
  `wav_url` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `word_source` varchar(100) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `definition_source` varchar(100) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `bad` int DEFAULT NULL,
  `freq_src` text COLLATE utf8mb4_general_ci,
  `len` int DEFAULT NULL,
  `phrase` int DEFAULT NULL,
  `hyphenated` int DEFAULT NULL,
  `has_circular_definition` tinyint(1) DEFAULT '0',
  `corrected_definition` text COLLATE utf8mb4_general_ci,
  `needs_manual_circularity_review` tinyint(1) DEFAULT '0',
  `python_wordfreq` float DEFAULT NULL,
  `ngram_freq` double DEFAULT NULL,
  `commoncrawl_freq` decimal(8,3) DEFAULT NULL,
  `definition_reliability` decimal(3,2) DEFAULT NULL,
  `definition_updated` timestamp NULL DEFAULT NULL,
  `final_rarity` decimal(8,6) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=27337 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `defined_bu`
--

DROP TABLE IF EXISTS `defined_bu`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `defined_bu` (
  `id` int NOT NULL DEFAULT '0',
  `term` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `part_of_speech` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `definition` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci,
  `quizzed` int DEFAULT NULL,
  `correct2` int DEFAULT NULL,
  `date_added` date DEFAULT NULL,
  `frequency` double DEFAULT NULL,
  `wav_url` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `word_source` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `definition_source` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `bad` int DEFAULT NULL,
  `freq_src` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci,
  `len` int DEFAULT NULL,
  `phrase` int DEFAULT NULL,
  `hyphenated` int DEFAULT NULL,
  `has_circular_definition` tinyint(1) DEFAULT '0',
  `corrected_definition` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci,
  `needs_manual_circularity_review` tinyint(1) DEFAULT '0'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `definition_embeddings`
--

DROP TABLE IF EXISTS `definition_embeddings`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `definition_embeddings` (
  `word_id` int NOT NULL,
  `word` varchar(255) NOT NULL,
  `definition_text` text NOT NULL,
  `embedding_json` text,
  `embedding_model` varchar(100) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`word_id`),
  KEY `idx_model` (`embedding_model`),
  CONSTRAINT `definition_embeddings_ibfk_1` FOREIGN KEY (`word_id`) REFERENCES `defined` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `definition_similarity`
--

DROP TABLE IF EXISTS `definition_similarity`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `definition_similarity` (
  `word1_id` int NOT NULL,
  `word2_id` int NOT NULL,
  `cosine_similarity` decimal(6,5) DEFAULT NULL,
  `embedding_model` varchar(100) NOT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`word1_id`,`word2_id`,`embedding_model`),
  KEY `idx_cosine_similarity` (`cosine_similarity` DESC),
  KEY `idx_word1_similarity` (`word1_id`,`cosine_similarity` DESC),
  KEY `idx_word2_similarity` (`word2_id`,`cosine_similarity` DESC),
  CONSTRAINT `definition_similarity_ibfk_1` FOREIGN KEY (`word1_id`) REFERENCES `defined` (`id`) ON DELETE CASCADE,
  CONSTRAINT `definition_similarity_ibfk_2` FOREIGN KEY (`word2_id`) REFERENCES `defined` (`id`) ON DELETE CASCADE,
  CONSTRAINT `chk_def_word_order` CHECK ((`word1_id` < `word2_id`))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `documents`
--

DROP TABLE IF EXISTS `documents`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `documents` (
  `id` int NOT NULL AUTO_INCREMENT,
  `source_id` int NOT NULL,
  `external_id` varchar(255) DEFAULT NULL,
  `title` text,
  `url` text,
  `published_at` datetime DEFAULT NULL,
  `fetched_at` datetime NOT NULL,
  `hash` char(64) NOT NULL,
  `lang` varchar(8) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uniq_source_external` (`source_id`,`external_id`),
  KEY `idx_source_published` (`source_id`,`published_at`),
  CONSTRAINT `fk_documents_source` FOREIGN KEY (`source_id`) REFERENCES `sources` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=949 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `domains`
--

DROP TABLE IF EXISTS `domains`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `domains` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(100) NOT NULL,
  `description` text,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `name` (`name`)
) ENGINE=InnoDB AUTO_INCREMENT=19 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `flashcard_deck_items`
--

DROP TABLE IF EXISTS `flashcard_deck_items`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `flashcard_deck_items` (
  `id` int NOT NULL AUTO_INCREMENT,
  `deck_id` int NOT NULL,
  `word_id` int NOT NULL,
  `added_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `unique_deck_word` (`deck_id`,`word_id`),
  KEY `word_id` (`word_id`),
  CONSTRAINT `flashcard_deck_items_ibfk_1` FOREIGN KEY (`deck_id`) REFERENCES `flashcard_decks` (`id`) ON DELETE CASCADE,
  CONSTRAINT `flashcard_deck_items_ibfk_2` FOREIGN KEY (`word_id`) REFERENCES `defined` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `flashcard_decks`
--

DROP TABLE IF EXISTS `flashcard_decks`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `flashcard_decks` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(255) NOT NULL,
  `description` text,
  `user_id` int NOT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_user_decks` (`user_id`),
  CONSTRAINT `flashcard_decks_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=11 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `harvester_config`
--

DROP TABLE IF EXISTS `harvester_config`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `harvester_config` (
  `id` int NOT NULL AUTO_INCREMENT,
  `source_type` varchar(50) NOT NULL,
  `config_key` varchar(100) NOT NULL,
  `config_value` text,
  `description` text,
  `last_updated` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `unique_source_key` (`source_type`,`config_key`)
) ENGINE=InnoDB AUTO_INCREMENT=37 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `harvesting_sessions`
--

DROP TABLE IF EXISTS `harvesting_sessions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `harvesting_sessions` (
  `id` int NOT NULL AUTO_INCREMENT,
  `source_type` varchar(50) NOT NULL,
  `session_start` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `session_end` timestamp NULL DEFAULT NULL,
  `total_processed` int DEFAULT '0',
  `candidates_found` int DEFAULT '0',
  `candidates_accepted` int DEFAULT '0',
  `avg_utility_score` decimal(5,3) DEFAULT '0.000',
  `categories_processed` text,
  `status` enum('running','completed','failed','active','paused','error','unknown') DEFAULT 'running',
  `error_message` text,
  `notes` text,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=11 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Temporary view structure for view `harvesting_stats`
--

DROP TABLE IF EXISTS `harvesting_stats`;
/*!50001 DROP VIEW IF EXISTS `harvesting_stats`*/;
SET @saved_cs_client     = @@character_set_client;
/*!50503 SET character_set_client = utf8mb4 */;
/*!50001 CREATE VIEW `harvesting_stats` AS SELECT 
 1 AS `source_type`,
 1 AS `total_candidates`,
 1 AS `pending`,
 1 AS `approved`,
 1 AS `rejected`,
 1 AS `avg_score`,
 1 AS `last_discovery`,
 1 AS `first_discovery`*/;
SET character_set_client = @saved_cs_client;

--
-- Table structure for table `pronunciation_similarity`
--

DROP TABLE IF EXISTS `pronunciation_similarity`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `pronunciation_similarity` (
  `word1_id` int NOT NULL,
  `word2_id` int NOT NULL,
  `overall_similarity` decimal(6,5) DEFAULT NULL,
  `phonetic_distance` decimal(6,5) DEFAULT NULL,
  `stress_similarity` decimal(6,5) DEFAULT NULL,
  `rhyme_score` decimal(6,5) DEFAULT NULL,
  `syllable_similarity` decimal(6,5) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`word1_id`,`word2_id`),
  KEY `idx_overall_similarity` (`overall_similarity` DESC),
  KEY `idx_word1_similarity` (`word1_id`,`overall_similarity` DESC),
  KEY `idx_word2_similarity` (`word2_id`,`overall_similarity` DESC),
  KEY `idx_high_similarity` (`overall_similarity` DESC,`word1_id`,`word2_id`),
  CONSTRAINT `pronunciation_similarity_ibfk_1` FOREIGN KEY (`word1_id`) REFERENCES `defined` (`id`) ON DELETE CASCADE,
  CONSTRAINT `pronunciation_similarity_ibfk_2` FOREIGN KEY (`word2_id`) REFERENCES `defined` (`id`) ON DELETE CASCADE,
  CONSTRAINT `chk_word_order` CHECK ((`word1_id` < `word2_id`))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `quiz_sessions`
--

DROP TABLE IF EXISTS `quiz_sessions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `quiz_sessions` (
  `id` varchar(50) NOT NULL,
  `user_id` int DEFAULT NULL,
  `started_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `completed_at` timestamp NULL DEFAULT NULL,
  `quiz_type` varchar(20) DEFAULT NULL,
  `difficulty` varchar(20) DEFAULT NULL,
  `topic_domain` varchar(100) DEFAULT NULL,
  `topic_pos` varchar(50) DEFAULT NULL,
  `total_questions` int DEFAULT NULL,
  `correct_answers` int DEFAULT '0',
  `session_config` json DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_user_sessions` (`user_id`,`started_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `sources`
--

DROP TABLE IF EXISTS `sources`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `sources` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(255) NOT NULL,
  `type` varchar(64) NOT NULL,
  `url` text,
  `license` varchar(255) DEFAULT NULL,
  `enabled` tinyint(1) NOT NULL DEFAULT '1',
  `added_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uniq_name_type` (`name`,`type`)
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `spider_sessions`
--

DROP TABLE IF EXISTS `spider_sessions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `spider_sessions` (
  `id` int NOT NULL AUTO_INCREMENT,
  `session_id` varchar(100) NOT NULL,
  `start_time` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `end_time` timestamp NULL DEFAULT NULL,
  `total_urls_visited` int DEFAULT '0',
  `total_candidates_found` int DEFAULT '0',
  `sources_used` text,
  `session_config` text,
  `status` enum('running','completed','terminated','error') DEFAULT 'running',
  PRIMARY KEY (`id`),
  UNIQUE KEY `session_id` (`session_id`),
  KEY `idx_session_time` (`start_time`),
  KEY `idx_session_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `spider_source_performance`
--

DROP TABLE IF EXISTS `spider_source_performance`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `spider_source_performance` (
  `id` int NOT NULL AUTO_INCREMENT,
  `source_type` enum('wikipedia','arxiv','gutenberg','pubmed','news_api') NOT NULL,
  `date_tracked` date NOT NULL,
  `urls_visited` int DEFAULT '0',
  `success_rate` decimal(5,2) DEFAULT '0.00',
  `avg_candidates_per_url` decimal(8,2) DEFAULT '0.00',
  `avg_response_time_ms` int DEFAULT '0',
  `error_count` int DEFAULT '0',
  PRIMARY KEY (`id`),
  UNIQUE KEY `unique_source_date` (`source_type`,`date_tracked`),
  KEY `idx_source_performance` (`source_type`,`date_tracked`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `spider_visited_urls`
--

DROP TABLE IF EXISTS `spider_visited_urls`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `spider_visited_urls` (
  `id` int NOT NULL AUTO_INCREMENT,
  `url` varchar(2000) NOT NULL,
  `url_hash` varchar(64) NOT NULL,
  `source_type` enum('wikipedia','arxiv','gutenberg','pubmed','news_api') NOT NULL,
  `first_visited` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `last_visited` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `visit_count` int DEFAULT '1',
  `success_count` int DEFAULT '0',
  `candidates_found` int DEFAULT '0',
  `status` enum('success','failed','error','blocked') DEFAULT 'success',
  PRIMARY KEY (`id`),
  UNIQUE KEY `url_hash` (`url_hash`),
  KEY `idx_url_hash` (`url_hash`),
  KEY `idx_source_visited` (`source_type`,`last_visited`),
  KEY `idx_expiration` (`last_visited`)
) ENGINE=InnoDB AUTO_INCREMENT=4590 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `user_flashcard_progress`
--

DROP TABLE IF EXISTS `user_flashcard_progress`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `user_flashcard_progress` (
  `user_id` int NOT NULL,
  `word_id` int NOT NULL,
  `mastery_level` enum('learning','reviewing','mastered') DEFAULT 'learning',
  `study_count` int DEFAULT '0',
  `correct_count` int DEFAULT '0',
  `last_studied` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `next_review` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `interval_days` int DEFAULT '1',
  `ease_factor` float DEFAULT '2.5',
  PRIMARY KEY (`user_id`,`word_id`),
  KEY `idx_next_review` (`user_id`,`next_review`),
  KEY `idx_mastery` (`user_id`,`mastery_level`),
  KEY `word_id` (`word_id`),
  CONSTRAINT `user_flashcard_progress_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
  CONSTRAINT `user_flashcard_progress_ibfk_2` FOREIGN KEY (`word_id`) REFERENCES `defined` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `user_quiz_results`
--

DROP TABLE IF EXISTS `user_quiz_results`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `user_quiz_results` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `word_id` int NOT NULL,
  `question_type` enum('multiple_choice','true_false','matching') NOT NULL,
  `is_correct` tinyint(1) NOT NULL,
  `response_time_ms` int DEFAULT NULL,
  `answered_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `difficulty_level` enum('easy','medium','hard') DEFAULT 'medium',
  `session_id` varchar(50) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_user_word` (`user_id`,`word_id`),
  KEY `idx_user_time` (`user_id`,`answered_at`),
  KEY `idx_word_results` (`word_id`,`is_correct`),
  KEY `session_id` (`session_id`),
  CONSTRAINT `user_quiz_results_ibfk_1` FOREIGN KEY (`word_id`) REFERENCES `defined` (`id`) ON DELETE CASCADE,
  CONSTRAINT `user_quiz_results_ibfk_2` FOREIGN KEY (`session_id`) REFERENCES `quiz_sessions` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=37 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `user_word_mastery`
--

DROP TABLE IF EXISTS `user_word_mastery`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `user_word_mastery` (
  `user_id` int NOT NULL,
  `word_id` int NOT NULL,
  `mastery_level` enum('learning','reviewing','mastered') DEFAULT 'learning',
  `total_attempts` int DEFAULT '0',
  `correct_attempts` int DEFAULT '0',
  `last_seen` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `next_review` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `streak` int DEFAULT '0',
  `ease_factor` float DEFAULT '2.5',
  PRIMARY KEY (`user_id`,`word_id`),
  KEY `idx_next_review` (`user_id`,`next_review`),
  KEY `idx_mastery` (`user_id`,`mastery_level`),
  KEY `word_id` (`word_id`),
  CONSTRAINT `user_word_mastery_ibfk_1` FOREIGN KEY (`word_id`) REFERENCES `defined` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `users`
--

DROP TABLE IF EXISTS `users`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `users` (
  `id` int NOT NULL AUTO_INCREMENT,
  `username` varchar(50) NOT NULL,
  `email` varchar(255) NOT NULL,
  `full_name` varchar(255) DEFAULT NULL,
  `password_hash` varchar(255) NOT NULL,
  `role` enum('user','admin') DEFAULT 'user',
  `is_active` tinyint(1) DEFAULT '1',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `last_login_at` timestamp NULL DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `username` (`username`),
  UNIQUE KEY `email` (`email`),
  KEY `idx_username` (`username`),
  KEY `idx_email` (`email`),
  KEY `idx_role` (`role`),
  KEY `idx_active` (`is_active`)
) ENGINE=InnoDB AUTO_INCREMENT=12 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `word_domains`
--

DROP TABLE IF EXISTS `word_domains`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `word_domains` (
  `word_id` int NOT NULL,
  `primary_domain` varchar(100) DEFAULT NULL,
  `domain_id` int DEFAULT NULL,
  PRIMARY KEY (`word_id`),
  KEY `fk_word_domains_domain` (`domain_id`),
  CONSTRAINT `fk_word_domains_domain` FOREIGN KEY (`domain_id`) REFERENCES `domains` (`id`) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `word_domains_ibfk_1` FOREIGN KEY (`word_id`) REFERENCES `defined` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `word_frequencies_independent`
--

DROP TABLE IF EXISTS `word_frequencies_independent`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `word_frequencies_independent` (
  `word_id` int NOT NULL,
  `term` varchar(255) DEFAULT NULL,
  `independent_frequency` double DEFAULT NULL,
  `original_frequency` decimal(15,8) DEFAULT NULL,
  `source_frequencies` json DEFAULT NULL,
  `method_count` int DEFAULT NULL,
  `frequency_rank` int DEFAULT NULL,
  `rarity_percentile` decimal(5,2) DEFAULT NULL,
  `calculation_date` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`word_id`),
  KEY `idx_independent_frequency` (`independent_frequency`),
  KEY `idx_frequency_rank` (`frequency_rank`),
  KEY `idx_rarity_percentile` (`rarity_percentile`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `word_frequency_data`
--

DROP TABLE IF EXISTS `word_frequency_data`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `word_frequency_data` (
  `id` int NOT NULL AUTO_INCREMENT,
  `word` varchar(100) NOT NULL,
  `source` varchar(50) NOT NULL,
  `zipf_score` decimal(6,3) DEFAULT '0.000',
  `raw_frequency` decimal(15,10) DEFAULT '0.0000000000',
  `confidence` decimal(4,3) DEFAULT '0.000',
  `collection_date` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `metadata` json DEFAULT NULL,
  `composite_zipf` decimal(6,3) DEFAULT '0.000',
  `composite_confidence` decimal(4,3) DEFAULT '0.000',
  PRIMARY KEY (`id`),
  UNIQUE KEY `unique_word_source` (`word`,`source`),
  KEY `idx_word` (`word`),
  KEY `idx_zipf` (`zipf_score`),
  KEY `idx_composite` (`composite_zipf`)
) ENGINE=InnoDB AUTO_INCREMENT=17 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `word_phonetics`
--

DROP TABLE IF EXISTS `word_phonetics`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `word_phonetics` (
  `word_id` int NOT NULL,
  `word` varchar(255) NOT NULL,
  `ipa_transcription` text,
  `arpabet_transcription` text,
  `syllable_count` int DEFAULT NULL,
  `stress_pattern` varchar(50) DEFAULT NULL,
  `phonemes_json` text,
  `transcription_source` varchar(50) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`word_id`),
  KEY `idx_word` (`word`),
  KEY `idx_syllables` (`syllable_count`),
  KEY `idx_source` (`transcription_source`),
  CONSTRAINT `word_phonetics_ibfk_1` FOREIGN KEY (`word_id`) REFERENCES `defined` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping events for database 'vocab'
--

--
-- Dumping routines for database 'vocab'
--

--
-- Final view structure for view `candidate_review_queue`
--

/*!50001 DROP VIEW IF EXISTS `candidate_review_queue`*/;
/*!50001 SET @saved_cs_client          = @@character_set_client */;
/*!50001 SET @saved_cs_results         = @@character_set_results */;
/*!50001 SET @saved_col_connection     = @@collation_connection */;
/*!50001 SET character_set_client      = utf8mb4 */;
/*!50001 SET character_set_results     = utf8mb4 */;
/*!50001 SET collation_connection      = utf8mb4_0900_ai_ci */;
/*!50001 CREATE ALGORITHM=UNDEFINED */
/*!50013 DEFINER=`brian`@`%` SQL SECURITY DEFINER */
/*!50001 VIEW `candidate_review_queue` AS select `candidate_words`.`id` AS `id`,`candidate_words`.`term` AS `term`,`candidate_words`.`source_type` AS `source_type`,`candidate_words`.`part_of_speech` AS `part_of_speech`,`candidate_words`.`utility_score` AS `utility_score`,`candidate_words`.`rarity_indicators` AS `rarity_indicators`,`candidate_words`.`context_snippet` AS `context_snippet`,`candidate_words`.`raw_definition` AS `raw_definition`,`candidate_words`.`etymology_preview` AS `etymology_preview`,`candidate_words`.`date_discovered` AS `date_discovered`,`candidate_words`.`review_status` AS `review_status`,(to_days(curdate()) - to_days(`candidate_words`.`date_discovered`)) AS `days_pending` from `candidate_words` where (`candidate_words`.`review_status` = 'pending') order by `candidate_words`.`utility_score` desc,`candidate_words`.`date_discovered` */;
/*!50001 SET character_set_client      = @saved_cs_client */;
/*!50001 SET character_set_results     = @saved_cs_results */;
/*!50001 SET collation_connection      = @saved_col_connection */;

--
-- Final view structure for view `harvesting_stats`
--

/*!50001 DROP VIEW IF EXISTS `harvesting_stats`*/;
/*!50001 SET @saved_cs_client          = @@character_set_client */;
/*!50001 SET @saved_cs_results         = @@character_set_results */;
/*!50001 SET @saved_col_connection     = @@collation_connection */;
/*!50001 SET character_set_client      = utf8mb4 */;
/*!50001 SET character_set_results     = utf8mb4 */;
/*!50001 SET collation_connection      = utf8mb4_0900_ai_ci */;
/*!50001 CREATE ALGORITHM=UNDEFINED */
/*!50013 DEFINER=`brian`@`%` SQL SECURITY DEFINER */
/*!50001 VIEW `harvesting_stats` AS select `candidate_words`.`source_type` AS `source_type`,count(0) AS `total_candidates`,count((case when (`candidate_words`.`review_status` = 'pending') then 1 end)) AS `pending`,count((case when (`candidate_words`.`review_status` = 'approved') then 1 end)) AS `approved`,count((case when (`candidate_words`.`review_status` = 'rejected') then 1 end)) AS `rejected`,avg(`candidate_words`.`utility_score`) AS `avg_score`,max(`candidate_words`.`date_discovered`) AS `last_discovery`,min(`candidate_words`.`date_discovered`) AS `first_discovery` from `candidate_words` group by `candidate_words`.`source_type` */;
/*!50001 SET character_set_client      = @saved_cs_client */;
/*!50001 SET character_set_results     = @saved_cs_results */;
/*!50001 SET collation_connection      = @saved_col_connection */;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2025-09-29 17:51:43
