# Pronunciation Audio System

## Overview
Complete local pronunciation audio library with download/synthesis capabilities and web app integration.

## Current Status

### Coverage Stats
- **Total words**: 23,153
- **Words with Merriam-Webster URLs**: 7,067 (30.5%)
- **Words needing synthesis**: 16,086 (69.5%)
- **Existing local files**: 26 → Growing rapidly!

## Components

### 1. Pronunciation Library Builder (`build_pronunciation_library.py`)

Automated script to build complete local pronunciation library.

**Features:**
- ✅ Downloads from Merriam-Webster (respectful 3-second delays)
- ✅ Synthesizes missing pronunciations using Google TTS
- ✅ Updates database with local paths
- ✅ Resume capability (idempotent)
- ✅ Progress tracking with tqdm
- ✅ Error handling and logging

**Usage:**
```bash
# Test with small batch
uv run python3 build_pronunciation_library.py --download-limit 10 --synthesis-limit 10

# Full library build (will take ~6+ hours due to rate limiting)
uv run python3 build_pronunciation_library.py

# Download only
uv run python3 build_pronunciation_library.py --skip-synthesis

# Synthesis only
uv run python3 build_pronunciation_library.py --skip-download
```

**Time Estimates:**
- Downloads: ~7,000 words × 3 seconds = ~5.8 hours
- Synthesis: ~16,000 words × 0.5 seconds = ~2.2 hours
- **Total**: ~8 hours for complete library

**Conservative Rate Limiting:**
- 3 seconds between Merriam-Webster requests
- Proper User-Agent header
- Respectful scraping practices

### 2. Web App Integration

**Static File Serving:**
```python
app.mount("/pronunciation", StaticFiles(directory="pronunciation_files"), name="pronunciation")
```

**Pronunciation Macro System:**
- `templates/macros/pronunciation.html` - Reusable Jinja2 macros
- `pronunciation_button(word)` - Full button with icon
- `pronunciation_icon(word)` - Minimal inline icon (🔊)
- `pronunciation_script()` - JavaScript for audio playback

**Features:**
- Inline audio playback (no page refresh)
- Visual feedback (button changes color when playing)
- Preloading on hover for instant playback
- Error handling for missing files
- Stops previous audio when playing new

### 3. Template Updates

**Completed:**
- ✅ `base.html` - Added pronunciation button styles
- ✅ `browse.html` - Pronunciation icons next to word titles
- ✅ Created macros/pronunciation.html

**Remaining (Next Steps):**
- [ ] `index.html` (search results)
- [ ] `word_detail.html` (word page)
- [ ] `flashcard_study.html` (flashcards)
- [ ] `quiz.html` (quiz interface)
- [ ] `lookup.html` (lookup results)

## File Structure

```
pronunciation_files/           # Local audio storage
├── 1473_abacinate.wav
├── 1560_abactinal.wav
├── 19463_abbatoir.wav
└── ... (growing to 23,000+ files)

templates/
├── macros/
│   └── pronunciation.html     # Reusable macros
├── browse.html                # ✅ Updated
├── index.html                 # ⏳ TODO
├── word_detail.html           # ⏳ TODO
├── flashcard_study.html       # ⏳ TODO
└── quiz.html                  # ⏳ TODO

build_pronunciation_library.py # Main builder script
audit_pronunciation_coverage.py # Coverage audit tool
```

## Database Schema

```sql
-- defined table
wav_url VARCHAR(255)  -- Stores: /pronunciation/{id}_{term}.wav

-- Examples:
-- /pronunciation/1473_abacinate.wav (local)
-- https://media.merriam-webster.com/soundc11/v/vallec01.wav (external, will be downloaded)
```

## Dependencies

Added to `pyproject.toml`:
```toml
"gtts>=2.5.0",      # Google Text-to-Speech
"pydub>=0.25.0",    # Audio processing (optional)
```

## Next Steps

1. **Run Full Library Build** (8+ hours):
   ```bash
   nohup uv run python3 build_pronunciation_library.py > pronunciation_build.log 2>&1 &
   ```

2. **Update Remaining Templates**:
   - Add pronunciation macros to index.html, word_detail.html, flashcards, quiz

3. **Test Across All Pages**:
   - Browse page
   - Search results
   - Random word
   - Flashcards
   - Quiz interface
   - Lookup results

4. **Deploy**:
   - Ensure `pronunciation_files/` is accessible in production
   - Verify static file mounting works correctly
   - Test audio playback in production environment

## Testing

```bash
# Start web app
uv run python3 web_apps/vocabulary_web_app.py

# Visit http://localhost:8001/browse
# Look for 🔊 icons next to words
# Click to play pronunciation
```

## Notes

- MP3 files are created if ffmpeg is not available (gTTS default)
- WAV files are preferred for consistency
- File naming: `{word_id}_{sanitized_term}.wav`
- All pronunciations served from `/pronunciation/` endpoint
- Audio player stops previous audio automatically
- Hover preloading for instant playback

## Future Enhancements

- [ ] Batch download progress bar in web UI
- [ ] Admin panel to trigger rebuilds
- [ ] Pronunciation quality verification
- [ ] Alternative TTS voices/engines
- [ ] Caching layer (Redis) for frequently accessed audio
- [ ] CDN integration for production scaling
