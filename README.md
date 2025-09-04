# Vocabulary Learning Platform

A comprehensive vocabulary learning platform combining CUDA-accelerated pronunciation similarity analysis with an interactive web application for vocabulary acquisition, quizzing, and progress tracking.

## 🚀 Features

### 🌐 Interactive Web Application
- **Modern FastAPI Backend**: High-performance web server with real-time quiz generation
- **Responsive Bootstrap UI**: Mobile-friendly interface with intuitive navigation  
- **User Authentication**: Secure login/registration with session management
- **Comprehensive Analytics**: Personal progress tracking with learning insights
- **Adaptive Quiz System**: Multiple question types with smart difficulty adjustment
- **Spaced Repetition**: Intelligent review scheduling based on performance
- **Database Integration**: 22,000+ vocabulary words with definitions and frequency rankings

### ⚡ CUDA-Accelerated Core Engine  
- **GPU Acceleration**: 10-100x speedup for pronunciation similarity calculations
- **Multiple Phonetic Sources**: CMU Dictionary, online APIs, and fallback rules
- **Advanced Similarity Metrics**: Phonetic distance, stress patterns, rhyme similarity, syllable matching
- **Professional Database Schema**: Optimized for 240M+ pairwise comparisons
- **Intelligent Quiz Generation**: Advanced distractor selection with quality scoring
- **Rich CLI Interface**: Beautiful output with progress tracking
- **Robust Error Handling**: Graceful fallbacks and detailed logging

### 📚 Vocabulary Learning System
- **Smart Quiz Generation**: Multiple choice, true/false, and matching questions
- **Progress Tracking**: Word mastery levels from Learning to Mastered (5 levels)
- **Learning Analytics**: Performance insights, learning streaks, and recommendations
- **Personalized Experience**: Challenging words identification and review suggestions
- **Browse & Search**: Explore 22,000+ words with filtering and pagination

## 📊 Performance

| Dataset Size | Pairs | CPU Time | GPU Time | Speedup |
|-------------|-------|----------|----------|---------|
| 1,000 words | 500K | 10s | 0.5s | 20x |
| 5,000 words | 12.5M | 4.2 min | 12s | 21x |
| 22,094 words | 240M | 1.3 hours | 4 min | 20x |

## 🛠️ Installation

### Prerequisites

1. **Python 3.10+**
2. **CUDA 11.x or 12.x** (for GPU acceleration)
3. **MySQL Database** with vocabulary data

### Install Dependencies

```bash
# Clone and navigate to directory
cd vocabulary

# Install with CUDA 12.x support (recommended)
pip install -e .[cuda12]

# Or install with CUDA 11.x support
pip install -e .[cuda11]

# Or CPU-only installation
pip install -e .

# Development installation
pip install -e .[dev]
```

### Verify Installation

```bash
python main_cli.py --check-cuda
```

## 🚀 Quick Start

### 🌐 Web Application (Recommended)

#### 1. Start the Web Server
```bash
python working_vocab_app.py
# or
uvicorn working_vocab_app:app --reload
```

#### 2. Open Your Browser  
Navigate to `http://localhost:8000`

#### 3. Create an Account
- Register a new user account
- Start taking quizzes immediately  
- Track your progress in real-time

#### 4. Explore Features
- **Browse**: Explore 22,000+ vocabulary words
- **Quiz**: Take adaptive quizzes with multiple question types
- **Analytics**: View detailed progress tracking and learning insights
- **Random Word**: Discover new vocabulary

### ⚡ CLI Tools (Advanced Users)

#### 1. Initialize System
```bash
python main_cli.py --initialize
```

#### 2. Process Words for Phonetics
```bash
python main_cli.py --process-words
```

#### 3. Calculate Similarities (GPU Accelerated)
```bash
python main_cli.py --calculate-similarities
```

#### 4. Generate Report
```bash
python main_cli.py --generate-report
```

#### 5. Find Quiz Distractors
```bash
python main_cli.py --find-distractors 12345 --num-distractors 4
```

## 📖 Web Application Guide

### 🎯 Quiz System

