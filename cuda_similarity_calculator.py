"""
CUDA-Accelerated Pronunciation Similarity Calculator
Speeds up pairwise comparisons using GPU parallelization
"""

import numpy as np
import cupy as cp  # CUDA-accelerated NumPy
import logging
from typing import List, Tuple, Dict, Optional
import json
import time
from dataclasses import dataclass
from tqdm import tqdm
import gc

logger = logging.getLogger(__name__)

@dataclass
class CUDAPhoneticFeatures:
    """GPU-optimized phonetic features"""
    word_id: int
    phoneme_vector: np.ndarray  # Fixed-length phoneme encoding
    stress_vector: np.ndarray   # Stress pattern as vector
    syllable_count: int
    rhyme_vector: np.ndarray    # Last N phonemes for rhyming

class CUDASimilarityCalculator:
    """GPU-accelerated similarity calculator"""
    
    def __init__(self, max_phoneme_length: int = 20, phoneme_vocab_size: int = 100):
        """
        Initialize CUDA similarity calculator
        
        Args:
            max_phoneme_length: Maximum number of phonemes to consider per word
            phoneme_vocab_size: Size of phoneme vocabulary for encoding
        """
        self.max_phoneme_length = max_phoneme_length
        self.phoneme_vocab_size = phoneme_vocab_size
        
        # Check CUDA availability
        if not cp.cuda.is_available():
            raise RuntimeError("CUDA is not available. Please install CUDA and CuPy.")
        
        self.device = cp.cuda.Device()
        logger.info(f"Using CUDA device: {self.device}")
        
        # Create phoneme vocabulary mapping
        self.phoneme_to_id = self._create_phoneme_vocabulary()
        
        # Similarity weights (can be tuned)
        self.weights = cp.array([0.4, 0.2, 0.3, 0.1], dtype=cp.float32)  # phonetic, stress, rhyme, syllable
        
    def _create_phoneme_vocabulary(self) -> Dict[str, int]:
        """Create a vocabulary mapping for phonemes"""
        # Common IPA phonemes - expand as needed
        common_phonemes = [
            # Vowels
            'i', 'ɪ', 'e', 'ɛ', 'æ', 'ɑ', 'ɔ', 'o', 'ʊ', 'u', 'ʌ', 'ə', 'ɜ', 'ɝ',
            'eɪ', 'aɪ', 'ɔɪ', 'aʊ', 'oʊ', 'ɪə', 'eə', 'ʊə',
            # Consonants  
            'p', 'b', 't', 'd', 'k', 'ɡ', 'f', 'v', 'θ', 'ð', 's', 'z', 'ʃ', 'ʒ',
            'h', 'm', 'n', 'ŋ', 'l', 'r', 'j', 'w', 'tʃ', 'dʒ',
            # Stress markers
            'ˈ', 'ˌ',
            # Common variants
            'iː', 'uː', 'ɑː', 'ɔː', 'ɜː'
        ]
        
        phoneme_to_id = {'<PAD>': 0, '<UNK>': 1}  # Special tokens
        for i, phoneme in enumerate(common_phonemes):
            phoneme_to_id[phoneme] = i + 2
            
        return phoneme_to_id
    
    def _encode_phonemes(self, phonemes: List[str]) -> np.ndarray:
        """Encode phonemes as fixed-length vector"""
        vector = np.zeros(self.max_phoneme_length, dtype=np.int32)
        
        for i, phoneme in enumerate(phonemes[:self.max_phoneme_length]):
            vector[i] = self.phoneme_to_id.get(phoneme, 1)  # 1 = <UNK>
            
        return vector
    
    def _encode_stress_pattern(self, stress_pattern: str) -> np.ndarray:
        """Encode stress pattern as vector"""
        vector = np.zeros(self.max_phoneme_length, dtype=np.float32)
        
        for i, char in enumerate(stress_pattern[:self.max_phoneme_length]):
            if char == '1':  # Primary stress
                vector[i] = 1.0
            elif char == '2':  # Secondary stress  
                vector[i] = 0.5
            # 0 remains 0 for unstressed
            
        return vector
    
    def _encode_rhyme(self, phonemes: List[str], rhyme_length: int = 3) -> np.ndarray:
        """Encode ending phonemes for rhyme comparison"""
        vector = np.zeros(rhyme_length, dtype=np.int32)
        
        # Take last N phonemes
        ending_phonemes = phonemes[-rhyme_length:] if len(phonemes) >= rhyme_length else phonemes
        
        for i, phoneme in enumerate(ending_phonemes):
            vector[-(len(ending_phonemes)-i)] = self.phoneme_to_id.get(phoneme, 1)
            
        return vector
    
    def prepare_features(self, phonetic_data_list: List) -> List[CUDAPhoneticFeatures]:
        """Convert phonetic data to GPU-optimized features"""
        features = []
        
        logger.info("Preparing phonetic features for GPU processing...")
        
        for data in tqdm(phonetic_data_list, desc="Encoding features"):
            # Get word ID
            word_id = getattr(data, 'word_id', 0)
            
            # Encode phonemes
            phoneme_vector = self._encode_phonemes(data.phonemes)
            
            # Encode stress pattern
            stress_vector = self._encode_stress_pattern(data.stress_pattern)
            
            # Encode rhyme
            rhyme_vector = self._encode_rhyme(data.phonemes)
            
            features.append(CUDAPhoneticFeatures(
                word_id=word_id,
                phoneme_vector=phoneme_vector,
                stress_vector=stress_vector,
                syllable_count=data.syllable_count,
                rhyme_vector=rhyme_vector
            ))
            
        logger.info(f"Prepared {len(features)} phonetic features")
        return features
    
    def _phonetic_distance_cuda(self, phonemes1: cp.ndarray, phonemes2: cp.ndarray) -> cp.ndarray:
        """Calculate phonetic distance on GPU using vectorized operations"""
        # Hamming distance (can be replaced with more sophisticated measures)
        matches = cp.sum(phonemes1 == phonemes2, axis=1)
        max_len = phonemes1.shape[1]
        
        # Normalize by maximum possible matches
        distances = 1.0 - (matches.astype(cp.float32) / max_len)
        return distances
    
    def _stress_similarity_cuda(self, stress1: cp.ndarray, stress2: cp.ndarray) -> cp.ndarray:
        """Calculate stress similarity on GPU"""
        # Cosine similarity for stress patterns
        dot_product = cp.sum(stress1 * stress2, axis=1)
        norm1 = cp.linalg.norm(stress1, axis=1)
        norm2 = cp.linalg.norm(stress2, axis=1)
        
        # Handle zero norms
        norms = norm1 * norm2
        similarity = cp.where(norms > 0, dot_product / norms, 0.0)
        return similarity
    
    def _rhyme_similarity_cuda(self, rhyme1: cp.ndarray, rhyme2: cp.ndarray) -> cp.ndarray:
        """Calculate rhyme similarity on GPU"""
        # Count matching ending phonemes
        matches = cp.sum(rhyme1 == rhyme2, axis=1)
        rhyme_length = rhyme1.shape[1]
        
        similarity = matches.astype(cp.float32) / rhyme_length
        return similarity
    
    def _syllable_similarity_cuda(self, syllables1: cp.ndarray, syllables2: cp.ndarray) -> cp.ndarray:
        """Calculate syllable similarity on GPU"""
        max_syllables = cp.maximum(syllables1, syllables2)
        diff = cp.abs(syllables1 - syllables2)
        
        similarity = cp.where(max_syllables > 0, 1.0 - (diff.astype(cp.float32) / max_syllables), 1.0)
        return similarity
    
    def calculate_batch_similarities_cuda(self, features1: List[CUDAPhoneticFeatures], 
                                        features2: List[CUDAPhoneticFeatures],
                                        batch_size: int = 10000) -> List[Tuple[int, int, float]]:
        """
        Calculate similarities between two sets of features using CUDA
        Returns list of (word1_id, word2_id, similarity) tuples
        """
        results = []
        
        # Convert features to GPU arrays
        n1, n2 = len(features1), len(features2)
        
        # Prepare arrays
        phonemes1 = cp.array([f.phoneme_vector for f in features1], dtype=cp.int32)
        phonemes2 = cp.array([f.phoneme_vector for f in features2], dtype=cp.int32)
        
        stress1 = cp.array([f.stress_vector for f in features1], dtype=cp.float32)
        stress2 = cp.array([f.stress_vector for f in features2], dtype=cp.float32)
        
        rhyme1 = cp.array([f.rhyme_vector for f in features1], dtype=cp.int32)
        rhyme2 = cp.array([f.rhyme_vector for f in features2], dtype=cp.int32)
        
        syllables1 = cp.array([f.syllable_count for f in features1], dtype=cp.int32)
        syllables2 = cp.array([f.syllable_count for f in features2], dtype=cp.int32)
        
        word_ids1 = [f.word_id for f in features1]
        word_ids2 = [f.word_id for f in features2]
        
        logger.info(f"Processing {n1} x {n2} = {n1*n2:,} similarity comparisons on GPU")
        
        # Process in batches to manage memory
        for i in tqdm(range(0, n1, batch_size), desc="GPU similarity batches"):
            end_i = min(i + batch_size, n1)
            batch1_size = end_i - i
            
            # Get batch data
            batch_phonemes1 = phonemes1[i:end_i]
            batch_stress1 = stress1[i:end_i]
            batch_rhyme1 = rhyme1[i:end_i]
            batch_syllables1 = syllables1[i:end_i]
            
            # Expand for pairwise comparison
            expanded_phonemes1 = cp.repeat(batch_phonemes1[:, None, :], n2, axis=1)
            expanded_phonemes2 = cp.tile(phonemes2[None, :, :], (batch1_size, 1, 1))
            
            expanded_stress1 = cp.repeat(batch_stress1[:, None, :], n2, axis=1)
            expanded_stress2 = cp.tile(stress2[None, :, :], (batch1_size, 1, 1))
            
            expanded_rhyme1 = cp.repeat(batch_rhyme1[:, None, :], n2, axis=1)
            expanded_rhyme2 = cp.tile(rhyme2[None, :, :], (batch1_size, 1, 1))
            
            expanded_syllables1 = cp.repeat(batch_syllables1[:, None], n2, axis=1)
            expanded_syllables2 = cp.tile(syllables2[None, :], (batch1_size, 1))
            
            # Reshape for vectorized operations
            flat_phonemes1 = expanded_phonemes1.reshape(-1, self.max_phoneme_length)
            flat_phonemes2 = expanded_phonemes2.reshape(-1, self.max_phoneme_length)
            
            flat_stress1 = expanded_stress1.reshape(-1, self.max_phoneme_length)
            flat_stress2 = expanded_stress2.reshape(-1, self.max_phoneme_length)
            
            flat_rhyme1 = expanded_rhyme1.reshape(-1, 3)  # rhyme_length = 3
            flat_rhyme2 = expanded_rhyme2.reshape(-1, 3)
            
            flat_syllables1 = expanded_syllables1.flatten()
            flat_syllables2 = expanded_syllables2.flatten()
            
            # Calculate similarity components
            phonetic_dist = self._phonetic_distance_cuda(flat_phonemes1, flat_phonemes2)
            stress_sim = self._stress_similarity_cuda(flat_stress1, flat_stress2)
            rhyme_sim = self._rhyme_similarity_cuda(flat_rhyme1, flat_rhyme2)
            syllable_sim = self._syllable_similarity_cuda(flat_syllables1, flat_syllables2)
            
            # Combined similarity (weighted average)
            phonetic_sim = 1.0 - phonetic_dist  # Convert distance to similarity
            overall_sim = (self.weights[0] * phonetic_sim + 
                          self.weights[1] * stress_sim +
                          self.weights[2] * rhyme_sim + 
                          self.weights[3] * syllable_sim)
            
            # Reshape back to matrix form
            similarity_matrix = overall_sim.reshape(batch1_size, n2)
            
            # Convert to CPU and extract results
            similarity_cpu = cp.asnumpy(similarity_matrix)
            
            for local_i in range(batch1_size):
                global_i = i + local_i
                for j in range(n2):
                    if similarity_cpu[local_i, j] > 0.1:  # Only store significant similarities
                        results.append((
                            word_ids1[global_i],
                            word_ids2[j], 
                            float(similarity_cpu[local_i, j])
                        ))
            
            # Clean up GPU memory
            del similarity_matrix, overall_sim, phonetic_sim, phonetic_dist, stress_sim, rhyme_sim, syllable_sim
            cp.get_default_memory_pool().free_all_blocks()
        
        logger.info(f"Generated {len(results):,} similarity pairs above threshold")
        return results
    
    def calculate_all_similarities_cuda(self, features: List[CUDAPhoneticFeatures], 
                                      similarity_threshold: float = 0.1,
                                      batch_size: int = 5000) -> List[Tuple[int, int, float]]:
        """
        Calculate all pairwise similarities using CUDA
        Uses triangular iteration to avoid duplicate pairs
        """
        n = len(features)
        total_pairs = n * (n - 1) // 2
        logger.info(f"Calculating {total_pairs:,} pairwise similarities on GPU")
        
        all_results = []
        
        # Process in triangular chunks
        for i in tqdm(range(0, n, batch_size), desc="Processing similarity chunks"):
            end_i = min(i + batch_size, n)
            
            # Upper triangle: compare with all following words
            if end_i < n:
                chunk_results = self.calculate_batch_similarities_cuda(
                    features[i:end_i], 
                    features[end_i:], 
                    batch_size=min(batch_size, 2000)
                )
                all_results.extend(chunk_results)
            
            # Within chunk: compare words within this batch (triangular)
            chunk_features = features[i:end_i]
            chunk_size = len(chunk_features)
            
            if chunk_size > 1:
                for local_i in range(chunk_size):
                    if local_i + 1 < chunk_size:
                        mini_results = self.calculate_batch_similarities_cuda(
                            [chunk_features[local_i]], 
                            chunk_features[local_i+1:],
                            batch_size=1000
                        )
                        all_results.extend(mini_results)
        
        # Filter by threshold
        filtered_results = [(w1, w2, sim) for w1, w2, sim in all_results 
                           if sim >= similarity_threshold]
        
        logger.info(f"Found {len(filtered_results):,} similarities above threshold {similarity_threshold}")
        return filtered_results


