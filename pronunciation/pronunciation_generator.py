#!/usr/bin/env python3
"""
Free Pronunciation Generator for Vocabulary Database
Generates WAV files for words missing pronunciation using free TTS engines
"""

import os
import sys
import mysql.connector
import subprocess
import tempfile
import shutil
from pathlib import Path
from typing import Optional, List, Tuple
import logging

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.config import get_db_config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PronunciationGenerator:
    def __init__(self, output_dir: str = "pronunciation_files"):
        self.config = get_db_config()
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
        # Check available TTS engines
        self.available_engines = self._detect_engines()
        logger.info(f"Available TTS engines: {self.available_engines}")
    
    def _detect_engines(self) -> List[str]:
        """Detect available TTS engines on the system"""
        engines = []
        
        # Check for eSpeak-NG
        try:
            result = subprocess.run(['espeak', '--version'], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                engines.append('espeak')
                logger.info("Found eSpeak-NG")
        except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
            pass
        
        # Check for Windows SAPI (pyttsx3)
        try:
            import pyttsx3
            engines.append('pyttsx3')
            logger.info("Found pyttsx3 (Windows SAPI)")
        except ImportError:
            pass
        
        # Check for Festival
        try:
            result = subprocess.run(['festival', '--version'], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                engines.append('festival')
                logger.info("Found Festival")
        except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
            pass
        
        return engines
    
    def get_words_missing_audio(self, limit: Optional[int] = None) -> List[Tuple]:
        """Get words that have phonetic data but no audio files"""
        conn = mysql.connector.connect(**self.config)
        cursor = conn.cursor()
        
        sql = """
        SELECT d.id, d.term, wp.ipa_transcription, wp.arpabet_transcription, 
               wp.stress_pattern, wp.syllable_count
        FROM vocab.defined d 
        JOIN vocab.word_phonetics wp ON d.id = wp.word_id 
        WHERE (d.wav_url IS NULL OR d.wav_url = "")
        AND (wp.ipa_transcription IS NOT NULL AND wp.ipa_transcription != "")
        ORDER BY d.term
        """
        
        if limit:
            sql += f" LIMIT {limit}"
        
        cursor.execute(sql)
        results = cursor.fetchall()
        conn.close()
        
        return results
    
    def generate_with_espeak(self, word: str, ipa: str, word_id: int) -> Optional[str]:
        """Generate pronunciation using eSpeak-NG with IPA input"""
        try:
            output_file = self.output_dir / f"{word_id}_{word}.wav"
            
            # eSpeak command with IPA input
            cmd = [
                'espeak',
                '-s', '150',  # Speed: 150 words per minute
                '-v', 'en',   # English voice
                '-w', str(output_file),  # Write to WAV file
                f"[[{ipa}]]"  # IPA input format for eSpeak
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0 and output_file.exists():
                logger.info(f"Generated {word} -> {output_file}")
                return str(output_file)
            else:
                logger.error(f"eSpeak failed for {word}: {result.stderr}")
                return None
                
        except Exception as e:
            logger.error(f"Error generating {word} with eSpeak: {e}")
            return None
    
    def generate_with_pyttsx3(self, word: str, word_id: int, arpabet: Optional[str] = None) -> Optional[str]:
        """Generate pronunciation using Windows SAPI via pyttsx3 with phonetic data"""
        try:
            import pyttsx3
            
            output_file = self.output_dir / f"{word_id}_{word}.wav"
            
            engine = pyttsx3.init()
            
            # Get available voices and prefer female voice (usually higher quality)
            voices = engine.getProperty('voices')
            if voices:
                # Look for Zira (female) or David (male) voices
                for voice in voices:
                    if 'zira' in voice.name.lower():
                        engine.setProperty('voice', voice.id)
                        break
                    elif 'david' in voice.name.lower() and len(voices) == 1:
                        engine.setProperty('voice', voice.id)
            
            engine.setProperty('rate', 130)  # Slower for clarity (default 200)
            engine.setProperty('volume', 0.9)  # Volume level (0.0 to 1.0)
            
            # Use phonetic pronunciation if available
            text_to_speak = word  # Fallback to word
            
            if arpabet:
                # Convert ARPABET to SAPI phonetic format
                sapi_phonemes = self._arpabet_to_sapi_phonemes(arpabet)
                if sapi_phonemes:
                    # Use SAPI phonetic markup
                    text_to_speak = f'<phoneme ph="{sapi_phonemes}">{word}</phoneme>'
                    logger.info(f"Using SAPI phonemes for {word}: {sapi_phonemes}")
            
            # Save to file
            engine.save_to_file(text_to_speak, str(output_file))
            engine.runAndWait()
            
            if output_file.exists():
                logger.info(f"Generated {word} -> {output_file}")
                return str(output_file)
            else:
                logger.error(f"pyttsx3 failed to create file for {word}")
                return None
                
        except Exception as e:
            logger.error(f"Error generating {word} with pyttsx3: {e}")
            return None
    
    def _arpabet_to_sapi_phonemes(self, arpabet: str) -> Optional[str]:
        """Convert ARPABET transcription to SAPI phoneme format"""
        if not arpabet:
            return None
            
        # ARPABET to SAPI phoneme mapping (expanded for better coverage)
        arpabet_to_sapi = {
            # Vowels
            'AE': 'ae', 'AE0': 'ae', 'AE1': 'ae', 'AE2': 'ae',
            'AH': 'ah', 'AH0': 'ah', 'AH1': 'ah', 'AH2': 'ah', 
            'AA': 'aa', 'AA0': 'aa', 'AA1': 'aa', 'AA2': 'aa',
            'AO': 'ao', 'AO0': 'ao', 'AO1': 'ao', 'AO2': 'ao',
            'AW': 'aw', 'AW0': 'aw', 'AW1': 'aw', 'AW2': 'aw',
            'AY': 'ay', 'AY0': 'ay', 'AY1': 'ay', 'AY2': 'ay',
            'EH': 'eh', 'EH0': 'eh', 'EH1': 'eh', 'EH2': 'eh',
            'ER': 'er', 'ER0': 'er', 'ER1': 'er', 'ER2': 'er',
            'EY': 'ey', 'EY0': 'ey', 'EY1': 'ey', 'EY2': 'ey',
            'IH': 'ih', 'IH0': 'ih', 'IH1': 'ih', 'IH2': 'ih',
            'IY': 'iy', 'IY0': 'iy', 'IY1': 'iy', 'IY2': 'iy',
            'OW': 'ow', 'OW0': 'ow', 'OW1': 'ow', 'OW2': 'ow',
            'OY': 'oy', 'OY0': 'oy', 'OY1': 'oy', 'OY2': 'oy',
            'UH': 'uh', 'UH0': 'uh', 'UH1': 'uh', 'UH2': 'uh',
            'UW': 'uw', 'UW0': 'uw', 'UW1': 'uw', 'UW2': 'uw',
            
            # Consonants
            'B': 'b', 'CH': 'ch', 'D': 'd', 'DH': 'dh', 'F': 'f',
            'G': 'g', 'HH': 'hh', 'JH': 'jh', 'K': 'k', 'L': 'l',
            'M': 'm', 'N': 'n', 'NG': 'ng', 'P': 'p', 'R': 'r',
            'S': 's', 'SH': 'sh', 'T': 't', 'TH': 'th', 'V': 'v',
            'W': 'w', 'Y': 'y', 'Z': 'z', 'ZH': 'zh',
        }
        
        try:
            # Split ARPABET into phonemes and convert
            phonemes = arpabet.strip().split()
            sapi_phonemes = []
            
            for phoneme in phonemes:
                if phoneme in arpabet_to_sapi:
                    sapi_phonemes.append(arpabet_to_sapi[phoneme])
                else:
                    # Remove stress numbers and try again
                    base_phoneme = ''.join(c for c in phoneme if not c.isdigit())
                    if base_phoneme in arpabet_to_sapi:
                        sapi_phonemes.append(arpabet_to_sapi[base_phoneme])
                    else:
                        logger.warning(f"Unknown ARPABET phoneme: {phoneme}")
                        return None  # If we can't convert, fall back to text
            
            return ' '.join(sapi_phonemes)
            
        except Exception as e:
            logger.error(f"Error converting ARPABET {arpabet}: {e}")
            return None
    
    def generate_with_festival(self, word: str, word_id: int) -> Optional[str]:
        """Generate pronunciation using Festival TTS"""
        try:
            output_file = self.output_dir / f"{word_id}_{word}.wav"
            
            # Create temporary scheme file for Festival
            with tempfile.NamedTemporaryFile(mode='w', suffix='.scm', delete=False) as f:
                f.write(f'''
                (set! utt1 (Utterance Text "{word}"))
                (utt.synth utt1)
                (utt.save.wave utt1 "{output_file}" 'riff)
                ''')
                scheme_file = f.name
            
            try:
                cmd = ['festival', '-b', scheme_file]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
                
                if result.returncode == 0 and output_file.exists():
                    logger.info(f"Generated {word} -> {output_file}")
                    return str(output_file)
                else:
                    logger.error(f"Festival failed for {word}: {result.stderr}")
                    return None
                    
            finally:
                os.unlink(scheme_file)  # Clean up temp file
                
        except Exception as e:
            logger.error(f"Error generating {word} with Festival: {e}")
            return None
    
    def update_database_with_audio_path(self, word_id: int, audio_path: str):
        """Update database with the path to the generated audio file"""
        conn = mysql.connector.connect(**self.config)
        cursor = conn.cursor()
        
        try:
            # Store relative path for portability
            relative_path = Path(audio_path).name
            
            cursor.execute(
                "UPDATE vocab.defined SET wav_url = %s WHERE id = %s",
                (f"/pronunciation/{relative_path}", word_id)
            )
            conn.commit()
            logger.info(f"Updated database for word_id {word_id}")
            
        except Exception as e:
            logger.error(f"Error updating database for word_id {word_id}: {e}")
        finally:
            conn.close()
    
    def generate_batch(self, limit: int = 100, engine: Optional[str] = None):
        """Generate pronunciations for a batch of words"""
        if not self.available_engines:
            logger.error("No TTS engines available. Please install eSpeak-NG, pyttsx3, or Festival.")
            return
        
        # Use specified engine or default to first available
        selected_engine = engine if engine in self.available_engines else self.available_engines[0]
        logger.info(f"Using TTS engine: {selected_engine}")
        
        words = self.get_words_missing_audio(limit=limit)
        logger.info(f"Processing {len(words)} words missing audio files")
        
        success_count = 0
        
        for word_id, term, ipa, arpabet, stress, syllables in words:
            try:
                audio_path = None
                
                if selected_engine == 'espeak' and ipa:
                    audio_path = self.generate_with_espeak(term, ipa, word_id)
                elif selected_engine == 'pyttsx3':
                    audio_path = self.generate_with_pyttsx3(term, word_id, arpabet)
                elif selected_engine == 'festival':
                    audio_path = self.generate_with_festival(term, word_id)
                
                if audio_path:
                    self.update_database_with_audio_path(word_id, audio_path)
                    success_count += 1
                
                # Progress update
                if (success_count + 1) % 10 == 0:
                    logger.info(f"Processed {success_count + 1}/{len(words)} words...")
                    
            except KeyboardInterrupt:
                logger.info("Process interrupted by user")
                break
            except Exception as e:
                logger.error(f"Unexpected error processing {term}: {e}")
                continue
        
        logger.info(f"Completed: {success_count}/{len(words)} pronunciations generated successfully")

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Generate pronunciation files for vocabulary database")
    parser.add_argument("--limit", type=int, default=100, 
                       help="Number of words to process (default: 100)")
    parser.add_argument("--engine", choices=['espeak', 'pyttsx3', 'festival'],
                       help="TTS engine to use (auto-detect if not specified)")
    parser.add_argument("--output-dir", default="pronunciation_files",
                       help="Directory to store generated audio files")
    
    args = parser.parse_args()
    
    generator = PronunciationGenerator(output_dir=args.output_dir)
    generator.generate_batch(limit=args.limit, engine=args.engine)

if __name__ == "__main__":
    main()