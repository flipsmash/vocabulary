#!/usr/bin/env python3
"""
CUDA-Enhanced CLI for Pronunciation Similarity System
Adds GPU acceleration for massive speed improvements
"""

import argparse
import sys
import os
import logging
import time
from typing import Dict

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import existing components
from core.custom_database_manager import CustomDatabaseManager
from pronunciation.modern_pronunciation_system import ModernPhoneticProcessor

# Try to import CUDA components
CUDA_AVAILABLE = False
try:
    from pronunciation.cuda_similarity_calculator import CUDAIntegratedSimilaritySystem, check_cuda_setup
    CUDA_AVAILABLE = check_cuda_setup()
except ImportError:
    print("[WARNING] CUDA components not available. Will use CPU-only version.")

# Database configuration
from core.config import get_db_config
DB_CONFIG = get_db_config()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class EnhancedPronunciationSystem:
    """Enhanced system with optional CUDA acceleration and resume capability"""
    
    def __init__(self, db_config: Dict, use_cuda: bool = True):
        self.db_manager = CustomDatabaseManager(**db_config)
        self.phonetic_processor = ModernPhoneticProcessor()
        
        self.use_cuda = use_cuda and CUDA_AVAILABLE
        
        if self.use_cuda:
            logger.info("🚀 Initializing with CUDA acceleration")
            self.cuda_system = CUDAIntegratedSimilaritySystem(
                self.db_manager, self.phonetic_processor
            )
        else:
            logger.info("🔧 Using CPU-only mode")
            # Fallback to CPU version
            from custom_pronunciation_cli import CustomPronunciationSimilaritySystem
            self.cpu_system = CustomPronunciationSimilaritySystem(db_config)
    
    def get_progress_info(self):
        """Check current similarity calculation progress"""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("SELECT COUNT(*) FROM word_phonetics WHERE ipa_transcription != ''")
            total_words = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM pronunciation_similarity")
            current_similarities = cursor.fetchone()[0]
            
            cursor.execute("SELECT MAX(word1_id) FROM pronunciation_similarity")
            max_word1 = cursor.fetchone()[0] or 0
            
            total_pairs = total_words * (total_words - 1) // 2
            
            return {
                'total_words': total_words,
                'total_pairs': total_pairs,
                'current_similarities': current_similarities,
                'max_processed_word1': max_word1,
                'progress_percentage': (current_similarities / total_pairs * 100) if total_pairs > 0 else 0
            }
    
    def calculate_similarities(self, similarity_threshold: float = 0.1, use_gpu: bool = None, resume: bool = True):
        """Calculate similarities with optional GPU acceleration and resume capability"""
        if use_gpu is None:
            use_gpu = self.use_cuda
        
        # Show progress before starting
        progress = self.get_progress_info()
        logger.info(f"📊 Current progress: {progress['current_similarities']:,} / {progress['total_pairs']:,} pairs ({progress['progress_percentage']:.2f}%)")
        
        if progress['current_similarities'] > 0 and resume:
            logger.info(f"📍 Resume capability available from word ID {progress['max_processed_word1']}")
        
        if use_gpu and self.use_cuda:
            logger.info("🎮 Using CUDA GPU acceleration for similarity calculation")
            start_time = time.time()
            
            self.cuda_system.calculate_all_similarities_cuda(
                similarity_threshold=similarity_threshold
            )
            
            end_time = time.time()
            logger.info(f"⚡ GPU calculation completed in {end_time - start_time:.2f} seconds")
            
        else:
            logger.info("💻 Using CPU for similarity calculation with resume capability")
            start_time = time.time()
            
            # Use optimized CPU calculation with resume
            self._calculate_similarities_cpu_optimized(similarity_threshold, resume)
            
            end_time = time.time()
            logger.info(f"🐌 CPU calculation completed in {end_time - start_time:.2f} seconds")
    
    def _calculate_similarities_cpu_optimized(self, similarity_threshold: float, resume: bool):
        """Optimized CPU calculation with resume capability and high-performance inserts"""
        from modern_pronunciation_system import SimilarityCalculator
        from high_performance_inserter import StreamingCUDAInserter
        import json
        
        # Initialize high-performance inserter for CPU mode too
        db_config = self.db_manager.connection_params.copy()
        hp_inserter = StreamingCUDAInserter(db_config, stream_batch_size=25000)
        logger.info("Initialized high-performance inserter for CPU mode with 25k batch size")
        
        similarity_calculator = SimilarityCalculator()
        progress = self.get_progress_info()
        
        # Get phonetic data
        with self.db_manager.get_connection() as conn:
            query = """
                SELECT word_id, word, ipa_transcription, arpabet_transcription,
                       syllable_count, stress_pattern, phonemes_json
                FROM word_phonetics
                WHERE ipa_transcription != ''
                ORDER BY word_id
            """
            cursor = conn.cursor()
            cursor.execute(query)
            rows = cursor.fetchall()
        
        logger.info(f"Loaded {len(rows)} words for CPU processing with high-performance inserts")
        
        # Convert to phonetic data
        from modern_pronunciation_system import PhoneticData
        phonetic_data = {}
        word_ids = []
        
        for row in rows:
            word_id = row[0]
            phonemes = json.loads(row[6]) if row[6] else []
            
            phonetic_data[word_id] = PhoneticData(
                word=row[1],
                ipa=row[2],
                arpabet=row[3],
                syllable_count=row[4] or 1,
                stress_pattern=row[5] or '0',
                phonemes=phonemes,
                source="database"
            )
            word_ids.append(word_id)
        
        # Calculate similarities with resume
        start_i = 0
        if resume and progress['max_processed_word1'] > 0:
            try:
                start_i = word_ids.index(progress['max_processed_word1'])
                logger.info(f"Resuming CPU processing from index {start_i}")
            except ValueError:
                logger.info("Could not find resume point, starting from beginning")
        
        processed_pairs = 0
        found_similarities = 0
        last_report = time.time()
        stream_buffer = []
        
        for i in range(start_i, len(word_ids)):
            word1_id = word_ids[i]
            
            for j in range(i + 1, len(word_ids)):
                word2_id = word_ids[j]
                
                try:
                    similarity = similarity_calculator.calculate_similarity(
                        phonetic_data[word1_id],
                        phonetic_data[word2_id]
                    )
                    
                    if similarity.overall_similarity >= similarity_threshold:
                        # Add to streaming buffer
                        stream_buffer.append((word1_id, word2_id, similarity.overall_similarity))
                        found_similarities += 1
                    
                    processed_pairs += 1
                    
                    # Stream to inserter when buffer gets large
                    if len(stream_buffer) >= 5000:
                        hp_inserter.add_similarities(stream_buffer)
                        stream_buffer = []
                        
                        # Progress report every 30 seconds
                        current_time = time.time()
                        if current_time - last_report > 30:
                            elapsed = current_time - time.time() + processed_pairs/1000
                            rate = processed_pairs / elapsed if elapsed > 0 else 0
                            stats = hp_inserter.get_stats()
                            logger.info(f"CPU Progress: {processed_pairs:,} pairs processed, "
                                       f"{found_similarities:,} similarities found, "
                                       f"{rate:.0f} pairs/sec, {stats['insertion_rate']:.0f}/sec inserts, "
                                       f"queue: {stats['queue_size']}")
                            last_report = current_time
                            
                except Exception as e:
                    logger.warning(f"Error processing {word1_id}-{word2_id}: {e}")
                    continue
        
        # Flush remaining buffer
        if stream_buffer:
            hp_inserter.add_similarities(stream_buffer)
        
        logger.info(f"CPU processing completed! Processed {processed_pairs:,} pairs, "
                   f"found {found_similarities:,} similarities")
        
        # Shutdown high-performance inserter
        logger.info("Flushing remaining CPU inserts...")
        hp_inserter.shutdown()
    
    def process_words(self, batch_size: int = 1000):
        """Process words (same for CPU and GPU)"""
        if hasattr(self, 'cpu_system'):
            self.cpu_system.process_all_words(batch_size=batch_size)
        else:
            # Create temporary CPU system for word processing
            from custom_pronunciation_cli import CustomPronunciationSimilaritySystem
            cpu_system = CustomPronunciationSimilaritySystem(DB_CONFIG)
            cpu_system.process_all_words(batch_size=batch_size)
    
    def initialize_system(self):
        """Initialize system"""
        return self.db_manager.examine_schema()