class CUDAIntegratedSimilaritySystem:
    """Integration class that combines CUDA calculator with existing system"""
    
    def __init__(self, db_manager, phonetic_processor):
        self.db_manager = db_manager
        self.phonetic_processor = phonetic_processor
        self.cuda_calculator = CUDASimilarityCalculator()
        self.hp_inserter = None  # Initialize when needed
        
    def calculate_all_similarities_cuda(self, similarity_threshold: float = 0.1):
        """Calculate similarities using CUDA acceleration with high-performance inserts"""
        logger.info("Starting CUDA-accelerated similarity calculation with optimized inserts...")
        
        # Initialize high-performance inserter
        if self.hp_inserter is None:
            from high_performance_inserter import StreamingCUDAInserter
            # Get database config from the connection_params attribute
            db_config = self.db_manager.connection_params.copy()
            self.hp_inserter = StreamingCUDAInserter(db_config, stream_batch_size=100000)
            logger.info("Initialized high-performance inserter with 100k batch size")
        
        # Get all phonetic data from database
        with self.db_manager.get_connection() as conn:
            query = """
            SELECT word_id, word, ipa_transcription, arpabet_transcription,
                   syllable_count, stress_pattern, phonemes_json
            FROM word_phonetics
            WHERE ipa_transcription != ''
            """
            import pandas as pd
            df = pd.read_sql(query, conn)
        
        logger.info(f"Loaded {len(df)} words for CUDA processing")
        
        # Convert to phonetic data objects
        from modern_pronunciation_system import PhoneticData
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
        
        # Prepare features for CUDA
        features = self.cuda_calculator.prepare_features(phonetic_data_list)
        
        # Calculate similarities on GPU with streaming inserts
        logger.info("Starting GPU similarity calculation with concurrent database inserts...")
        start_time = time.time()
        
        # Process in chunks to allow streaming inserts
        chunk_size = 5000  # Process 5k words at a time
        total_similarities = 0
        
        for i in range(0, len(features), chunk_size):
            chunk_end = min(i + chunk_size, len(features))
            chunk_features = features[i:chunk_end]
            
            logger.info(f"Processing chunk {i//chunk_size + 1}/{(len(features)-1)//chunk_size + 1}: words {i}-{chunk_end}")
            
            # Calculate similarities for this chunk
            similarity_results = self.cuda_calculator.calculate_all_similarities_cuda(
                chunk_features, similarity_threshold=similarity_threshold
            )
            
            # Stream results to high-performance inserter
            if similarity_results:
                self.hp_inserter.add_similarities(similarity_results)
                total_similarities += len(similarity_results)
            
            # Show progress
            elapsed = time.time() - start_time
            stats = self.hp_inserter.get_stats()
            logger.info(f"Chunk complete: {total_similarities:,} similarities found, "
                       f"{stats['insertion_rate']:.0f}/sec insert rate, "
                       f"queue: {stats['queue_size']}")
        
        end_time = time.time()
        
        logger.info(f"CUDA calculation completed in {end_time - start_time:.2f} seconds")
        logger.info(f"Total similarities found: {total_similarities:,}")
        
        # Flush remaining inserts
        logger.info("Flushing remaining database inserts...")
        self.hp_inserter.shutdown()
        self.hp_inserter = None  # Reset for next run
        
        logger.info("CUDA similarity calculation and high-performance storage complete!")


