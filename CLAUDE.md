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

**Web Testing**: Use Playwright browser automation for all web functionality testing
- ALWAYS use Playwright tools (mcp__playwright__*) instead of curl for web testing
- Playwright provides actual browser experience with snapshots and interaction capabilities
- Better for testing UI, navigation, forms, and user workflows
- Use `mcp__playwright__browser_navigate`, `mcp__playwright__browser_click`, `mcp__playwright__browser_snapshot` etc.

## Advanced Search & Analysis Tools

### File Discovery
- **Finding FILES?** → Use `fd` instead of Glob for complex patterns and better performance
- **Examples**:
  ```bash
  fd -e py -e js --exclude __pycache__ --exclude node_modules
  fd "test_" --type f --extension py
  fd "config" --type f --max-depth 2
  ```

### Text & String Search  
- **Finding TEXT/strings?** → Use `rg` (ripgrep) for ultra-fast text search
- **Examples**:
  ```bash
  rg "def.*quiz" --type py --context 3
  rg "class.*App" --type py --line-number
  rg "TODO|FIXME|HACK" --type py --ignore-case
  ```

### Code Structure Analysis ⭐ GAME CHANGER
- **Finding CODE STRUCTURE?** → Use `ast-grep` for AST-based semantic searches
- **Examples**:
  ```bash
  # Find all function definitions
  ast-grep --pattern 'def $NAME($$$): $$$'
  
  # Find all FastAPI endpoints  
  ast-grep --pattern '@app.$METHOD($$$)'
  
  # Find all class methods
  ast-grep --pattern 'class $CLASS: $$$ def $METHOD(self, $$$): $$$'
  
  # Find all imports from specific modules
  ast-grep --pattern 'from $MODULE import $$$'
  
  # Find all database queries
  ast-grep --pattern 'cursor.execute($$$)'
  
  # Find all exception handling
  ast-grep --pattern 'try: $$$ except $EXCEPTION: $$$'
  ```

### Interactive Selection
- **Selecting from multiple results?** → Pipe to `fzf` for fuzzy selection
- **Examples**:
  ```bash
  fd -e py | fzf --preview 'head -20 {}'
  rg "def " --files-with-matches | fzf
  ```

### Data Processing  
- **Processing JSON?** → Use `jq` for precise JSON manipulation
- **Examples**:
  ```bash
  # Extract dependencies from package.json
  jq '.dependencies | keys[]' package.json
  
  # Get database config
  jq '.database.host' config.json
  
  # Filter quiz results
  jq '.quiz_sessions[] | select(.accuracy > 0.8)' results.json
  ```

- **Processing YAML/XML?** → Use `yq` for YAML/XML processing
- **Examples**:
  ```bash
  yq '.services.web.ports' docker-compose.yml
  yq '.database.host' config.yaml
  ```

### Search Priority & Usage Guidelines

1. **ast-grep** (HIGHEST PRIORITY) - Use for finding code patterns, functions, classes
   - Revolutionary improvement for code structure searches
   - Semantic understanding vs regex pattern matching
   - Perfect for refactoring analysis and code discovery

2. **rg** (ALREADY OPTIMIZED) - Continue using Grep tool for text searches
   - Already integrated and working excellently
   - Fastest text search available

3. **fd** (HIGH PRIORITY) - Use for file discovery
   - Significant speed improvement over traditional file searches  
   - Better pattern matching and filtering options

4. **jq** (HIGH PRIORITY) - Use for config and data analysis
   - Essential for JSON configuration files
   - Perfect for analyzing API responses and structured data

5. **fzf** (MEDIUM PRIORITY) - Use for interactive selections when applicable
   - Great for interactive file/result selection
   - Limited applicability in our current workflow

6. **yq** (LOW-MEDIUM PRIORITY) - Use for YAML/XML when needed
   - Useful for configuration files in YAML format
   - Less common in current Python-focused codebase

### Tool Installation Status
✅ All tools successfully installed via winget and npm:
- fd v10.3.0 (File finder)
- jq v1.8.1 (JSON processor)  
- fzf v0.65.1 (Fuzzy finder)
- ast-grep (AST pattern matching)
- yq v4.46.1 (YAML/XML processor)

**Note**: Tools require shell restart to be available in PATH. Test with: `fd --version`, `jq --version`, etc.

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
- Always use playwright mcp to test web UI and fomr interactions


# How to ensure Always Works™ implementation

Please ensure your implementation Always Works™ for: $ARGUMENTS.

Follow this systematic approach:

## Core Philosophy

- "Should work" ≠ "does work" - Pattern matching isn't enough
- I'm not paid to write code, I'm paid to solve problems
- Untested code is just a guess, not a solution

# The 30-Second Reality Check - Must answer YES to ALL:

- Did I run/build the code?
- Did I trigger the exact feature I changed?
- Did I see the expected result with my own observation (including GUI)?
- Did I check for error messages?
- Would I bet $100 this works?

# Phrases to Avoid:

- "This should work now"
- "I've fixed the issue" (especially 2nd+ time)
- "Try it now" (without trying it myself)
- "The logic is correct so..."

# Specific Test Requirements:

- UI Changes: Actually click the button/link/form
- API Changes: Make the actual API call
- Data Changes: Query the database
- Logic Changes: Run the specific scenario
- Config Changes: Restart and verify it loads

# The Embarrassment Test:

"If the user records trying this and it fails, will I feel embarrassed to see his face?"

# Time Reality:

- Time saved skipping tests: 30 seconds
- Time wasted when it doesn't work: 30 minutes
- User trust lost: Immeasurable

---