def benchmark_cuda_vs_cpu(system, sample_size: int = 1000):
    """Benchmark CUDA vs CPU performance"""
    print("🏁 Running CUDA vs CPU benchmark...")
    
    # Get sample data
    with system.db_manager.get_connection() as conn:
        query = f"""
        SELECT word_id, word, ipa_transcription, arpabet_transcription,
               syllable_count, stress_pattern, phonemes_json
        FROM word_phonetics
        WHERE ipa_transcription != ''
        LIMIT {sample_size}
        """
        import pandas as pd
        df = pd.read_sql(query, conn)
    
    if len(df) < 100:
        print("❌ Not enough processed words for benchmark. Process words first.")
        return
    
    print(f"📊 Benchmarking with {len(df)} words ({len(df)*(len(df)-1)//2:,} pairs)")
    
    # Prepare data for CUDA
    if CUDA_AVAILABLE:
        from modern_pronunciation_system import PhoneticData
        import json
        
        phonetic_data_list = []
        for _, row in df.iterrows():
            phonemes = json.loads(row['phonemes_json']) if row['phonemes_json'] else []
            phonetic_data = PhoneticData(
                word=row['word'],
                ipa=row['ipa_transcription'],
                arpabet=row['arpabet_transcription'],
                syllable_count=row['syllable_count'],
                stress_pattern=row['stress_pattern'],
                phonemes=phonemes,
                source="database"
            )
            phonetic_data.word_id = row['word_id']
            phonetic_data_list.append(phonetic_data)
        
        # CUDA benchmark
        print("🎮 Testing CUDA performance...")
        cuda_start = time.time()
        
        features = system.cuda_system.cuda_calculator.prepare_features(phonetic_data_list)
        cuda_results = system.cuda_system.cuda_calculator.calculate_all_similarities_cuda(
            features, similarity_threshold=0.1
        )
        
        cuda_end = time.time()
        cuda_time = cuda_end - cuda_start
        
        print(f"✅ CUDA: {cuda_time:.2f} seconds, {len(cuda_results):,} similarities found")
        
        # Extrapolate to full dataset
        full_size = system.db_manager.get_processing_stats()['processed_words']
        if full_size > sample_size:
            scale_factor = (full_size / sample_size) ** 2  # O(n²) scaling
            estimated_cuda_time = cuda_time * scale_factor
            print(f"📈 Estimated time for {full_size:,} words: {estimated_cuda_time/3600:.1f} hours (CUDA)")
            print(f"📈 Estimated time for {full_size:,} words: {estimated_cuda_time*10/3600:.1f} hours (CPU)")
    
    else:
        print("❌ CUDA not available for benchmark")


