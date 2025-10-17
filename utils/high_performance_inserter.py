#!/usr/bin/env python3
"""
High-Performance Database Inserter for CUDA Similarity Results
Optimized for massive throughput with async operations and bulk inserts
"""

import mysql.connector
from mysql.connector import pooling
import threading
import queue
import time
import logging
from typing import List, Tuple
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
import numpy as np

logger = logging.getLogger(__name__)

@dataclass
class FastSimilarityScore:
    """Lightweight similarity score for high-speed inserts"""
    word1_id: int
    word2_id: int
    overall_similarity: float
    phonetic_distance: float = 0.0
    stress_similarity: float = 0.0
    rhyme_score: float = 0.0
    syllable_similarity: float = 0.0

class HighPerformanceInserter:
    """Ultra-fast database inserter with connection pooling and async operations"""
    
    def __init__(self, db_config, pool_size=12, batch_size=50000, queue_size=5000000):
        self.db_config = db_config
        self.pool_size = pool_size
        self.batch_size = batch_size
        self.queue_size = queue_size
        
        # Create connection pool
        self.connection_pool = pooling.MySQLConnectionPool(
            pool_name="similarity_pool",
            pool_size=pool_size,
            pool_reset_session=True,
            **db_config
        )
        
        # Threading components
        self.insert_queue = queue.Queue(maxsize=queue_size)
        self.shutdown_event = threading.Event()
        self.insert_threads = []
        self.stats_lock = threading.Lock()
        
        # Performance tracking
        self.total_inserted = 0
        self.start_time = time.time()
        self.last_report_time = time.time()
        self.last_report_count = 0
        
        # Start insert worker threads
        self._start_insert_workers()
        
        logger.info(f"HighPerformanceInserter initialized with {pool_size} workers, batch size {batch_size}")
    
    def _start_insert_workers(self):
        """Start background insert worker threads"""
        for i in range(self.pool_size):
            worker = threading.Thread(
                target=self._insert_worker,
                name=f"InsertWorker-{i}",
                daemon=True
            )
            worker.start()
            self.insert_threads.append(worker)
        
        logger.info(f"Started {len(self.insert_threads)} insert worker threads")
    
    def _insert_worker(self):
        """Background worker that processes insert batches"""
        batch = []
        
        while not self.shutdown_event.is_set():
            try:
                # Try to get items with timeout
                try:
                    item = self.insert_queue.get(timeout=1.0)
                    if item is None:  # Shutdown signal
                        break
                    batch.append(item)
                except queue.Empty:
                    # Timeout - process any accumulated batch
                    if batch:
                        self._bulk_insert_batch(batch)
                        batch = []
                    continue
                
                # If batch is full, insert it
                if len(batch) >= self.batch_size:
                    self._bulk_insert_batch(batch)
                    batch = []
                
            except Exception as e:
                logger.error(f"Insert worker error: {e}")
                # Don't let one error kill the worker
                continue
        
        # Process any remaining batch on shutdown
        if batch:
            self._bulk_insert_batch(batch)
    
    def _bulk_insert_batch(self, batch: List[FastSimilarityScore]):
        """Perform optimized bulk insert of a batch"""
        if not batch:
            return
        
        start_time = time.time()
        
        try:
            # Get connection from pool
            conn = self.connection_pool.get_connection()
            cursor = conn.cursor()
            
            # Disable autocommit and optimize settings for bulk insert
            conn.autocommit = False
            cursor.execute("SET SESSION sql_log_bin=0")  # Disable binary logging
            cursor.execute("SET SESSION unique_checks=0")  # Disable unique checks
            cursor.execute("SET SESSION foreign_key_checks=0")  # Disable FK checks
            
            # Use optimized INSERT IGNORE (faster than ON DUPLICATE KEY UPDATE)
            insert_query = """
                INSERT IGNORE INTO vocab.pronunciation_similarity
                (word1_id, word2_id, overall_similarity, phonetic_distance,
                 stress_similarity, rhyme_score, syllable_similarity)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            
            # Prepare data as tuples (fastest format) with proper ordering constraint
            data_tuples = []
            for score in batch:
                word1_id = min(score.word1_id, score.word2_id)
                word2_id = max(score.word1_id, score.word2_id)
                
                # Skip self-comparisons
                if word1_id == word2_id:
                    continue
                    
                data_tuples.append((
                    word1_id,
                    word2_id,
                    score.overall_similarity,
                    score.phonetic_distance,
                    score.stress_similarity,
                    score.rhyme_score,
                    score.syllable_similarity
                ))
            
            # Skip empty batches
            if not data_tuples:
                cursor.close()
                conn.close()
                return
            
            # Bulk insert
            cursor.executemany(insert_query, data_tuples)
            
            # Commit and restore settings
            conn.commit()
            cursor.execute("SET SESSION unique_checks=1")
            cursor.execute("SET SESSION foreign_key_checks=1")
            cursor.execute("SET SESSION sql_log_bin=1")
            conn.autocommit = True
            
            cursor.close()
            conn.close()
            
            # Update statistics
            with self.stats_lock:
                self.total_inserted += len(batch)
                
                # Report progress every 10 seconds
                current_time = time.time()
                if current_time - self.last_report_time > 10.0:
                    elapsed = current_time - self.start_time
                    rate = self.total_inserted / elapsed if elapsed > 0 else 0
                    recent_rate = (self.total_inserted - self.last_report_count) / (current_time - self.last_report_time)
                    
                    logger.info(f"[BULK INSERT] {self.total_inserted:,} total | "
                              f"Rate: {rate:.0f}/sec avg, {recent_rate:.0f}/sec recent | "
                              f"Queue: {self.insert_queue.qsize()}")
                    
                    self.last_report_time = current_time
                    self.last_report_count = self.total_inserted
            
            insert_time = time.time() - start_time
            logger.debug(f"Bulk inserted {len(batch)} records in {insert_time:.3f}s")
            
        except Exception as e:
            logger.error(f"Bulk insert failed for batch of {len(batch)}: {e}")
            # Put items back in queue for retry (optional)
            # for item in batch:
            #     self.insert_queue.put(item)
    
    def queue_similarity_batch(self, similarities: List[Tuple[int, int, float]]):
        """Queue a batch of similarities for async insertion"""
        for word1_id, word2_id, similarity in similarities:
            score = FastSimilarityScore(
                word1_id=word1_id,
                word2_id=word2_id,
                overall_similarity=similarity
            )
            
            try:
                self.insert_queue.put(score, timeout=10.0)
            except queue.Full:
                logger.warning("Insert queue full, dropping similarity record")
                # Could implement backpressure here
    
    def queue_similarity_scores(self, scores: List):
        """Queue similarity score objects for async insertion"""
        for score in scores:
            fast_score = FastSimilarityScore(
                word1_id=score.word1_id,
                word2_id=score.word2_id,
                overall_similarity=score.overall_similarity,
                phonetic_distance=getattr(score, 'phonetic_distance', 0.0),
                stress_similarity=getattr(score, 'stress_similarity', 0.0),
                rhyme_score=getattr(score, 'rhyme_score', 0.0),
                syllable_similarity=getattr(score, 'syllable_similarity', 0.0)
            )
            
            try:
                self.insert_queue.put(fast_score, timeout=10.0)
            except queue.Full:
                logger.warning("Insert queue full, dropping similarity record")
    
    def get_queue_size(self):
        """Get current queue size"""
        return self.insert_queue.qsize()
    
    def get_stats(self):
        """Get performance statistics"""
        with self.stats_lock:
            elapsed = time.time() - self.start_time
            rate = self.total_inserted / elapsed if elapsed > 0 else 0
            
            return {
                'total_inserted': self.total_inserted,
                'elapsed_time': elapsed,
                'insertion_rate': rate,
                'queue_size': self.insert_queue.qsize(),
                'active_workers': len(self.insert_threads)
            }
    
    def flush_and_wait(self, timeout=300):
        """Wait for all queued inserts to complete"""
        logger.info(f"Flushing {self.insert_queue.qsize()} remaining inserts...")
        
        start_wait = time.time()
        while self.insert_queue.qsize() > 0 and time.time() - start_wait < timeout:
            time.sleep(1.0)
            if time.time() - start_wait > 30:
                logger.info(f"Still flushing... {self.insert_queue.qsize()} remaining")
        
        if self.insert_queue.qsize() > 0:
            logger.warning(f"Timeout waiting for flush. {self.insert_queue.qsize()} items remain")
        else:
            logger.info("All inserts completed")
    
    def shutdown(self):
        """Gracefully shutdown the inserter"""
        logger.info("Shutting down HighPerformanceInserter...")
        
        # Signal shutdown
        self.shutdown_event.set()
        
        # Send shutdown signals to workers
        for _ in range(len(self.insert_threads)):
            self.insert_queue.put(None)
        
        # Wait for workers to finish
        for worker in self.insert_threads:
            worker.join(timeout=30)
        
        # Final stats
        stats = self.get_stats()
        logger.info(f"Shutdown complete. Total inserted: {stats['total_inserted']:,} "
                   f"at {stats['insertion_rate']:.0f}/sec average")


class StreamingCUDAInserter:
    """Streaming inserter that works with CUDA calculations"""
    
    def __init__(self, db_config, stream_batch_size=50000):
        self.hp_inserter = HighPerformanceInserter(db_config, batch_size=stream_batch_size)
        self.stream_buffer = []
        self.stream_batch_size = stream_batch_size
        
    def add_similarities(self, similarities: List[Tuple[int, int, float]]):
        """Add similarities to the streaming buffer"""
        self.stream_buffer.extend(similarities)
        
        # Flush buffer when it gets large enough
        if len(self.stream_buffer) >= self.stream_batch_size:
            self.flush_buffer()
    
    def flush_buffer(self):
        """Flush the current buffer to the high-performance inserter"""
        if self.stream_buffer:
            self.hp_inserter.queue_similarity_batch(self.stream_buffer)
            self.stream_buffer = []
    
    def get_stats(self):
        """Get insertion statistics"""
        stats = self.hp_inserter.get_stats()
        stats['buffer_size'] = len(self.stream_buffer)
        return stats
    
    def shutdown(self):
        """Shutdown the streaming inserter"""
        self.flush_buffer()  # Flush remaining buffer
        self.hp_inserter.flush_and_wait()
        self.hp_inserter.shutdown()


if __name__ == "__main__":
    # Test the high-performance inserter
    DB_CONFIG = {
        'host': '10.0.0.160',
        'port': 3306,
        'database': 'vocab',
        'user': 'brian',
        'password': 'Fl1p5ma5h!'
    }
    
    logging.basicConfig(level=logging.INFO)
    
    # Create test data
    test_similarities = []
    for i in range(100000):
        test_similarities.append((i, i+1, 0.5 + i*0.0001))
    
    print(f"Testing with {len(test_similarities)} similarity records...")
    
    inserter = HighPerformanceInserter(DB_CONFIG)
    
    start_time = time.time()
    inserter.queue_similarity_batch(test_similarities)
    inserter.flush_and_wait()
    end_time = time.time()
    
    stats = inserter.get_stats()
    print(f"Insert test completed in {end_time - start_time:.2f} seconds")
    print(f"Rate: {stats['insertion_rate']:.0f} records/second")
    
    inserter.shutdown()