#### Taking Quizzes
- **Question Types**: Multiple choice, true/false, matching questions
- **Difficulty Levels**: Easy (common words), Medium (mixed), Hard (rare words), Adaptive (personalized)
- **Domain Filtering**: Focus on specific word categories  
- **Spaced Repetition**: Words you struggle with appear more frequently

#### Quiz Configuration
```
- Quiz Types: Mixed, Multiple Choice Only, True/False Only, Matching Only
- Question Count: 5, 10, 20, or 50 questions
- Difficulty: Easy, Medium, Hard, or Adaptive based on your performance
- Topic Focus: Filter by domain or part of speech
```

### 📊 Analytics Dashboard

#### Overview Statistics
- **Total Quiz Sessions**: Number of quizzes completed
- **Correct Answers**: Total correct responses across all quizzes
- **Average Accuracy**: Overall performance percentage
- **Learning Streak**: Consecutive days of vocabulary practice

#### Word Mastery Tracking
- **5-Level Mastery System**: Learning → Beginner → Intermediate → Advanced → Mastered
- **Visual Progress Bars**: See your progress across mastery levels
- **Spaced Repetition Alerts**: Words ready for review based on learning science

#### Personalized Insights  
- **Challenging Words**: Words with lowest accuracy - focus areas for improvement
- **Strongest Words**: Words you've mastered with high accuracy and streaks
- **Recent Performance**: Table of your last 10 quiz sessions with detailed stats
- **Difficulty Analysis**: Performance breakdown across Easy/Medium/Hard levels

#### Learning Recommendations
- **Smart Insights**: Personalized feedback based on your performance data
- **Next Steps**: Actionable recommendations for continued learning
- **Review Reminders**: Spaced repetition notifications for optimal retention

### 🔍 Browse & Search

#### Word Exploration
- **22,000+ Words**: Complete vocabulary database with definitions
- **Advanced Filtering**: Filter by part of speech, domain, frequency
- **Pagination**: Browse efficiently with configurable page sizes (25/50/100)
- **Alphabetical Navigation**: Jump to specific letter combinations

#### Search Features  
- **Full-Text Search**: Search in word terms and definitions
- **Smart Results**: Results ordered by frequency and relevance
- **Quick Access**: Direct links to word detail pages

### 👤 User System

#### Authentication
- **Secure Registration**: Email-based account creation
- **Session Management**: Persistent login with secure cookies
- **Password Security**: Bcrypt hashing for password protection

#### Progress Persistence
- **Database Storage**: All quiz results and progress saved automatically
- **Cross-Session Continuity**: Continue learning across browser sessions
- **Performance History**: Complete record of your vocabulary journey

## 📖 CLI Usage (Advanced)

### Processing Words

Process all 22,094 words with phonetic transcription:

```bash
# Standard processing
python main_cli.py --process-words --batch-size 1000

# Test with limited words
python main_cli.py --process-words --limit-words 100

# With progress monitoring
python main_cli.py --process-words --verbose
```

### Similarity Calculations

Calculate 240M pairwise similarities:

```bash
# GPU accelerated (recommended)
python main_cli.py --calculate-similarities --similarity-threshold 0.2

# CPU fallback
python main_cli.py --calculate-similarities --force-cpu

# Different thresholds
python main_cli.py --calculate-similarities --similarity-threshold 0.1  # More results
python main_cli.py --calculate-similarities --similarity-threshold 0.4  # Fewer, higher quality
```

### Quiz Generation

Generate quiz distractors for vocabulary tests:

```bash
# Find distractors for word ID 12345
python main_cli.py --find-distractors 12345

# More distractors
python main_cli.py --find-distractors 12345 --num-distractors 8

# Test specific word transcription
python main_cli.py --test-word \"serendipitous\"
```

### Analysis and Reporting

```bash
# Comprehensive system report
python main_cli.py --generate-report

# System status
python main_cli.py --status

# Performance benchmark
python main_cli.py --benchmark
```

## 🏗️ Architecture

### Core Components