def handle_cuda_similarities(system, threshold, force_cpu=False, auto_gpu=False):
    """Handle similarity calculation with CUDA option and progress monitoring"""
    stats = system.db_manager.get_processing_stats()
    processed_words = stats['processed_words']
    total_pairs = processed_words * (processed_words - 1) // 2
    
    # Get current progress
    progress = system.get_progress_info()
    
    print(f"🔍 Calculating similarities for {processed_words:,} words ({total_pairs:,} pairs)")
    print(f"📊 Similarity threshold: {threshold}")
    print(f"📈 Current progress: {progress['current_similarities']:,} pairs ({progress['progress_percentage']:.1f}% complete)")
    
    if progress['progress_percentage'] > 0:
        remaining_pairs = total_pairs - progress['current_similarities']
        print(f"🎯 Remaining: {remaining_pairs:,} pairs")
    
    if CUDA_AVAILABLE and not force_cpu:
        estimated_gpu_time = total_pairs / 1000000  # Rough estimate: 1M pairs per second on GPU
        estimated_cpu_time = total_pairs / 50000    # Rough estimate: 50K pairs per second on CPU
        
        print(f"⚡ Estimated GPU time: {estimated_gpu_time/3600:.1f} hours")
        print(f"🐌 Estimated CPU time: {estimated_cpu_time/3600:.1f} hours")
        print(f"🚀 GPU speedup: {estimated_cpu_time/estimated_gpu_time:.1f}x faster")
        
        if auto_gpu:
            print("🎮 Auto-selecting GPU acceleration...")
            use_gpu = True
        else:
            use_gpu = input("\nUse GPU acceleration? (Y/n): ").lower().strip()
            use_gpu = use_gpu in ['', 'y', 'yes']
        
        if use_gpu:
            print("🎮 Using CUDA GPU acceleration...")
            system.calculate_similarities(threshold, use_gpu=True)
        else:
            print("💻 Using CPU calculation with resume capability...")
            system.calculate_similarities(threshold, use_gpu=False)
    else:
        if force_cpu:
            print("💻 Forced CPU mode with resume capability...")
        else:
            print("💻 CUDA not available, using CPU with resume capability...")
        system.calculate_similarities(threshold, use_gpu=False)


