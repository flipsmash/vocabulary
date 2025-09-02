#!/usr/bin/env python3
"""
Definition Similarity Calculator using Sentence Transformers
Similar architecture to pronunciation similarity but for semantic meaning
"""

import mysql.connector
import numpy as np
import json
import logging
from typing import List, Tuple, Optional
from dataclasses import dataclass
from tqdm import tqdm
import time

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
    import cupy as cp
    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False

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
    
    def __init__(self, db_config, model_name="all-MiniLM-L6-v2"):
        self.db_config = db_config
        self.model_name = model_name
        
        if not SENTENCE_TRANSFORMERS_AVAILABLE:
            raise ImportError("sentence-transformers required. Install with: pip install sentence-transformers")
            
        logger.info(f"Loading SentenceTransformer model: {model_name}")
        self.model = SentenceTransformer(model_name)
        logger.info("Model loaded successfully")
        
        # GPU detection
        if CUDA_AVAILABLE:
            logger.info("CUDA available for accelerated similarity calculations")
        else:
            logger.info("Using CPU for similarity calculations")
    
    def get_connection(self):
        """Get database connection"""
        return mysql.connector.connect(**self.db_config)
    
    def create_definition_tables(self):
        """Create tables for definition embeddings and similarities"""
        
        create_embeddings_table = """
        CREATE TABLE IF NOT EXISTS definition_embeddings (
            word_id INT PRIMARY KEY,
            word VARCHAR(255) NOT NULL,
            definition_text TEXT NOT NULL,
            embedding_json TEXT,
            embedding_model VARCHAR(100),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (word_id) REFERENCES defined(id) ON DELETE CASCADE,
            INDEX idx_model (embedding_model)
        )
        """
        
        create_similarity_table = """
        CREATE TABLE IF NOT EXISTS definition_similarity (
            word1_id INT,
            word2_id INT,
            cosine_similarity DECIMAL(6,5),
            embedding_model VARCHAR(100),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (word1_id, word2_id, embedding_model),
            INDEX idx_cosine_similarity (cosine_similarity DESC),
            INDEX idx_word1_similarity (word1_id, cosine_similarity DESC),
            INDEX idx_word2_similarity (word2_id, cosine_similarity DESC),
            CONSTRAINT chk_def_word_order CHECK (word1_id < word2_id),
            FOREIGN KEY (word1_id) REFERENCES defined(id) ON DELETE CASCADE,
            FOREIGN KEY (word2_id) REFERENCES defined(id) ON DELETE CASCADE
        )
        """
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(create_embeddings_table)
            cursor.execute(create_similarity_table)
            conn.commit()
            logger.info("Created definition similarity tables")
    
    def get_definitions(self, limit: Optional[int] = None) -> List[DefinitionData]:
        """Get word definitions from database"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            query = """
            SELECT id, term, definition 
            FROM defined 
            WHERE definition IS NOT NULL 
            AND definition != '' 
            AND LENGTH(TRIM(definition)) > 10
            ORDER BY id
            """
            if limit:
                query += f" LIMIT {limit}"
            
            cursor.execute(query)
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
            return definitions
    
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
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            insert_query = """
            INSERT INTO definition_embeddings 
            (word_id, word, definition_text, embedding_json, embedding_model)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                definition_text = VALUES(definition_text),
                embedding_json = VALUES(embedding_json),
                embedding_model = VALUES(embedding_model)
            """
            
            data = []
            for def_data in definitions:
                if def_data.embedding is not None:
                    embedding_json = json.dumps(def_data.embedding.tolist())
                    data.append((
                        def_data.word_id,
                        def_data.word,
                        def_data.definition,
                        embedding_json,
                        self.model_name
                    ))
            
            cursor.executemany(insert_query, data)
            conn.commit()
            logger.info(f"Stored {len(data)} embeddings")
    
    def load_embeddings(self) -> List[DefinitionData]:
        """Load embeddings from database"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
            SELECT word_id, word, definition_text, embedding_json
            FROM definition_embeddings
            WHERE embedding_model = %s
            ORDER BY word_id
            """, (self.model_name,))
            
            results = cursor.fetchall()
            definitions = []
            
            for word_id, word, definition, embedding_json in results:
                embedding = np.array(json.loads(embedding_json))
                definitions.append(DefinitionData(
                    word_id=word_id,
                    word=word,
                    definition=definition,
                    embedding=embedding
                ))
            
            logger.info(f"Loaded {len(definitions)} embeddings")
            return definitions
    
    def calculate_cosine_similarity_matrix(self, embeddings1: np.ndarray, embeddings2: np.ndarray) -> np.ndarray:
        """Calculate cosine similarity matrix between two sets of embeddings"""
        if CUDA_AVAILABLE:
            return self._calculate_similarity_gpu(embeddings1, embeddings2)
        else:
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
    
    def calculate_all_similarities(self, similarity_threshold: float = 0.3, batch_size: int = 1000):
        """Calculate similarities between all definition pairs"""
        logger.info(f"Calculating definition similarities with threshold {similarity_threshold}")
        
        # Load embeddings
        definitions = self.load_embeddings()
        if not definitions:
            logger.error("No embeddings found. Run generate_embeddings first.")
            return
        
        embeddings = np.array([d.embedding for d in definitions])
        word_ids = [d.word_id for d in definitions]
        
        logger.info(f"Processing {len(definitions)} definitions")
        
        similarity_scores = []
        processed_pairs = 0
        
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
        
        logger.info(f"Found {len(similarity_scores)} similar pairs from {processed_pairs:,} comparisons")
        
        # Store similarities
        if similarity_scores:
            self.store_similarities(similarity_scores)
        
        return similarity_scores
    
    def store_similarities(self, similarities: List[DefinitionSimilarityScore]):
        """Store similarity scores in database"""
        logger.info(f"Storing {len(similarities)} similarity scores")
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            insert_query = """
            INSERT INTO definition_similarity 
            (word1_id, word2_id, cosine_similarity, embedding_model)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                cosine_similarity = VALUES(cosine_similarity)
            """
            
            data = [(s.word1_id, s.word2_id, s.cosine_similarity, s.model_name) 
                   for s in similarities]
            
            cursor.executemany(insert_query, data)
            conn.commit()
            logger.info("Similarities stored successfully")

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
            # Get word names for display
            with calculator.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT term FROM defined WHERE id = %s", (sim.word1_id,))
                word1 = cursor.fetchone()[0]
                cursor.execute("SELECT term FROM defined WHERE id = %s", (sim.word2_id,))
                word2 = cursor.fetchone()[0]
            
            print(f"{i+1:2d}. {word1:15} <-> {word2:15} (similarity: {sim.cosine_similarity:.3f})")

if __name__ == "__main__":
    main()