```
vocabulary/
├── working_vocab_app.py     # Main FastAPI web application
├── templates/               # Jinja2 HTML templates
│   ├── base.html                # Base template with navigation
│   ├── analytics.html           # Analytics dashboard
│   ├── browse.html              # Word browsing interface
│   ├── quiz.html                # Quiz setup page
│   ├── quiz_session.html        # Active quiz interface
│   └── quiz_results.html        # Quiz results and feedback
├── pronunciation_similarity/# CUDA-accelerated core engine
│   ├── core/                    # Core processing logic
│   │   ├── phonetic_processor.py   # Phonetic transcription
│   │   ├── similarity_calculator.py# Similarity algorithms  
│   │   └── database_manager.py     # Database operations
│   ├── cuda/                    # GPU acceleration
│   │   └── cuda_calculator.py      # CUDA similarity engine
│   ├── analysis/                # Analytics and reporting
│   │   └── similarity_analyzer.py  # Analysis tools
│   ├── cli/                     # Command-line interface
│   │   └── main_cli.py             # Rich CLI implementation
│   └── utils/                   # Utilities
│       ├── error_handling.py       # Error management
│       ├── validation.py           # Input validation
│       └── performance_monitor.py  # Performance tracking
├── config.py                # Database and app configuration
└── ingestion/              # Content ingestion system
    ├── rss_ingestion.py        # RSS feed processing
    ├── arxiv_ingestion.py      # arXiv paper processing
    └── github_ingestion.py     # GitHub repository analysis
```

### Database Schema

#### Web Application Tables

**users**
- `id` (PRIMARY KEY): Unique user identifier
- `username`: Unique username for login
- `email`: User email address
- `password_hash`: Bcrypt hashed password
- `created_at`: Account creation timestamp
- `role`: User role (user/admin)

**quiz_sessions**  
- `id` (PRIMARY KEY): Unique session identifier
- `user_id` (FOREIGN KEY): Links to users table
- `started_at`: Quiz start timestamp
- `completed_at`: Quiz completion timestamp (NULL if incomplete)
- `quiz_type`: Type of quiz (mixed, multiple_choice, etc.)
- `difficulty`: Difficulty level (easy, medium, hard, adaptive)
- `total_questions`: Number of questions in quiz
- `correct_answers`: Number of correct responses
- `session_config`: JSON configuration data

**user_quiz_results**
- `id` (PRIMARY KEY): Unique result identifier  
- `user_id` (FOREIGN KEY): Links to users table
- `word_id` (FOREIGN KEY): Links to defined table
- `question_type`: Type of question (multiple_choice, true_false)
- `is_correct`: Boolean indicating if answer was correct
- `response_time_ms`: Time taken to answer in milliseconds
- `answered_at`: Timestamp of response
- `difficulty_level`: Difficulty level of the question

**user_word_mastery**
- `id` (PRIMARY KEY): Unique mastery record identifier
- `user_id` (FOREIGN KEY): Links to users table  
- `word_id` (FOREIGN KEY): Links to defined table
- `mastery_level`: Current mastery level (learning, reviewing, mastered)
- `total_attempts`: Total number of times word was tested
- `correct_attempts`: Number of correct responses
- `last_seen`: Timestamp of last encounter
- `next_review`: Scheduled review time for spaced repetition
- `streak`: Current streak of consecutive correct answers
- `ease_factor`: Spaced repetition ease factor (1.3-2.5)

#### CUDA Engine Tables

**word_phonetics**
- `word_id` (PRIMARY KEY): Links to vocabulary database
- `ipa_transcription`: International Phonetic Alphabet
- `arpabet_transcription`: ARPAbet phonemes
- `syllable_count`: Number of syllables
- `stress_pattern`: Stress pattern (0=unstressed, 1=primary, 2=secondary)
- `phonemes_json`: Individual phonemes as JSON array
- `transcription_source`: Source of transcription (CMU/API/Fallback)

**pronunciation_similarity**  
- `word1_id`, `word2_id` (COMPOSITE PRIMARY KEY): Word pair IDs
- `overall_similarity`: Weighted combination of all metrics (0-1)
- `phonetic_distance`: Levenshtein distance on phonemes (0-1)
- `stress_similarity`: Stress pattern matching (0-1)
- `rhyme_score`: Ending sound similarity (0-1)
- `syllable_similarity`: Syllable count similarity (0-1)

#### Core Vocabulary Table