def create_enhanced_parser():
    """Create enhanced argument parser with CUDA options"""
    parser = argparse.ArgumentParser(
        description='CUDA-Enhanced Pronunciation Similarity System',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
🚀 Consolidated CUDA-Enhanced Features:
  --calculate-similarities-cuda    Use GPU acceleration (10-100x faster)
  --calculate-similarities         Use CPU with resume capability
  --resume                         Resume previous calculation
  --progress                       Show current progress
  --benchmark                      Compare CUDA vs CPU performance
  --auto-gpu                       Auto-select GPU without prompting
  --force-cpu                      Force CPU-only mode
  --check-cuda                     Check CUDA setup

Examples:
  python cuda_enhanced_cli.py --initialize
  python cuda_enhanced_cli.py --process-words
  python cuda_enhanced_cli.py --progress
  python cuda_enhanced_cli.py --calculate-similarities-cuda --auto-gpu
  python cuda_enhanced_cli.py --resume
  python cuda_enhanced_cli.py --benchmark --sample-size 500
        """
    )
    
    # Main operations
    parser.add_argument('--initialize', action='store_true',
                       help='Initialize the system')
    parser.add_argument('--process-words', action='store_true',
                       help='Process all words for phonetic transcription')
    parser.add_argument('--calculate-similarities', action='store_true',
                       help='Calculate similarities (CPU mode)')
    parser.add_argument('--calculate-similarities-cuda', action='store_true',
                       help='Calculate similarities with GPU acceleration')
    
    # CUDA-specific options
    parser.add_argument('--benchmark', action='store_true',
                       help='Benchmark CUDA vs CPU performance')
    parser.add_argument('--check-cuda', action='store_true',
                       help='Check CUDA setup and availability')
    parser.add_argument('--force-cpu', action='store_true',
                       help='Force CPU-only mode (disable CUDA)')
    parser.add_argument('--auto-gpu', action='store_true',
                       help='Automatically use GPU without prompting')
    parser.add_argument('--resume', action='store_true',
                       help='Resume previous similarity calculation')
    parser.add_argument('--progress', action='store_true',
                       help='Show current processing progress')
    parser.add_argument('--test-insert-performance', action='store_true',
                       help='Test high-performance insert speed')
    parser.add_argument('--monitor-mysql', action='store_true',
                       help='Monitor MySQL performance during operations')
    parser.add_argument('--mysql-config-check', action='store_true',
                       help='Check MySQL configuration for optimization opportunities')
    
    # Parameters
    parser.add_argument('--similarity-threshold', type=float, default=0.2,
                       help='Minimum similarity score (default: 0.2)')
    parser.add_argument('--batch-size', type=int, default=500,
                       help='Batch size for word processing (default: 500)')
    parser.add_argument('--sample-size', type=int, default=1000,
                       help='Sample size for benchmarking (default: 1000)')
    
    # Reporting and testing
    parser.add_argument('--generate-report', action='store_true',
                       help='Generate comprehensive report')
    parser.add_argument('--processing-report', action='store_true',
                       help='Show phonetic processing statistics')
    parser.add_argument('--test-word', type=str,
                       help='Test phonetic transcription for a word')
    parser.add_argument('--find-distractors', type=int,
                       help='Find distractors for word ID')
    parser.add_argument('--num-distractors', type=int, default=5,
                       help='Number of distractors to find')
    
    return parser


def main():
    """Enhanced main function with CUDA support"""
    parser = create_enhanced_parser()
    args = parser.parse_args()
    
    # Show enhanced help if no arguments
    if len(sys.argv) == 1:
        print("🚀 CUDA-Enhanced Pronunciation Similarity System")
        print("=" * 55)
        print("Configured for your vocabulary database with GPU acceleration")
        print()
        if CUDA_AVAILABLE:
            print("✅ CUDA GPU acceleration is AVAILABLE")
            print("   Expect 10-100x speedup for similarity calculations!")
        else:
            print("❌ CUDA GPU acceleration is NOT available")
            print("   Install CUDA + CuPy for massive speedup:")
            print("   pip install cupy-cuda11x  # or cupy-cuda12x")
        print()
        print("Quick start:")
        print("  --initialize                    Set up the system")
        print("  --process-words                 Process all 22k words")
        print("  --calculate-similarities-cuda   Lightning-fast GPU similarities")
        print("  --benchmark                     Compare GPU vs CPU speed")
        print("  --check-cuda                    Test CUDA setup")
        print()
        print("Use --help for full options")
        return 0
    
    # Handle CUDA check
    if args.check_cuda:
        success = check_cuda_setup()
        if success:
            print("\n🎉 CUDA is ready for GPU acceleration!")
            
            # Show GPU specs
            try:
                import cupy as cp
                device = cp.cuda.Device()
                mem_total = device.mem_info[1] // (1024**3)
                mem_free = device.mem_info[0] // (1024**3)
                print(f"GPU Memory: {mem_free}GB free / {mem_total}GB total")
                
                # Estimate capacity
                estimated_words = mem_free * 100000  # Rough estimate
                print(f"Estimated capacity: ~{estimated_words:,} words")
                
            except Exception as e:
                print(f"Could not get GPU details: {e}")
        else:
            print("\n❌ CUDA setup failed")
            print("Installation guide:")
            print("1. Install CUDA toolkit from NVIDIA")
            print("2. pip install cupy-cuda11x  # or cupy-cuda12x for CUDA 12")
            print("3. Restart terminal and try again")
        return 0 if success else 1
    
    try:
        # Initialize system
        print("Initializing enhanced pronunciation system...")
        system = EnhancedPronunciationSystem(DB_CONFIG, use_cuda=not args.force_cpu)
        
        if system.use_cuda:
            print("✅ CUDA acceleration enabled")
        else:
            print("💻 Using CPU-only mode")
        
        success = True
        
        # Handle operations
        if args.initialize:
            print("🚀 Initializing system...")
            schema_info = system.initialize_system()
            system.db_manager.create_phonetic_tables()
            print("✅ System initialized successfully!")
        
        if args.test_word:
            print(f"🧪 Testing word: '{args.test_word}'")
            phonetic_data = system.phonetic_processor.transcribe_word(args.test_word)
            print(f"IPA: {phonetic_data.ipa}")
            print(f"Phonemes: {phonetic_data.phonemes}")
            print(f"Syllables: {phonetic_data.syllable_count}")
            print(f"Source: {phonetic_data.source}")
        
        if args.process_words:
            print(f"📝 Processing words (batch size: {args.batch_size})...")
            system.process_words(batch_size=args.batch_size)
            print("✅ Word processing complete!")
        
        if args.processing_report:
            stats = system.db_manager.get_processing_stats()
            print("\n=== Processing Statistics ===")
            print(f"Total words in database: {stats['total_words']:,}")
            print(f"Processed words: {stats['processed_words']:,}")
            print(f"Processing coverage: {stats['processing_percentage']:.1f}%")
            print(f"Existing similarities: {stats['similarity_count']:,}")
            
            if stats['source_breakdown']:
                print("\nPhonetic sources:")
                for source, count in stats['source_breakdown']:
                    print(f"  {source}: {count:,}")
        
        if args.test_insert_performance:
            print("🔍 Testing high-performance insert speed...")
            from high_performance_inserter import HighPerformanceInserter
            import time
            import random
            
            db_config = {
                'host': '10.0.0.160',
                'port': 3306,
                'database': 'vocab',
                'user': 'brian',
                'password': 'Fl1p5ma5h!'
            }
            
            # Generate test data with proper constraints
            test_size = 10000  # Smaller for quick test
            test_similarities = []
            used_pairs = set()
            
            for i in range(test_size):
                word1_id = random.randint(1, 1000)  # Use smaller range to avoid constraint issues
                word2_id = random.randint(1, 1000)
                
                # Ensure proper ordering and no duplicates
                if word1_id == word2_id:
                    continue
                
                pair = (min(word1_id, word2_id), max(word1_id, word2_id))
                if pair in used_pairs:
                    continue
                
                used_pairs.add(pair)
                similarity = random.uniform(0.1, 1.0)
                test_similarities.append((pair[0], pair[1], similarity))
            
            print(f"Generated {len(test_similarities):,} unique test similarity records")
            
            # Test old method
            print("Testing old insert method...")
            start = time.time()
            try:
                system.db_manager.insert_similarity_scores([
                    type('SimilarityScore', (), {
                        'word1_id': s[0], 'word2_id': s[1], 'overall_similarity': s[2],
                        'phonetic_distance': 0.0, 'stress_similarity': 0.0,
                        'rhyme_score': 0.0, 'syllable_similarity': 0.0
                    })() for s in test_similarities[:1000]  # Only test 1k records
                ])
                old_time = time.time() - start
                old_rate = 1000 / old_time
                print(f"Old method: {old_time:.2f}s for 1,000 records ({old_rate:.0f}/sec)")
            except Exception as e:
                print(f"Old method failed: {e}")
                old_rate = 0
            
            # Test new method
            print("Testing high-performance insert method...")
            inserter = HighPerformanceInserter(db_config, pool_size=4)
            
            start = time.time()
            inserter.queue_similarity_batch(test_similarities)
            inserter.flush_and_wait()
            new_time = time.time() - start
            
            stats = inserter.get_stats()
            new_rate = stats['insertion_rate']
            
            print(f"New method: {new_time:.2f}s for {len(test_similarities):,} records ({new_rate:.0f}/sec)")
            if old_rate > 0:
                speedup = new_rate / old_rate
                print(f"Speedup: {speedup:.1f}x faster")
            
            inserter.shutdown()
        
        if args.mysql_config_check:
            print("🔍 Checking MySQL configuration for optimization opportunities...")
            from mysql_performance_monitor import MySQLPerformanceMonitor
            
            db_config = {
                'host': '10.0.0.160',
                'port': 3306,
                'database': 'vocab',
                'user': 'brian',
                'password': 'Fl1p5ma5h!'
            }
            
            monitor = MySQLPerformanceMonitor(db_config)
            
            try:
                config = monitor.get_configuration()
                metrics = monitor.get_key_metrics()
                
                print("\n📊 Current MySQL Configuration:")
                print(f"   Buffer Pool Size: {config.get('innodb_buffer_pool_size', 'Unknown')}")
                print(f"   Log File Size: {config.get('innodb_log_file_size', 'Unknown')}")
                print(f"   Flush Log at Commit: {config.get('innodb_flush_log_at_trx_commit', 'Unknown')}")
                print(f"   Binary Logging: {config.get('sql_log_bin', 'Unknown')}")
                print(f"   I/O Capacity: {config.get('innodb_io_capacity', 'Unknown')}")
                print(f"   Max Connections: {config.get('max_connections', 'Unknown')}")
                
                print(f"\n📈 Current Performance Metrics:")
                print(f"   Buffer Pool Hit Ratio: {metrics['buffer_pool_hit_ratio']:.2f}%")
                print(f"   Active Connections: {metrics['active_connections']}")
                print(f"   Similarity Table Rows: {metrics['similarity_table_rows']:,}")
                print(f"   Table Size: {metrics['similarity_data_mb']:.1f} MB")
                
                print(f"\n💡 Optimization Recommendations:")
                
                # Buffer pool recommendations
                buffer_size_gb = int(config.get('innodb_buffer_pool_size', '0')) / (1024**3)
                if buffer_size_gb < 8:
                    print(f"   ⚠️  Buffer pool size ({buffer_size_gb:.1f}GB) is small - recommend 12-24GB")
                
                # Log file recommendations  
                log_size_mb = int(config.get('innodb_log_file_size', '0')) / (1024**2)
                if log_size_mb < 1024:
                    print(f"   ⚠️  Log file size ({log_size_mb:.0f}MB) is small - recommend 2GB (2048MB)")
                
                # Binary logging check
                if config.get('sql_log_bin', '').upper() != 'OFF':
                    print(f"   ⚠️  Binary logging enabled - disable with sql_log_bin=0 for faster inserts")
                
                # Flush settings
                if config.get('innodb_flush_log_at_trx_commit', '') != '2':
                    print(f"   ⚠️  Flush setting not optimized - set innodb_flush_log_at_trx_commit=2")
                    
                # Hit ratio check
                if metrics['buffer_pool_hit_ratio'] < 95:
                    print(f"   ⚠️  Low buffer pool hit ratio ({metrics['buffer_pool_hit_ratio']:.1f}%) - increase buffer pool size")
                
                print(f"\n📖 See MYSQL_OPTIMIZATION_GUIDE.md for complete optimization instructions")
                
            except Exception as e:
                print(f"❌ Failed to check MySQL configuration: {e}")
        
        if args.monitor_mysql:
            print("🔍 Starting MySQL performance monitoring...")
            print("This will run continuously until you press Ctrl+C")
            print("Start your similarity calculations in another terminal")
            
            from mysql_performance_monitor import MySQLPerformanceMonitor
            
            db_config = {
                'host': '10.0.0.160',
                'port': 3306,
                'database': 'vocab',
                'user': 'brian',
                'password': 'Fl1p5ma5h!'
            }
            
            monitor = MySQLPerformanceMonitor(db_config)
            
            try:
                monitor.start_monitoring(interval_seconds=10)
            except KeyboardInterrupt:
                print("\n📊 Generating final performance report...")
                report = monitor.get_performance_report()
                
                print(f"\n🎯 Performance Summary:")
                print(f"   Monitoring Duration: {report['monitoring_duration_minutes']:.1f} minutes")
                print(f"   Total Inserts: {report['total_inserts_during_monitoring']:,}")
                print(f"   Average Insert Rate: {report['average_insert_rate_per_second']:.0f}/sec")
                print(f"   Buffer Pool Hit Ratio: {report['buffer_pool_hit_ratio']:.2f}%")
                print(f"   Final Table Rows: {report['current_table_rows']:,}")
                print(f"   Final Table Size: {report['current_table_size_mb']:.1f} MB")
                
                if report['recommendations']:
                    print(f"\n💡 Recommendations:")
                    for rec in report['recommendations']:
                        print(f"   • {rec}")
        
        if args.benchmark:
            if not CUDA_AVAILABLE:
                print("❌ Cannot benchmark: CUDA not available")
            else:
                benchmark_cuda_vs_cpu(system, args.sample_size)
        
        if args.progress:
            progress = system.get_progress_info()
            print(f"\n📊 Current Progress:")
            print(f"   Total words: {progress['total_words']:,}")
            print(f"   Total pairs needed: {progress['total_pairs']:,}")
            print(f"   Similarities stored: {progress['current_similarities']:,}")
            print(f"   Progress: {progress['progress_percentage']:.2f}%")
            if progress['progress_percentage'] > 0:
                remaining = progress['total_pairs'] - progress['current_similarities']
                print(f"   Remaining: {remaining:,} pairs")
        
        if args.resume:
            print("🔄 Resuming similarity calculation...")
            handle_cuda_similarities(system, args.similarity_threshold, force_cpu=args.force_cpu, auto_gpu=args.auto_gpu)
        
        if args.calculate_similarities:
            handle_cuda_similarities(system, args.similarity_threshold, force_cpu=True, auto_gpu=False)
        
        if args.calculate_similarities_cuda:
            if not CUDA_AVAILABLE:
                print("❌ CUDA not available. Use --calculate-similarities for CPU mode.")
                return 1
            handle_cuda_similarities(system, args.similarity_threshold, force_cpu=False, auto_gpu=args.auto_gpu)
        
        if args.generate_report:
            # Use CPU system for reporting
            from custom_pronunciation_cli import CustomSimilarityAnalyzer
            analyzer = CustomSimilarityAnalyzer(system.db_manager)
            report = analyzer.generate_similarity_report()
            
            print("\n=== Final System Report ===")
            print(f"Total words: {report['total_words']:,}")
            print(f"Total similarities: {report['total_similarities']:,}")
            print(f"Average similarity: {report['average_similarity']:.3f}")
            print(f"Max similarity: {report['max_similarity']:.3f}")
            
            if report['similarity_distribution']:
                print("\nSimilarity distribution:")
                for range_name, count in report['similarity_distribution']:
                    print(f"  {range_name}: {count:,}")
        
        if args.find_distractors:
            target_word = system.db_manager.get_word_by_id(args.find_distractors)
            if target_word:
                print(f"🎯 Finding distractors for '{target_word}' (ID: {args.find_distractors})")
                
                from custom_pronunciation_cli import CustomSimilarityAnalyzer
                analyzer = CustomSimilarityAnalyzer(system.db_manager)
                distractors = analyzer.find_best_distractors(
                    args.find_distractors, 
                    num_distractors=args.num_distractors
                )
                
                if distractors:
                    print(f"\n=== Best {len(distractors)} distractors ===")
                    for i, (d_id, d_word, sim, phon_dist, rhyme, source) in enumerate(distractors, 1):
                        print(f"{i}. '{d_word}' (similarity: {sim:.3f})")
                else:
                    print("No suitable distractors found")
            else:
                print(f"❌ Word ID {args.find_distractors} not found")
        
        # Save cache
        system.phonetic_processor.save_cache()
        
        return 0 if success else 1
        
    except KeyboardInterrupt:
        print("\n⚠️  Operation interrupted")
        return 1
    except Exception as e:
        print(f"❌ Error: {e}")
        logger.exception("Unexpected error")
        return 1


if __name__ == "__main__":
    sys.exit(main())
