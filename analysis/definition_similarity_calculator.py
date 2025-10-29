#!/usr/bin/env python3
"""
Definition Similarity Calculator using Sentence Transformers
Similar architecture to pronunciation similarity but for semantic meaning
"""

import numpy as np
import json
import logging
from typing import List, Tuple, Optional
from dataclasses import dataclass
from tqdm import tqdm
import time

from core.database_manager import db_manager

try:
    from psycopg.rows import execute_batch
    EXECUTE_BATCH_AVAILABLE = True
except ImportError:
    EXECUTE_BATCH_AVAILABLE = False

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    logger.warning("sentence-transformers not available. Install with: pip install sentence-transformers")

try:
    import torch
    TORCH_AVAILABLE = True
    TORCH_CUDA_AVAILABLE = torch.cuda.is_available()
except ImportError:
    TORCH_AVAILABLE = False
    TORCH_CUDA_AVAILABLE = False

try:
    import cupy as cp
    # Test if CuPy can actually perform GPU operations
    try:
        _ = cp.array([1.0])  # Simple GPU allocation test
        CUPY_AVAILABLE = True
    except Exception as e:
        logger.warning(f"CuPy installed but GPU operations failed: {e}")
        CUPY_AVAILABLE = False
except ImportError:
    CUPY_AVAILABLE = False

@dataclass
class DefinitionData:
    """Definition data structure"""
    word_id: int
    word: str
    definition: str
    embedding: Optional[np.ndarray] = None

@dataclass
class DefinitionSimilarityScore:
    """Definition similarity score"""
    word1_id: int
    word2_id: int
    cosine_similarity: float
    model_name: str = "all-MiniLM-L6-v2"