**defined** (22,000+ words)
- `id` (PRIMARY KEY): Unique word identifier
- `term`: The vocabulary word
- `definition`: Word definition
- `part_of_speech`: Grammatical category (noun, verb, etc.)
- `frequency`: Frequency score for commonality ranking
- `domain`: Subject domain (academic, scientific, etc.)

All tables optimized with indexes for fast quiz generation and analytics queries.

## 🎯 Quiz Generation Algorithm

### Distractor Selection Process

1. **Similarity Filtering**: Find words within optimal similarity range (0.2-0.7)
2. **Quality Scoring**: Balance similarity with phonetic confusability
3. **Diversity Enforcement**: Ensure varied similarity ranges
4. **Lexical Filtering**: Remove words too lexically similar to target

### Quality Metrics

- **Ideal Similarity**: Target 0.4 similarity (confusing but not obvious)
- **Rhyme Bonus**: Reward strong ending sound matches
- **Stress Bonus**: Reward similar stress patterns
- **Diversity Penalty**: Prevent clustering in similarity ranges

## 🔬 Phonetic Processing

### Data Sources (Priority Order)

1. **CMU Pronouncing Dictionary** (Primary): 134K+ entries, highly accurate
2. **Online Dictionary APIs** (Fallback): Real-time lookup for missing words
3. **Rule-Based Generation** (Last Resort): Basic English pronunciation rules

### Phonetic Features

- **IPA Transcription**: International standard phonetic notation
- **ARPAbet**: Computer-readable phoneme representation
- **Stress Patterns**: Primary (1), Secondary (2), Unstressed (0)
- **Syllable Segmentation**: Automatic syllable counting
- **Phoneme Vectorization**: For efficient GPU processing

## ⚡ CUDA Acceleration

### GPU Optimization Features

- **Memory-Efficient Batching**: Adaptive batch sizes based on GPU memory
- **Vectorized Operations**: Parallel phoneme comparisons
- **Position Weighting**: Earlier phonemes weighted more heavily
- **Triangular Processing**: Avoid duplicate pair calculations
- **Threshold Filtering**: GPU-side filtering before CPU transfer

### Memory Management

- **Automatic Memory Cleanup**: Aggressive GPU memory recycling
- **Batch Size Adaptation**: Dynamic sizing based on available memory
- **Progress Monitoring**: Real-time memory usage tracking

## 📊 Performance Monitoring

### Built-in Profiling

```python
from pronunciation_similarity.utils.performance_monitor import monitor_performance

with monitor_performance(\"similarity_calculation\", items_to_process=240_000_000):
    # Your code here
    pass
```

### Metrics Tracked

- **Processing Time**: Wall clock and CPU time
- **Memory Usage**: System and GPU memory consumption
- **Throughput**: Items processed per second
- **Error Rates**: Success/failure statistics

## 🧪 Testing and Validation

### Input Validation

- **Database Configuration**: Host, port, credentials validation
- **Word Input**: Format, length, character validation
- **Parameter Ranges**: Threshold, batch size limits
- **GPU Memory**: Available memory checking

### Error Handling

- **Graceful Degradation**: CPU fallback when GPU unavailable
- **Detailed Logging**: Comprehensive error tracking
- **User-Friendly Messages**: Clear error explanations
- **Recovery Mechanisms**: Automatic retry and cleanup

## 🎛️ Configuration

### Database Configuration

```python
DB_CONFIG = {
    'host': '10.0.0.196',
    'port': 3306,
    'database': 'Vocab',
    'user': 'brian',
    'password': 'your_password'
}
```

### Command Line Options

```bash
# Database options
--db-host 10.0.0.196 --db-port 3306 --db-name Vocab --db-user brian

# Processing options
--batch-size 1000 --similarity-threshold 0.2 --force-cpu

# Output options
--verbose --quiet
```

## 🚨 Troubleshooting

### Common Issues

**CUDA Not Available**
```bash
# Check CUDA installation
nvidia-smi
python -c \"import cupy; print(cupy.cuda.is_available())\"

# Install CuPy
pip install cupy-cuda12x  # for CUDA 12.x
pip install cupy-cuda11x  # for CUDA 11.x
```

**Database Connection Issues**
```bash
# Test connection
python main_cli.py --initialize

# Check MySQL service
mysql -h 10.0.0.196 -u brian -p Vocab
```

