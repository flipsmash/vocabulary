# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Core Application Commands
```bash
# Main CLI interface (pronunciation similarity)
python cuda_enhanced_cli.py --help

# Process words with phonetic transcriptions
python cuda_enhanced_cli.py --process-words --batch-size 1000

# Calculate pronunciation similarities (GPU accelerated)
python cuda_enhanced_cli.py --calculate-similarities --similarity-threshold 0.2

# Find pronunciation-based quiz distractors
python cuda_enhanced_cli.py --find-distractors 12345 --num-distractors 4

# Check CUDA setup
python cuda_enhanced_cli.py --check-cuda

# Generate system status report
python cuda_enhanced_cli.py --status

# Alternative main CLI (wrapper)
python main_cli.py --find-semantic-distractors 12345
```

### Definition Similarity Commands
```bash
# Process definitions and calculate semantic similarities
python definition_similarity_calculator.py

# Process definitions in chunks
python process_definitions_chunked.py
```

### Testing and Quality Assurance
```bash
# Run tests
pytest tests/ -v --cov=pronunciation --cov-report=term-missing

# Code formatting
black . --line-length 88
isort . --profile black

# Type checking
mypy . --ignore-missing-imports

# Linting
flake8 .
```

### Database and Performance
```bash
# Check database connectivity
python config.py

# Monitor MySQL performance
python mysql_performance_monitor.py

# Populate phonetic metrics
python populate_phonetic_metrics.py
```

### Web Application
```bash
# Run simple vocabulary web app
python simple_vocab_app.py

# Run full vocabulary web application
python vocabulary_web_app.py
```

## Architecture Overview

### Core System Components

**CUDA-Accelerated Pronunciation Engine**: The primary system uses GPU acceleration for massive-scale phonetic similarity calculations (240M+ word pairs). Key files:
- `cuda_enhanced_cli.py` - Main CUDA-accelerated CLI interface
- `cuda_similarity_calculator.py` - GPU-based similarity computation
- `modern_pronunciation_system.py` - Phonetic processing pipeline
- `custom_database_manager.py` - Database operations and optimization

**Definition Similarity System**: Semantic similarity calculations for vocabulary definitions:
- `definition_similarity_calculator.py` - Main semantic similarity engine
- `process_definitions_chunked.py` - Chunked processing for large datasets
- `ai_definition_corrector.py` - AI-powered definition quality improvement

**Web Applications**: Multiple web interfaces for vocabulary management:
- `vocabulary_web_app.py` - Full-featured web application with user authentication
- `simple_vocab_app.py` - Simplified vocabulary interface
- `auth.py` - User authentication and authorization

### Database Architecture

**Primary Database**: MySQL on host `10.0.0.160:3306`, database `vocab`
- Configuration managed in `config.py` (VocabularyConfig class)
- High-performance connection pooling via `custom_database_manager.py`
- Optimized for 22,094 vocabulary words with 240M+ pairwise comparisons

**Key Tables**:
- `word_phonetics` - Phonetic transcriptions (IPA, ARPAbet, syllables, stress patterns)
- `pronunciation_similarity` - Pairwise similarity scores with composite indexing
- User management tables created via `setup_user_tables.py`

### Performance and Scaling

**CUDA Acceleration**: GPU processing provides 10-100x speedup for similarity calculations
- Requires CuPy with CUDA 11.x or 12.x support
- Automatic fallback to CPU when GPU unavailable
- Memory-efficient batching for large datasets

**Database Optimization**: 
- Connection pooling with 12 connections
- Batch insert operations (50,000+ records per batch)
- Composite indexes for fast quiz distractor lookup
- Performance monitoring via `mysql_performance_monitor.py`

### Data Processing Pipeline

**Phonetic Processing**:
1. CMU Pronouncing Dictionary (primary source)
2. Online dictionary APIs (fallback)
3. Rule-based generation (last resort)
4. Stress pattern analysis and syllable counting

**Similarity Calculation**:
1. Phonetic distance (Levenshtein on phonemes)
2. Stress pattern matching
3. Rhyme similarity scoring  
4. Syllable count comparison
5. Weighted combination into overall similarity

### Configuration Management

All system configuration centralized in `config.py`:
- Database connection parameters
- Processing batch sizes and thresholds
- CUDA settings and memory management
- File paths and logging configuration

Environment variable overrides supported via `VocabularyConfig.from_env()`.

### Quality Assurance

**Testing Framework**: pytest with coverage reporting
- Test files in `tests/` directory
- Focus on phonetic processor and validation modules
- Coverage reporting configured in `pyproject.toml`

**Code Standards**: Black formatting, isort imports, mypy typing, flake8 linting
- Line length: 88 characters
- Python 3.10+ target version
- Type hints encouraged but not strictly required

### Development Notes

**Package Management**: Uses `pyproject.toml` for modern Python packaging
- Optional CUDA dependencies: `cupy-cuda11x` or `cupy-cuda12x`  
- Development dependencies include testing and formatting tools
- Scripts defined for `pronunciation-similarity` and `cuda-pronunciation` commands

**Modular Design**: Core functionality separated into focused modules
- Pronunciation processing, similarity calculation, database management
- CLI interfaces, web applications, and utility scripts
- Clear separation between CPU and GPU code paths

**Error Handling**: Comprehensive error handling with graceful degradation
- CUDA availability detection with CPU fallback
- Database connection retry logic
- Detailed logging and user-friendly error messages