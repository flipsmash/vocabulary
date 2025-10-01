# Experimental Ingestion System - ABANDONED

This folder contains the experimental ingestion pipeline that was developed but ultimately abandoned in favor of the current harvesting system.

## What was moved here:

### Core Experimental System:
- `ingestion/` folder - Complete experimental ingestion pipeline
  - `models.py` - CandidateRepo with candidate_terms table structure  
  - `pipeline.py` - RSS/ArXiv/GitHub ingestion pipelines
  - `connectors/` - RSS, ArXiv, and GitHub connectors
  - `definitions.py` - Definition fetching utilities
  - `filters.py` - Token filtering logic
  - `scoring.py` - Candidate scoring algorithms

### Database Schema:
- `create_candidate_terms_tables.sql` - Experimental database schema with:
  - `candidate_terms` - Main candidates table
  - `candidate_observations` - Context tracking
  - `candidate_metrics` - Advanced scoring metrics
  - `definition_candidates` - Definition sources
  - `sources` and `documents` - Source tracking

## Why was this abandoned?

This experimental system was designed as a "minimal end-to-end flow" for processing RSS feeds, ArXiv papers, and GitHub releases. However, it was abandoned because:

1. **Complexity vs. Value**: The system was over-engineered for the vocabulary extraction use case
2. **Source Limitations**: RSS feeds and GitHub releases don't contain rich vocabulary like classic literature  
3. **Existing System**: The current harvesting system (`candidate_words` table) was already working well
4. **Focus Shift**: Decision to focus on high-quality sources like Project Gutenberg and Wiktionary

## Current Active System

The current system uses:
- **Database**: `candidate_words` table with simpler, more focused structure
- **Sources**: Project Gutenberg (classic literature), Wiktionary (archaic terms)
- **Tools**: 
  - `gutenberg_harvester.py` - Rich vocabulary from classic texts
  - `wiktionary_harvester.py` - Archaic and obsolete terms  
  - `wiktionary_reviewer.py` - Manual review interface
  - `vocabulary_orchestrator.py` - Coordinated harvesting

## Database Impact

The experimental tables (`candidate_terms`, `candidate_observations`, etc.) may still exist in the database but are no longer used. The active system uses the `candidate_words` table.

## Code References Removed

References to this experimental system were removed from:
- `main_cli.py` - Removed `--ingest-run` options for RSS/ArXiv/GitHub
- Command line options for experimental ingestion

**DO NOT USE FILES IN THIS FOLDER** - They are preserved for reference only.

The current system provides better vocabulary quality through focused harvesting of classic literature and specialized linguistic resources.