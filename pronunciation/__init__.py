"""
Pronunciation analysis and similarity calculation.

This package contains CUDA-accelerated pronunciation processing:
- Modern pronunciation system with phonetic analysis
- CUDA similarity calculator for massive-scale comparisons
- Pronunciation generator using espeak
- Performance optimization utilities
"""

from .modern_pronunciation_system import ModernPronunciationSystem
from .cuda_similarity_calculator import CUDASimilarityCalculator
from .pronunciation_generator import PronunciationGenerator

__all__ = [
    'ModernPronunciationSystem',
    'CUDASimilarityCalculator',
    'PronunciationGenerator'
]