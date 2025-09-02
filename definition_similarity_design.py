#!/usr/bin/env python3
"""
Design for Definition Similarity System
Similar architecture to pronunciation similarity but for word definitions
"""

from dataclasses import dataclass
from typing import List, Optional
import numpy as np

# Database Schema Extensions
CREATE_DEFINITION_EMBEDDINGS_TABLE = """
CREATE TABLE IF NOT EXISTS definition_embeddings (
    word_id INT PRIMARY KEY,
    word VARCHAR(255) NOT NULL,
    definition_text TEXT NOT NULL,
    embedding_vector JSON,  -- Store as JSON array
    embedding_model VARCHAR(100),  -- Track which model was used
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (word_id) REFERENCES defined(id) ON DELETE CASCADE,
    INDEX idx_model (embedding_model)
)
"""

CREATE_DEFINITION_SIMILARITY_TABLE = """
CREATE TABLE IF NOT EXISTS definition_similarity (
    word1_id INT,
    word2_id INT,
    cosine_similarity DECIMAL(6,5),
    semantic_category VARCHAR(100),  -- e.g., 'emotion', 'action', 'object'
    embedding_model VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (word1_id, word2_id, embedding_model),
    INDEX idx_cosine_similarity (cosine_similarity DESC),
    INDEX idx_word1_similarity (word1_id, cosine_similarity DESC),
    INDEX idx_category (semantic_category, cosine_similarity DESC),
    CONSTRAINT chk_word_order CHECK (word1_id < word2_id),
    FOREIGN KEY (word1_id) REFERENCES defined(id) ON DELETE CASCADE,
    FOREIGN KEY (word2_id) REFERENCES defined(id) ON DELETE CASCADE
)
"""

@dataclass
class DefinitionEmbedding:
    """Definition embedding data structure"""
    word_id: int
    word: str
    definition: str
    embedding: np.ndarray
    model_name: str

@dataclass
class DefinitionSimilarity:
    """Definition similarity score"""
    word1_id: int
    word2_id: int
    cosine_similarity: float
    semantic_category: Optional[str] = None
    model_name: str = "all-MiniLM-L6-v2"

class DefinitionSimilaritySystem:
    """System for calculating definition similarities"""
    
    def __init__(self, db_config, model_name="all-MiniLM-L6-v2"):
        from sentence_transformers import SentenceTransformer
        from config import config
        
        self.db_config = db_config
        self.model = SentenceTransformer(model_name)
        self.model_name = model_name
        
    def get_definitions_from_database(self, limit: Optional[int] = None) -> List[tuple]:
        """Get word definitions from existing database"""
        # Assuming definitions are in the 'defined' table
        # You'll need to check your actual schema
        pass
    
    def generate_embeddings(self, definitions: List[str]) -> np.ndarray:
        """Generate embeddings for a batch of definitions"""
        return self.model.encode(definitions, convert_to_numpy=True)
    
    def calculate_cosine_similarity(self, embedding1: np.ndarray, embedding2: np.ndarray) -> float:
        """Calculate cosine similarity between two embeddings"""
        return np.dot(embedding1, embedding2) / (np.linalg.norm(embedding1) * np.linalg.norm(embedding2))
    
    def process_definitions(self, batch_size: int = 1000):
        """Process all definitions and generate embeddings"""
        # Similar to phonetic processing pipeline
        pass
    
    def calculate_all_similarities(self, similarity_threshold: float = 0.3):
        """Calculate similarities between all definition pairs"""
        # Similar to pronunciation similarity calculation
        # But using cosine similarity of embeddings
        pass

# CUDA-accelerated version for large-scale processing
class CUDADefinitionSimilarity:
    """CUDA-accelerated definition similarity calculation"""
    
    def __init__(self, db_config, model_name="all-MiniLM-L6-v2"):
        try:
            import cupy as cp
            self.cp = cp
            self.cuda_available = True
        except ImportError:
            self.cuda_available = False
            
        self.model_name = model_name
        
    def calculate_batch_similarities_cuda(self, embeddings1: np.ndarray, embeddings2: np.ndarray) -> np.ndarray:
        """Calculate cosine similarities using GPU"""
        if not self.cuda_available:
            return self._calculate_batch_similarities_cpu(embeddings1, embeddings2)
            
        # Convert to CuPy arrays
        gpu_emb1 = self.cp.asarray(embeddings1)
        gpu_emb2 = self.cp.asarray(embeddings2)
        
        # Calculate cosine similarity matrix on GPU
        # cos_sim = (A @ B.T) / (||A|| * ||B||)
        norms1 = self.cp.linalg.norm(gpu_emb1, axis=1, keepdims=True)
        norms2 = self.cp.linalg.norm(gpu_emb2, axis=1, keepdims=True)
        
        normalized_emb1 = gpu_emb1 / norms1
        normalized_emb2 = gpu_emb2 / norms2
        
        similarities = normalized_emb1 @ normalized_emb2.T
        
        return self.cp.asnumpy(similarities)

# Integration with existing quiz system
def find_definition_distractors(target_word_id: int, num_distractors: int = 5, 
                              similarity_range: tuple = (0.4, 0.8)) -> List[tuple]:
    """
    Find distractors based on definition similarity
    
    Args:
        target_word_id: The target word ID
        num_distractors: Number of distractors to return
        similarity_range: (min_sim, max_sim) - not too similar, not too different
    
    Returns:
        List of (word_id, word, similarity_score) tuples
    """
    pass

def find_semantic_categories(similarity_threshold: float = 0.7) -> dict:
    """
    Group words into semantic categories based on definition similarity
    
    Returns:
        Dict mapping category names to lists of word IDs
    """
    pass

if __name__ == "__main__":
    # Example usage
    print("Definition Similarity System Design")
    print("=" * 50)
    
    print("1. Text Embedding Approach:")
    print("   - Use SentenceTransformers for semantic embeddings")
    print("   - Store embeddings in definition_embeddings table")
    print("   - Calculate cosine similarity between embeddings")
    print("   - GPU acceleration with CuPy for large-scale processing")
    
    print("\n2. Database Schema:")
    print("   - definition_embeddings: Store word embeddings")
    print("   - definition_similarity: Store similarity scores")
    print("   - Indexed by similarity score for fast retrieval")
    
    print("\n3. Integration:")
    print("   - Combine with pronunciation similarity for better distractors")
    print("   - Semantic categories for quiz organization")
    print("   - Similar architecture to existing pronunciation system")