**Memory Issues**
```bash
# Reduce batch size
python main_cli.py --process-words --batch-size 500

# Use CPU mode
python main_cli.py --calculate-similarities --force-cpu
```

**Performance Issues**
```bash
# Monitor performance
python main_cli.py --benchmark --verbose

# Check system resources
python main_cli.py --status
```

## 📈 Scalability

### Current Capacity
- **Words**: Tested up to 22,094 vocabulary words
- **Pairs**: Handles 240M+ similarity calculations
- **GPU Memory**: Optimized for 11GB GPUs
- **Processing Speed**: 1M+ similarity comparisons/second on GPU

### Scaling Options
- **Distributed Processing**: Multi-GPU support roadmap
- **Database Partitioning**: Horizontal scaling for larger vocabularies  
- **Cloud Deployment**: Docker containers and cloud GPU support

## 🤝 Contributing

### Development Setup

```bash
# Install development dependencies
pip install -e .[dev]

# Install pre-commit hooks
pre-commit install

# Run tests
pytest tests/ -v --cov=pronunciation_similarity

# Format code
black pronunciation_similarity/
isort pronunciation_similarity/
```

### Code Style
- **Black**: Code formatting
- **isort**: Import sorting  
- **flake8**: Linting
- **mypy**: Type checking

## 📄 License

MIT License - see LICENSE file for details.

## 🙏 Acknowledgments

- **CMU Pronouncing Dictionary**: Primary phonetic data source
- **CuPy**: CUDA acceleration library
- **Rich**: Beautiful CLI formatting
- **MySQL**: Robust database storage

## 🔗 Related Projects

- [CMU Pronouncing Dictionary](http://www.speech.cs.cmu.edu/cgi-bin/cmudict)
- [CuPy - NumPy-compatible array library for GPU](https://cupy.dev/)
- [Rich - Beautiful terminal formatting](https://rich.readthedocs.io/)

---

## 🎯 Getting Started

### For Vocabulary Learners
1. **Start the web app**: `python working_vocab_app.py`  
2. **Visit**: `http://localhost:8000`
3. **Register**: Create your account  
4. **Learn**: Take quizzes and track your progress!

### For Developers  
1. **Explore the codebase**: FastAPI backend with comprehensive analytics
2. **CUDA acceleration**: GPU-powered pronunciation similarity engine  
3. **Database integration**: MySQL with optimized schemas
4. **Spaced repetition**: Learning science-based review scheduling

---

**A complete vocabulary learning platform with 22,000+ words, powered by CUDA-accelerated pronunciation analysis** 🚀📚
**Ingestion Settings**
- **Requirement (spaCy model):** install `spacy` and `en_core_web_sm` for robust proper-noun/NER exclusion. Commands: `pip install spacy` then `python -m spacy download en_core_web_sm`.
- **Run (CLI):** `python main_cli.py --ingest-run rss --ingest-limit 200` (also `arxiv` or `github`). Phrases are disabled; only single-token rare terms are kept.
- **Run (Web):** start API `uvicorn vocabulary_web_app:app --reload`, open `/candidates`, choose a strategy, click “Run Ingestion”.
- **Config defaults:** managed in `config.py` under `VocabularyConfig.INGESTION` with helpers: `get_rss_feeds()`, `get_arxiv_categories()`, `get_github_repos()`, `get_zipf_threshold()`.
- **Env overrides:** set `RSS_FEEDS`, `ARXIV_CATEGORIES`, and `GITHUB_REPOS`. Example: `export RSS_FEEDS="https://feed1,https://feed2"`.
- **Rarity cutoff:** keeps only single-token candidates with Zipf < 3.0 (hard-coded) to target seriously rare/difficult/emerging words.
- **Strategies:** `rss` (research/AI-focused feeds), `arxiv` (AI/ML categories), `github` (ML/NLP repos). Sources can be tuned via config/env.
- **Storage:** new tables: `sources`, `documents`, `candidate_terms`, `candidate_observations`, `candidate_metrics`, `definition_candidates`, `promotions`, `rejections`, and final `terms`.
- **Cron examples:** see `CRON_JOBS.md` for scheduled runs (RSS every 6h, arXiv/GitHub daily).