class DefinitionSimilarityCalculator:
    """Calculate semantic similarity between word definitions"""

    def __init__(self, db_config=None, model_name="all-MiniLM-L6-v2"):
        # db_config kept for backward compatibility; connections now use shared pool
        self.model_name = model_name

        if not SENTENCE_TRANSFORMERS_AVAILABLE:
            raise ImportError("sentence-transformers required. Install with: pip install sentence-transformers")

        # Determine device for embedding model
        if TORCH_CUDA_AVAILABLE:
            device = 'cuda'
            logger.info("🚀 GPU detected - using CUDA for embedding generation")
        else:
            device = 'cpu'
            logger.info("Using CPU for embedding generation")

        logger.info(f"Loading SentenceTransformer model: {model_name}")
        self.model = SentenceTransformer(model_name, device=device)
        logger.info(f"Model loaded successfully on device: {device}")

        # GPU detection for similarity calculations
        if CUPY_AVAILABLE:
            logger.info("🚀 CuPy detected - using CUDA for similarity calculations")
            self.use_gpu_similarity = True
        else:
            logger.info("CuPy not available - using CPU for similarity calculations")
            self.use_gpu_similarity = False

    def _cursor(self, autocommit: bool = False):
        return db_manager.get_cursor(autocommit=autocommit)

    def create_definition_tables(self):
        """Create tables for definition embeddings and similarities"""
        
        create_embeddings_table = """
        CREATE TABLE IF NOT EXISTS definition_embeddings (
            word_id INTEGER PRIMARY KEY,
            word VARCHAR(255) NOT NULL,
            definition_text TEXT NOT NULL,
            embedding_json TEXT,
            embedding_model VARCHAR(100),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (word_id) REFERENCES defined(id) ON DELETE CASCADE
        )
        """

        create_similarity_table = """
        CREATE TABLE IF NOT EXISTS definition_similarity (
            word1_id INTEGER,
            word2_id INTEGER,
            cosine_similarity NUMERIC(6,5),
            embedding_model VARCHAR(100),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (word1_id, word2_id, embedding_model),
            CONSTRAINT chk_def_word_order CHECK (word1_id < word2_id),
            FOREIGN KEY (word1_id) REFERENCES defined(id) ON DELETE CASCADE,
            FOREIGN KEY (word2_id) REFERENCES defined(id) ON DELETE CASCADE
        )
        """

        with self._cursor(autocommit=True) as cursor:
            cursor.execute(create_embeddings_table)
            cursor.execute(create_similarity_table)
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_definition_embeddings_model "
                "ON definition_embeddings (embedding_model)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_definition_similarity_cosine "
                "ON definition_similarity (cosine_similarity DESC)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_definition_similarity_word1 "
                "ON definition_similarity (word1_id, cosine_similarity DESC)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_definition_similarity_word2 "
                "ON definition_similarity (word2_id, cosine_similarity DESC)"
            )
        logger.info("Created definition similarity tables")
    
    def get_definitions(self, limit: Optional[int] = None, load_embeddings: bool = True) -> List[DefinitionData]:
        """Get word definitions from database

        Args:
            limit: Optional limit on number of definitions to retrieve
            load_embeddings: If True, also load existing embeddings for this model

        Returns:
            List of DefinitionData objects with embeddings populated if they exist
        """
        query = (
            "SELECT id, term, definition "
            "FROM vocab.defined "
            "WHERE definition IS NOT NULL "
            "AND TRIM(definition) <> '' "
            "ORDER BY id "
        )
        params = []
        if limit:
            query += "LIMIT %s"
            params.append(limit)

        with self._cursor() as cursor:
            cursor.execute(query, params)
            results = cursor.fetchall()

            definitions = []
            for word_id, word, definition in results:
                # Clean up definition text
                clean_def = definition.strip()
                if clean_def:
                    definitions.append(DefinitionData(
                        word_id=word_id,
                        word=word.lower(),
                        definition=clean_def
                    ))

            logger.info(f"Retrieved {len(definitions)} definitions")

            # Load existing embeddings if requested
            if load_embeddings and definitions:
                embeddings_map = self._load_embeddings_map([d.word_id for d in definitions])
                for d in definitions:
                    if d.word_id in embeddings_map:
                        d.embedding = embeddings_map[d.word_id]

                num_with_embeddings = sum(1 for d in definitions if d.embedding is not None)
                logger.info(f"Loaded embeddings for {num_with_embeddings}/{len(definitions)} definitions")

            return definitions

    def _load_embeddings_map(self, word_ids: List[int]) -> dict:
        """Load embeddings for specific word IDs into a dict

        Args:
            word_ids: List of word IDs to load embeddings for

        Returns:
            Dict mapping word_id -> embedding array
        """
        if not word_ids:
            return {}

        query = """
            SELECT word_id, embedding_json
            FROM vocab.definition_embeddings
            WHERE embedding_model = %s AND word_id = ANY(%s)
        """

        with self._cursor() as cursor:
            cursor.execute(query, (self.model_name, word_ids))
            results = cursor.fetchall()

        embeddings_map = {}
        for word_id, embedding_json in results:
            if embedding_json:
                try:
                    embeddings_map[word_id] = np.array(json.loads(embedding_json))
                except (json.JSONDecodeError, ValueError) as e:
                    logger.warning(f"Failed to parse embedding for word_id {word_id}: {e}")

        return embeddings_map
    
    def generate_embeddings_batch(self, definitions: List[DefinitionData], batch_size: int = 32):
        """Generate embeddings for definitions in batches"""
        logger.info(f"Generating embeddings for {len(definitions)} definitions")
        
        for i in tqdm(range(0, len(definitions), batch_size), desc="Generating embeddings"):
            batch = definitions[i:i + batch_size]
            texts = [d.definition for d in batch]
            
            # Generate embeddings
            embeddings = self.model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
            
            # Store embeddings in definition objects
            for j, embedding in enumerate(embeddings):
                batch[j].embedding = embedding
        
        logger.info("Embedding generation complete")
    
    def store_embeddings(self, definitions: List[DefinitionData]):
        """Store embeddings in database"""
        logger.info(f"Storing {len(definitions)} embeddings in database")

        data = []
        for def_data in definitions:
            if def_data.embedding is not None:
                embedding_json = json.dumps(def_data.embedding.tolist())
                data.append((
                    def_data.word_id,
                    def_data.word,
                    def_data.definition,
                    embedding_json,
                    self.model_name,
                ))

        if not data:
            logger.info("No embeddings to store")
            return

        # PostgreSQL has a limit of 65535 parameters per query
        # With 5 parameters per row, we can insert up to 13,107 rows at once
        # Use a conservative batch size of 10,000 to stay well under the limit
        batch_size = 10000
        total_stored = 0

        for i in range(0, len(data), batch_size):
            batch = data[i:i + batch_size]

            # Build multi-row INSERT for this batch
            placeholders = ','.join(['(%s,%s,%s,%s,%s)'] * len(batch))
            insert_query = f"""
                INSERT INTO vocab.definition_embeddings
                (word_id, word, definition_text, embedding_json, embedding_model)
                VALUES {placeholders}
                ON CONFLICT (word_id)
                DO UPDATE SET
                    word = EXCLUDED.word,
                    definition_text = EXCLUDED.definition_text,
                    embedding_json = EXCLUDED.embedding_json,
                    embedding_model = EXCLUDED.embedding_model,
                    created_at = CURRENT_TIMESTAMP
            """

            # Flatten the batch data for the query
            flattened = [item for row in batch for item in row]

            with self._cursor(autocommit=True) as cursor:
                cursor.execute(insert_query, flattened)

            total_stored += len(batch)
            if len(data) > batch_size:
                logger.info(f"Stored {total_stored}/{len(data)} embeddings...")

        logger.info(f"Stored {total_stored} embeddings total")
    
    def load_embeddings(self) -> List[DefinitionData]:
        """Load embeddings from database"""
        query = (
            "SELECT word_id, word, definition_text, embedding_json "
            "FROM vocab.definition_embeddings "
            "WHERE embedding_model = %s "
            "ORDER BY word_id"
        )
        with self._cursor() as cursor:
            cursor.execute(query, (self.model_name,))
            results = cursor.fetchall()

        definitions: List[DefinitionData] = []
        for word_id, word, definition, embedding_json in results:
            embedding = np.array(json.loads(embedding_json))
            definitions.append(DefinitionData(
                word_id=word_id,
                word=word,
                definition=definition,
                embedding=embedding,
            ))

        logger.info(f"Loaded {len(definitions)} embeddings")
        return definitions

    def calculate_cosine_similarity_matrix(self, embeddings1: np.ndarray, embeddings2: np.ndarray) -> np.ndarray:
        """Calculate cosine similarity matrix between two sets of embeddings

        Automatically chooses CPU or GPU based on matrix size for optimal performance.
        GPU has significant overhead, only beneficial for larger matrices (>= 5000 items).
        """
        # GPU only beneficial for large matrices due to transfer overhead
        GPU_THRESHOLD = 5000
        matrix_size = min(embeddings1.shape[0], embeddings2.shape[0])

        if self.use_gpu_similarity and matrix_size >= GPU_THRESHOLD:
            # Only log GPU usage on first large batch (to avoid spam)
            if not hasattr(self, '_logged_gpu_usage'):
                logger.info(f"🚀 Using GPU for similarity calculations (batch size: {matrix_size} >= {GPU_THRESHOLD})")
                self._logged_gpu_usage = True
            return self._calculate_similarity_gpu(embeddings1, embeddings2)
        else:
            # Only log CPU usage once if we have GPU available
            if self.use_gpu_similarity and not hasattr(self, '_logged_cpu_usage'):
                logger.info(f"Using CPU for similarity calculations (batch size: {matrix_size} < {GPU_THRESHOLD} threshold)")
                self._logged_cpu_usage = True
            return self._calculate_similarity_cpu(embeddings1, embeddings2)
    
    def _calculate_similarity_gpu(self, embeddings1: np.ndarray, embeddings2: np.ndarray) -> np.ndarray:
        """GPU-accelerated cosine similarity calculation"""
        # Move to GPU
        gpu_emb1 = cp.asarray(embeddings1)
        gpu_emb2 = cp.asarray(embeddings2)
        
        # Normalize vectors
        norms1 = cp.linalg.norm(gpu_emb1, axis=1, keepdims=True)
        norms2 = cp.linalg.norm(gpu_emb2, axis=1, keepdims=True)
        
        normalized_emb1 = gpu_emb1 / norms1
        normalized_emb2 = gpu_emb2 / norms2
        
        # Calculate cosine similarity matrix
        similarities = normalized_emb1 @ normalized_emb2.T
        
        # Move back to CPU
        return cp.asnumpy(similarities)
    
    def _calculate_similarity_cpu(self, embeddings1: np.ndarray, embeddings2: np.ndarray) -> np.ndarray:
        """CPU cosine similarity calculation"""
        # Normalize vectors
        norms1 = np.linalg.norm(embeddings1, axis=1, keepdims=True)
        norms2 = np.linalg.norm(embeddings2, axis=1, keepdims=True)
        
        normalized_emb1 = embeddings1 / norms1
        normalized_emb2 = embeddings2 / norms2
        
        # Calculate cosine similarity matrix
        return normalized_emb1 @ normalized_emb2.T
    
    def calculate_all_similarities(self, similarity_threshold: float = 0.3, batch_size: int = 1000, store_batch_size: int = 10000):
        """Calculate similarities between all definition pairs with incremental storage"""
        logger.info(f"Calculating definition similarities with threshold {similarity_threshold}")

        # Load embeddings
        definitions = self.load_embeddings()
        if not definitions:
            logger.error("No embeddings found. Run generate_embeddings first.")
            return 0

        embeddings = np.array([d.embedding for d in definitions])
        word_ids = [d.word_id for d in definitions]

        logger.info(f"Processing {len(definitions)} definitions")
        logger.info(f"Will store to database every {store_batch_size:,} similar pairs found")

        similarity_scores = []
        processed_pairs = 0
        total_stored = 0

        # Process in batches to manage memory
        for i in tqdm(range(0, len(definitions), batch_size), desc="Calculating similarities"):
            batch_end = min(i + batch_size, len(definitions))
            batch_embeddings = embeddings[i:batch_end]

            # Calculate similarities between this batch and all subsequent definitions
            for j in range(i, len(definitions), batch_size):
                other_batch_end = min(j + batch_size, len(definitions))
                other_batch_embeddings = embeddings[j:other_batch_end]

                # Calculate similarity matrix
                similarities = self.calculate_cosine_similarity_matrix(
                    batch_embeddings, other_batch_embeddings
                )

                # Extract pairs above threshold
                for bi, batch_idx in enumerate(range(i, batch_end)):
                    for oj, other_idx in enumerate(range(j, other_batch_end)):
                        if batch_idx >= other_idx:  # Only process upper triangle
                            continue

                        similarity = similarities[bi, oj]
                        if similarity >= similarity_threshold:
                            similarity_scores.append(DefinitionSimilarityScore(
                                word1_id=word_ids[batch_idx],
                                word2_id=word_ids[other_idx],
                                cosine_similarity=float(similarity),
                                model_name=self.model_name
                            ))

                processed_pairs += batch_embeddings.shape[0] * other_batch_embeddings.shape[0]

                # Incrementally store to database when we hit the storage batch size
                if len(similarity_scores) >= store_batch_size:
                    logger.info(f"Storing batch of {len(similarity_scores):,} similarities to database...")
                    self.store_similarities(similarity_scores)
                    total_stored += len(similarity_scores)
                    logger.info(f"Total stored so far: {total_stored:,}")
                    similarity_scores = []  # Clear the list to free memory

        # Store any remaining similarities
        if similarity_scores:
            logger.info(f"Storing final batch of {len(similarity_scores):,} similarities...")
            self.store_similarities(similarity_scores)
            total_stored += len(similarity_scores)

        logger.info(f"Complete! Stored {total_stored:,} similar pairs from {processed_pairs:,} comparisons")

        # Return count instead of full list (to avoid memory issues)
        return total_stored
    
    def store_similarities(self, similarities: List[DefinitionSimilarityScore], batch_size: int = 10000):
        """Store similarity scores in database with batching for large datasets.

        Args:
            similarities: List of similarity scores to store
            batch_size: Number of rows per batch (default: 10000, limited by PostgreSQL's 65535 parameter limit)

        Note: PostgreSQL has a limit of 65,535 parameters per query. Each row uses 4 parameters,
              so max batch size is 65535 / 4 = 16,383. We use 10,000 for extra safety margin.
        """
        logger.info(f"Storing {len(similarities)} similarity scores in batches of {batch_size}")

        data = [(s.word1_id, s.word2_id, s.cosine_similarity, s.model_name)
                for s in similarities]

        # Process in batches to avoid overwhelming the database
        total_batches = (len(data) + batch_size - 1) // batch_size
        for i in range(0, len(data), batch_size):
            batch = data[i:i + batch_size]
            batch_num = (i // batch_size) + 1
            logger.info(f"Storing batch {batch_num}/{total_batches} ({len(batch)} rows)")

            # Build VALUES clause with all rows in one query (avoids prepared statement issues)
            placeholders = ','.join(['(%s,%s,%s,%s)'] * len(batch))
            insert_query = f"""
                INSERT INTO vocab.definition_similarity
                (word1_id, word2_id, cosine_similarity, embedding_model)
                VALUES {placeholders}
                ON CONFLICT (word1_id, word2_id, embedding_model)
                DO UPDATE SET
                    cosine_similarity = EXCLUDED.cosine_similarity,
                    created_at = CURRENT_TIMESTAMP
            """

            # Flatten the batch data for the query
            flattened = [item for row in batch for item in row]

            with self._cursor(autocommit=True) as cursor:
                cursor.execute(insert_query, flattened)

            logger.info(f"Batch {batch_num}/{total_batches} completed")

        logger.info(f"All {len(similarities)} similarities stored successfully")

def main():
    """Main function for testing"""
    from config import get_db_config
    
    db_config = get_db_config()
    calculator = DefinitionSimilarityCalculator(db_config)
    
    print("=== Definition Similarity Calculator ===")
    print(f"Model: {calculator.model_name}")
    print(f"CUDA Available: {CUDA_AVAILABLE}")
    print()
    
    # Create tables
    calculator.create_definition_tables()
    
    # Get sample definitions for testing
    definitions = calculator.get_definitions(limit=100)
    print(f"Processing {len(definitions)} definitions for testing")
    
    # Generate embeddings
    calculator.generate_embeddings_batch(definitions)
    
    # Store embeddings
    calculator.store_embeddings(definitions)
    
    # Calculate similarities
    similarities = calculator.calculate_all_similarities(similarity_threshold=0.4)
    
    if similarities:
        print(f"\nTop 10 most similar definition pairs:")
        similarities.sort(key=lambda x: x.cosine_similarity, reverse=True)
        
        for i, sim in enumerate(similarities[:10]):
            with db_manager.get_cursor() as cursor:
                cursor.execute("SELECT term FROM vocab.defined WHERE id = %s", (sim.word1_id,))
                word1 = cursor.fetchone()[0]
                cursor.execute("SELECT term FROM vocab.defined WHERE id = %s", (sim.word2_id,))
                word2 = cursor.fetchone()[0]

            print(f"{i+1:2d}. {word1:15} <-> {word2:15} (similarity: {sim.cosine_similarity:.3f})")

if __name__ == "__main__":
    main()
