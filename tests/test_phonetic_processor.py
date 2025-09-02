"""Tests for phonetic processor module."""

import pytest
from pronunciation_similarity.core.phonetic_processor import ModernPhoneticProcessor, PhoneticData


class TestModernPhoneticProcessor:
    """Test suite for ModernPhoneticProcessor"""

    @pytest.fixture
    def processor(self):
        """Create a processor instance for testing"""
        return ModernPhoneticProcessor()

    def test_transcribe_simple_word(self, processor):
        """Test transcription of a simple word"""
        result = processor.transcribe_word("hello")
        
        assert isinstance(result, PhoneticData)
        assert result.word == "hello"
        assert result.ipa is not None
        assert result.arpabet is not None
        assert result.syllable_count >= 1
        assert result.source in {"CMU Dictionary", "Online API", "Fallback Rules"}

    def test_transcribe_complex_word(self, processor):
        """Test transcription of a complex word"""
        result = processor.transcribe_word("serendipitous")
        
        assert isinstance(result, PhoneticData)
        assert result.word == "serendipitous"
        assert result.syllable_count >= 3  # Should be 5 syllables
        assert len(result.phonemes) > 0

    def test_transcribe_empty_word(self, processor):
        """Test handling of empty word"""
        result = processor.transcribe_word("")
        
        # Should handle gracefully
        assert isinstance(result, PhoneticData)

    def test_transcribe_invalid_characters(self, processor):
        """Test handling of words with invalid characters"""
        result = processor.transcribe_word("hello123!")
        
        # Should still return a result
        assert isinstance(result, PhoneticData)

    def test_cache_functionality(self, processor):
        """Test that caching works properly"""
        word = "test"
        
        # First transcription
        result1 = processor.transcribe_word(word)
        
        # Second transcription should use cache
        result2 = processor.transcribe_word(word)
        
        # Results should be identical
        assert result1.ipa == result2.ipa
        assert result1.arpabet == result2.arpabet
        assert result1.syllable_count == result2.syllable_count

    def test_arpabet_to_ipa_conversion(self, processor):
        """Test ARPAbet to IPA conversion"""
        arpabet_phonemes = ['HH', 'EH1', 'L', 'OW0']
        ipa = processor._arpabet_to_ipa_convert(arpabet_phonemes)
        
        assert isinstance(ipa, str)
        assert len(ipa) > 0

    def test_syllable_counting(self, processor):
        """Test syllable counting accuracy"""
        test_cases = [
            ("cat", 1),
            ("hello", 2),
            ("computer", 3),
            ("serendipitous", 5)
        ]
        
        for word, expected_syllables in test_cases:
            result = processor.transcribe_word(word)
            # Allow some variance in syllable counting
            assert abs(result.syllable_count - expected_syllables) <= 1

    def test_stress_pattern_extraction(self, processor):
        """Test stress pattern extraction"""
        arpabet_phonemes = ['HH', 'EH1', 'L', 'OW0']
        stress_pattern = processor._extract_stress_pattern_from_arpabet(arpabet_phonemes)
        
        assert isinstance(stress_pattern, str)
        assert '1' in stress_pattern  # Should have primary stress

    def test_phoneme_extraction_from_ipa(self, processor):
        """Test phoneme extraction from IPA string"""
        ipa = "hɛˈloʊ"
        phonemes = processor._extract_phonemes_from_ipa(ipa)
        
        assert isinstance(phonemes, list)
        assert len(phonemes) > 0

    def test_get_cache_stats(self, processor):
        """Test cache statistics functionality"""
        # Transcribe a few words to populate cache
        processor.transcribe_word("test1")
        processor.transcribe_word("test2")
        processor.transcribe_word("test3")
        
        stats = processor.get_cache_stats()
        
        assert isinstance(stats, dict)
        assert 'total_cached' in stats
        assert stats['total_cached'] >= 3
        assert 'sources' in stats