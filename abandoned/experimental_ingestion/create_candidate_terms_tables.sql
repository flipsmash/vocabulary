-- Candidate ingestion schema (idempotent)

CREATE TABLE IF NOT EXISTS sources (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(255) NOT NULL,
  type VARCHAR(64) NOT NULL,
  url TEXT NULL,
  license VARCHAR(255) NULL,
  enabled TINYINT(1) NOT NULL DEFAULT 1,
  added_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uniq_name_type (name, type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS documents (
  id INT AUTO_INCREMENT PRIMARY KEY,
  source_id INT NOT NULL,
  external_id VARCHAR(255) NULL,
  title TEXT NULL,
  url TEXT NULL,
  published_at DATETIME NULL,
  fetched_at DATETIME NOT NULL,
  hash CHAR(64) NOT NULL,
  lang VARCHAR(8) NULL,
  UNIQUE KEY uniq_source_external (source_id, external_id),
  KEY idx_source_published (source_id, published_at),
  CONSTRAINT fk_documents_source FOREIGN KEY (source_id)
    REFERENCES sources(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS candidate_terms (
  id INT AUTO_INCREMENT PRIMARY KEY,
  lemma VARCHAR(255) NOT NULL,
  display VARCHAR(255) NOT NULL,
  lang VARCHAR(8) NOT NULL DEFAULT 'en',
  pos VARCHAR(32) NULL,
  ngram_len TINYINT NOT NULL DEFAULT 1,
  status ENUM('new','queued','reviewing','promoted','rejected') NOT NULL DEFAULT 'new',
  origin VARCHAR(64) NULL,
  primary_source_id INT NULL,
  origin_sources_json JSON NULL,
  first_seen_at DATETIME NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uniq_lemma_lang_ngram (lemma, lang, ngram_len),
  KEY idx_status (status),
  CONSTRAINT fk_candidate_primary_source FOREIGN KEY (primary_source_id)
    REFERENCES sources(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS candidate_observations (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  candidate_id INT NOT NULL,
  document_id INT NOT NULL,
  token_or_phrase VARCHAR(255) NOT NULL,
  start_idx INT NULL,
  context_snippet VARCHAR(512) NULL,
  observed_at DATETIME NOT NULL,
  KEY idx_candidate (candidate_id),
  CONSTRAINT fk_obs_candidate FOREIGN KEY (candidate_id)
    REFERENCES candidate_terms(id) ON DELETE CASCADE,
  CONSTRAINT fk_obs_document FOREIGN KEY (document_id)
    REFERENCES documents(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS candidate_metrics (
  candidate_id INT PRIMARY KEY,
  computed_at DATETIME NOT NULL,
  score DOUBLE NULL,
  rarity_z DOUBLE NULL,
  burstiness DOUBLE NULL,
  source_diversity DOUBLE NULL,
  context_diversity DOUBLE NULL,
  novelty DOUBLE NULL,
  length_complexity DOUBLE NULL,
  typo_risk DOUBLE NULL,
  safety_penalty DOUBLE NULL,
  metrics_json JSON NULL,
  CONSTRAINT fk_metrics_candidate FOREIGN KEY (candidate_id)
    REFERENCES candidate_terms(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS definition_candidates (
  id INT AUTO_INCREMENT PRIMARY KEY,
  candidate_id INT NOT NULL,
  source VARCHAR(32) NOT NULL,
  pos VARCHAR(32) NULL,
  gloss TEXT NULL,
  example TEXT NULL,
  sense_key VARCHAR(255) NULL,
  confidence DOUBLE NULL,
  added_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_def_cand (candidate_id),
  CONSTRAINT fk_def_candidate FOREIGN KEY (candidate_id)
    REFERENCES candidate_terms(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS promotions (
  id INT AUTO_INCREMENT PRIMARY KEY,
  candidate_id INT NOT NULL,
  term_id INT NULL,
  promoted_at DATETIME NOT NULL,
  notes TEXT NULL,
  KEY idx_prom_cand (candidate_id),
  CONSTRAINT fk_prom_candidate FOREIGN KEY (candidate_id)
    REFERENCES candidate_terms(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS rejections (
  id INT AUTO_INCREMENT PRIMARY KEY,
  candidate_id INT NOT NULL,
  reason_code VARCHAR(64) NULL,
  notes TEXT NULL,
  rejected_at DATETIME NOT NULL,
  KEY idx_rej_cand (candidate_id),
  CONSTRAINT fk_rej_candidate FOREIGN KEY (candidate_id)
    REFERENCES candidate_terms(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS terms (
  id INT AUTO_INCREMENT PRIMARY KEY,
  lemma VARCHAR(255) NOT NULL,
  display VARCHAR(255) NOT NULL,
  lang VARCHAR(8) NOT NULL DEFAULT 'en',
  pos VARCHAR(32) NULL,
  definition TEXT NULL,
  definition_source VARCHAR(64) NULL,
  examples_json JSON NULL,
  pronunciation VARCHAR(255) NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uniq_terms (lemma, lang)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