def check_cuda_setup():
    """Check if CUDA setup is working"""
    try:
        import cupy as cp
        
        print("[INFO] Checking CUDA setup...")
        print(f"[OK] CuPy version: {cp.__version__}")
        print(f"[OK] CUDA available: {cp.cuda.is_available()}")
        
        if cp.cuda.is_available():
            device = cp.cuda.Device()
            print(f"[OK] CUDA device: {device}")
            print(f"[OK] Device memory: {device.mem_info[1] // (1024**3)} GB")
            
            # Simple test
            a = cp.array([1, 2, 3])
            b = cp.array([4, 5, 6])
            c = a + b
            print(f"[OK] CUDA computation test: {cp.asnumpy(c)}")
            
            return True
        else:
            print("[ERROR] CUDA not available")
            return False
            
    except ImportError:
        print("[ERROR] CuPy not installed. Install with: pip install cupy-cuda11x")
        return False
    except Exception as e:
        print(f"[ERROR] CUDA setup error: {e}")
        return False


if __name__ == "__main__":
    # Test CUDA setup
    if check_cuda_setup():
        print("\n🚀 CUDA setup is working! You can use GPU acceleration.")
        print("\nTo install CuPy:")
        print("  pip install cupy-cuda11x  # for CUDA 11.x")
        print("  pip install cupy-cuda12x  # for CUDA 12.x")
    else:
        print("\n⚠️  CUDA setup failed. Using CPU-only version.")
        print("\nTo enable CUDA:")
        print("1. Install CUDA toolkit from NVIDIA")
        print("2. Install CuPy: pip install cupy-cuda11x")
