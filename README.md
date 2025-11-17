# 🎓 Vocabulary Learning Platform

<div align="center">

**A comprehensive vocabulary learning ecosystem with CUDA-accelerated pronunciation analysis, intelligent web applications, and autonomous content harvesting**

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![CUDA](https://img.shields.io/badge/CUDA-11.x%2F12.x-green.svg)](https://developer.nvidia.com/cuda-zone)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-teal.svg)](https://fastapi.tiangolo.com)
[![MySQL](https://img.shields.io/badge/MySQL-8.0+-orange.svg)](https://mysql.com)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

[🚀 Quick Start](#-quick-start) • [📚 Features](#-features) • [⚡ Performance](#-performance) • [🛠️ Installation](#️-installation) • [📖 Documentation](#-documentation)

</div>

---

## 🌟 Overview

This platform combines cutting-edge GPU acceleration with intelligent web applications to create a comprehensive vocabulary learning ecosystem. From CUDA-powered pronunciation similarity analysis to autonomous content harvesting, it provides everything needed for advanced vocabulary acquisition and research.

### 🎯 Core Capabilities

- **🌐 Full-Featured Web Application**: Modern FastAPI backend with user authentication, analytics, and adaptive quizzing
- **⚡ CUDA-Accelerated Engine**: GPU-powered pronunciation similarity calculations (10-100x speedup)
- **🤖 Autonomous Content Harvesting**: Intelligent vocabulary extraction from academic sources, RSS feeds, and repositories
- **📊 Advanced Analytics**: Comprehensive progress tracking with spaced repetition and learning science
- **🔧 Professional Admin Tools**: Complete definition editing system with bulk operations and filtering

---

## 🚀 Quick Start

### 🌐 Web Application (Recommended)

```bash
# Start the full-featured web application
python web_apps/vocabulary_web_app.py
```

Open **http://localhost:8001** in your browser and create an account to start learning!

### ⚡ CLI Tools (Advanced)

```bash
# Check system status and CUDA availability
python cuda_enhanced_cli.py --check-cuda

# Process vocabulary with phonetic analysis
python cuda_enhanced_cli.py --process-words --batch-size 1000

# Calculate pronunciation similarities (GPU accelerated)
python cuda_enhanced_cli.py --calculate-similarities --similarity-threshold 0.2
```

---

## 📚 Features

### 🌐 Interactive Web Application

- **🔐 User Authentication**: Secure registration/login with role-based access control
- **🎯 Adaptive Quiz System**: Multiple question types with intelligent difficulty adjustment
- **📈 Learning Analytics**: Personal progress tracking with visual insights and streaks
- **🔄 Spaced Repetition**: Science-based review scheduling for optimal retention
- **🔍 Advanced Search & Browse**: Explore 22,000+ words with filtering and pagination
- **📊 Visualization Studio**: Interactive rarity histograms, domain heatmaps, and semantic neighborhood graphs
- **👥 User Management**: Complete admin dashboard with user statistics and controls
- **✏️ Definition Editor**: Professional admin tools for managing vocabulary database

### ⚡ CUDA-Accelerated Core Engine

- **🚀 GPU Acceleration**: 10-100x speedup for pronunciation similarity calculations
- **🔊 Multi-Source Phonetics**: CMU Dictionary, online APIs, and fallback generation
- **📊 Advanced Metrics**: Phonetic distance, stress patterns, rhyme similarity, syllable matching
- **🎲 Smart Quiz Generation**: Intelligent distractor selection with quality scoring
- **💾 Optimized Database**: Handles 240M+ pairwise comparisons efficiently
- **🎨 Rich CLI Interface**: Beautiful terminal output with progress tracking

### 🤖 Autonomous Content Harvesting

- **📡 Multi-Source Ingestion**: RSS feeds, arXiv papers, GitHub repositories
- **🧠 Intelligent Filtering**: NLP-based candidate term extraction and scoring
- **📊 Zipf Frequency Analysis**: Target rare/emerging vocabulary (configurable thresholds)
- **🕷️ Autonomous Spider**: Self-directed web crawling for vocabulary discovery
- **⏰ Scheduled Harvesting**: Automated daily/hourly content processing
- **🎯 Domain-Specific Sources**: AI/ML research focus with configurable feeds

### 📊 Advanced Analytics System

- **📈 Progress Tracking**: 5-level mastery system (Learning → Mastered)
- **🎯 Performance Insights**: Accuracy trends, difficulty analysis, learning streaks
- **🧠 Personalized Recommendations**: AI-powered next steps and review scheduling
- **📋 Detailed Reporting**: Comprehensive session history and word performance
- **🔍 Challenging Words Analysis**: Identify and focus on difficult vocabulary
- **⏰ Spaced Repetition Alerts**: Optimal review timing notifications

---

## ⚡ Performance

### 🔢 Benchmark Results

| Dataset Size | Word Pairs | CPU Time | GPU Time | Speedup | Throughput |
|-------------|------------|----------|----------|---------|------------|
| 1,000 words | 500K | 10s | 0.5s | **20x** | 1M pairs/sec |
| 5,000 words | 12.5M | 4.2 min | 12s | **21x** | 1M pairs/sec |
| 22,094 words | 240M | 1.3 hours | 4 min | **20x** | 1M pairs/sec |

### 🚀 Scalability Features

- **Memory-Efficient Batching**: Adaptive sizing based on GPU memory
- **Vectorized Operations**: Parallel phoneme comparisons
- **Triangular Processing**: Avoid duplicate calculations
- **Threshold Filtering**: GPU-side filtering before CPU transfer
- **Connection Pooling**: High-performance database operations

---

## 🛠️ Installation

### 📋 Prerequisites

- **Python 3.10+**
- **CUDA 11.x or 12.x** (for GPU acceleration)
- **MySQL Database** (configured and accessible)
- **Node.js** (optional, for advanced search tools)

### 🔧 Installation Steps

```bash
# Clone the repository
git clone https://github.com/yourusername/vocabulary.git
cd vocabulary

# Install with CUDA 12.x support (recommended)
pip install -e .[cuda12]

# Alternative installations
pip install -e .[cuda11]  # CUDA 11.x
pip install -e .          # CPU-only
pip install -e .[dev]     # Development tools

# Install advanced search tools
winget install sharkdp.fd
winget install BurntSushi.ripgrep.MSVC
npm install -g @ast-grep/cli
winget install jqlang.jq
```

### ✅ Verify Installation

```bash
# Check CUDA availability
python cuda_enhanced_cli.py --check-cuda

# Test database connection
python -c "from core.config import get_db_config; print('DB Config:', get_db_config())"

# Generate system status report
python cuda_enhanced_cli.py --status
```

---

## 📖 Documentation

- For contributor and agent workflows, review [AGENTS.md](AGENTS.md) alongside the instructions here.

### 🌐 Web Application Guide

#### 🎯 Quiz System
- **Question Types**: Multiple choice, true/false, matching questions
- **Difficulty Levels**: Easy, Medium, Hard, or Adaptive (personalized)
- **Domain Filtering**: Focus on specific subject areas
- **Configuration**: 5-50 questions, various quiz types and difficulties

#### 📊 Analytics Dashboard
- **Overview Stats**: Quiz sessions, accuracy, learning streaks
- **Word Mastery**: 5-level progress tracking with visual indicators
- **Performance Analysis**: Difficulty breakdown, challenging words identification
- **Spaced Repetition**: Science-based review scheduling

#### 🔍 Browse & Search
- **22,000+ Words**: Complete vocabulary database with definitions
- **Advanced Filtering**: Part of speech, domain, frequency ranges
- **Search Features**: Full-text search in terms and definitions
- **Alphabetical Navigation**: Quick letter-based browsing

#### 👨‍💼 Admin Features
- **User Management**: View user statistics and activity
- **Definition Editor**: Professional grid-style editing with bulk operations
- **System Monitoring**: Database stats and performance metrics
- **Role Management**: Admin/user role assignments

### 🔗 Definition Linking Maintenance
- **Purpose**: Inject cross-links into stored definitions whenever another known vocabulary term appears in the text.
- **Script**: `python scripts/update_definition_links.py` (add `--dry-run` to preview changes or `--limit 500` for spot checks).
- **Behavior**: Creates/updates the `definition_with_links` column on `vocab.defined`, stores HTML only when links are available, and caps each definition at 25 anchors by default.
- **Display**: The web app automatically prefers the new HTML column for detail pages and flashcard study views; templates fall back to the plain definition if no links were generated.

### ⚡ CLI Reference

#### 🔊 Phonetic Processing
```bash
# Process all vocabulary with phonetic transcriptions
python cuda_enhanced_cli.py --process-words --batch-size 1000

# Test specific word pronunciation
python cuda_enhanced_cli.py --test-word "serendipitous"

# Limit processing for testing
python cuda_enhanced_cli.py --process-words --limit-words 100
```

#### 📊 Similarity Calculations
```bash
# GPU-accelerated similarity calculations
python cuda_enhanced_cli.py --calculate-similarities --similarity-threshold 0.2

# Force CPU mode (fallback)
python cuda_enhanced_cli.py --calculate-similarities --force-cpu

# Adjust similarity thresholds
python cuda_enhanced_cli.py --calculate-similarities --similarity-threshold 0.1  # More results
python cuda_enhanced_cli.py --calculate-similarities --similarity-threshold 0.4  # Higher quality
```

#### 🎲 Quiz Generation
```bash
# Find pronunciation-based distractors
python cuda_enhanced_cli.py --find-distractors 12345 --num-distractors 4

# Semantic similarity distractors
python main_cli.py --find-semantic-distractors 12345
```

#### 🤖 Content Harvesting
```bash
# RSS feed ingestion
python main_cli.py --ingest-run rss --ingest-limit 200

# arXiv paper processing
python main_cli.py --ingest-run arxiv --ingest-limit 100

# GitHub repository analysis
python main_cli.py --ingest-run github --ingest-limit 50

# Autonomous spider crawling
python harvesters/autonomous_spider.py --max-urls 100 --duration 30 --candidates 200
```

### 🏗️ Architecture Overview

```
vocabulary/
├── 🌐 web_apps/
│   ├── vocabulary_web_app.py       # Main FastAPI application
│   ├── simple_vocab_app.py         # Lightweight version
│   ├── enhanced_quiz_system.py     # Advanced quiz features
│   └── quiz_system.py              # Core quiz functionality
├── 📐 templates/                   # Jinja2 HTML templates
│   ├── base.html                   # Navigation and layout
│   ├── quiz.html, quiz_session.html, quiz_results.html
│   ├── analytics.html, browse.html  # User interface
│   ├── admin_dashboard.html        # Admin overview
│   └── admin_definitions.html      # Definition editor
├── 🧠 core/                       # Core system components
│   ├── config.py                   # System configuration
│   ├── auth.py                     # Authentication system
│   └── comprehensive_definition_lookup.py  # Multi-source definitions
├── 🔊 pronunciation/               # Phonetic processing
│   └── pronunciation_generator.py  # IPA and ARPAbet generation
├── 📊 analysis/                    # Analytics and insights
│   ├── domain_classifier.py        # Subject domain classification
│   └── frequency_analysis_system.py # Statistical analysis
├── 🕷️ harvesters/                 # Content ingestion
│   ├── autonomous_spider.py        # Self-directed crawling
│   ├── url_harvester.py           # URL processing
│   ├── gutenberg_harvester.py     # Project Gutenberg
│   ├── respectful_scraper.py      # Ethical web scraping
│   └── universal_vocabulary_extractor.py  # NLP extraction
├── 🛠️ utils/                      # Utilities and helpers
│   └── circular_definition_detector.py  # Definition quality
└── ⚡ cuda_enhanced_cli.py         # Main CUDA-accelerated CLI
```

### 💾 Database Schema

#### 🔐 User Management Tables
- **users**: User accounts, authentication, roles
- **quiz_sessions**: Quiz session tracking and configuration
- **user_quiz_results**: Individual question responses and timing
- **user_word_mastery**: Spaced repetition and progress tracking

#### 🔊 CUDA Engine Tables
- **word_phonetics**: IPA, ARPAbet, syllables, stress patterns
- **pronunciation_similarity**: 240M+ pairwise similarity scores
- **defined**: Core vocabulary database (22,000+ words)

#### 🤖 Content Harvesting Tables
- **sources**: RSS feeds, repositories, API endpoints
- **documents**: Harvested content and metadata
- **candidate_terms**: Extracted vocabulary candidates
- **candidate_observations**: Frequency and context tracking
- **definition_candidates**: Multi-source definition aggregation

---

## 🔧 Advanced Configuration

### 🗄️ Database Configuration
```python
# core/config.py
DATABASE = {
    'host': '10.0.0.160',
    'port': 3306,
    'database': 'vocab',
    'user': 'brian',
    'password': 'your_password'
}
```

### 🌐 Environment Variables
```bash
# Database overrides
export DB_HOST=10.0.0.160
export DB_PORT=3306
export DB_NAME=vocab
export DB_USER=brian
export DB_PASSWORD=your_password

# Harvesting configuration
export RSS_FEEDS="https://feed1.com,https://feed2.com"
export ARXIV_CATEGORIES="cs.CL,cs.LG,cs.AI"
export GITHUB_REPOS="org/repo1,org/repo2"
export ZIPF_COMMON_THRESHOLD=3.0
```

### ⚡ Performance Tuning
```python
# High-Performance Inserter Settings
HP_INSERTER = {
    'pool_size': 12,
    'batch_size': 50000,
    'queue_size': 5000000,
    'timeout': 10.0
}

# CUDA Settings
CUDA_BATCH_SIZE = 5000
DEFAULT_SIMILARITY_THRESHOLD = 0.1
```

---

## 🧪 Testing & Quality Assurance

### 🔍 Code Quality Tools
```bash
# Run tests with coverage
pytest tests/ -v --cov=pronunciation --cov-report=term-missing

# Code formatting
black . --line-length 88
isort . --profile black

# Type checking
mypy . --ignore-missing-imports

# Linting
flake8 .
```

### 🌐 Web Application Testing
```bash
# Use Playwright for comprehensive web testing
# Tests authentication, quiz functionality, admin features
# Navigate to test endpoints and verify UI interactions
```

### 📊 Performance Testing
```bash
# Benchmark GPU vs CPU performance
python cuda_enhanced_cli.py --benchmark

# Monitor system performance
python cuda_enhanced_cli.py --status

# Database performance analysis
python mysql_performance_monitor.py
```

---

## 🚨 Troubleshooting

### 🔧 Common Issues & Solutions

#### CUDA Not Available
```bash
# Check CUDA installation
nvidia-smi
python -c "import cupy; print(cupy.cuda.is_available())"

# Install appropriate CuPy version
pip install cupy-cuda12x  # CUDA 12.x
pip install cupy-cuda11x  # CUDA 11.x
```

#### Database Connection Issues
```bash
# Test database connectivity
python -c "from core.config import get_db_config; print(get_db_config())"

# Verify MySQL service
mysql -h 10.0.0.160 -u brian -p vocab
```

#### Memory Issues
```bash
# Reduce batch size for limited memory
python cuda_enhanced_cli.py --process-words --batch-size 500

# Force CPU mode
python cuda_enhanced_cli.py --calculate-similarities --force-cpu
```

#### Web Application Issues
```bash
# Check if port is already in use
netstat -an | findstr :8001

# Kill existing process
taskkill /F /IM python.exe

# Restart with proper configuration
python web_apps/vocabulary_web_app.py
```

---

## 🤝 Contributing

### 🛠️ Development Setup
```bash
# Install development dependencies
pip install -e .[dev]

# Install pre-commit hooks
pre-commit install

# Install advanced search tools
winget install sharkdp.fd BurntSushi.ripgrep.MSVC jqlang.jq
npm install -g @ast-grep/cli fzf yq
```

### 📋 Code Standards
- **Black**: Code formatting (line length: 88)
- **isort**: Import organization
- **flake8**: Linting and style checking
- **mypy**: Type checking (encouraged)
- **pytest**: Testing framework with coverage

### 🔍 Advanced Search & Analysis
- **ast-grep**: Semantic code structure searches
- **ripgrep (rg)**: Ultra-fast text search
- **fd**: Advanced file discovery
- **jq**: JSON processing and analysis
- **yq**: YAML/XML processing

---

## 📄 License

MIT License - see [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- **[CMU Pronouncing Dictionary](http://www.speech.cs.cmu.edu/cgi-bin/cmudict)**: Primary phonetic data source
- **[CuPy](https://cupy.dev/)**: CUDA acceleration library
- **[FastAPI](https://fastapi.tiangolo.com/)**: Modern web framework
- **[Rich](https://rich.readthedocs.io/)**: Beautiful CLI formatting
- **[spaCy](https://spacy.io/)**: Advanced NLP for content harvesting

---

<div align="center">

**🚀 A complete vocabulary learning platform with 22,000+ words, powered by CUDA-accelerated analysis and intelligent harvesting**

[⭐ Star this project](https://github.com/yourusername/vocabulary) • [🐛 Report Issues](https://github.com/yourusername/vocabulary/issues) • [💡 Suggest Features](https://github.com/yourusername/vocabulary/discussions)

</div>
