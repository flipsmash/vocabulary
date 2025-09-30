# Free Pronunciation Generation Strategy

## Current Situation
- **Total words**: 22,094
- **Words with WAV files**: 7,047
- **Words missing audio**: 15,047
- **All words have**: Complete phonetic data (IPA, ARPABET, stress patterns, syllable counts)

## Free TTS Options (Ranked by Quality)

### 1. **Microsoft Azure Cognitive Services Speech** (FREE TIER) ⭐⭐⭐⭐⭐
- **Quality**: Excellent neural voices
- **Free limit**: 500,000 characters/month
- **Cost**: FREE for our needs (~15,047 words = ~150,000 characters)
- **Setup**: Requires Azure free account
- **API**: REST API with Python SDK

### 2. **Google Cloud Text-to-Speech** (FREE TIER) ⭐⭐⭐⭐⭐
- **Quality**: Excellent WaveNet voices
- **Free limit**: 1 million characters/month  
- **Cost**: FREE for our needs
- **Setup**: Requires Google Cloud free account
- **API**: REST API with Python SDK

### 3. **Windows SAPI (pyttsx3)** (CURRENT) ⭐⭐⭐⭐
- **Quality**: Good, much better than eSpeak
- **Free limit**: Unlimited
- **Cost**: FREE (built into Windows)
- **Setup**: Already implemented
- **Voices**: Microsoft David/Zira

### 4. **Amazon Polly** (FREE TIER) ⭐⭐⭐⭐⭐
- **Quality**: Excellent neural voices
- **Free limit**: 5 million characters/month for first 12 months
- **Cost**: FREE for our needs
- **Setup**: Requires AWS free account

### 5. **IBM Watson Text to Speech** (FREE TIER) ⭐⭐⭐⭐
- **Quality**: Very good
- **Free limit**: 10,000 characters/month
- **Cost**: Would need multiple months
- **Setup**: IBM Cloud free account

## Recommended Implementation Plan

### Phase 1: Cloud TTS Setup (Best Quality)
1. **Set up Azure Speech Services** (500K chars/month free)
2. **Set up Google Cloud TTS** (1M chars/month free)
3. **Implement batch processing** with both services
4. **Total capacity**: 1.5M characters/month (enough for all 15,047 words)

### Phase 2: Enhanced Local TTS (Backup)
1. **Improve Windows SAPI quality** (current implementation)
2. **Add voice variety** (install additional SAPI voices)
3. **Fine-tune pronunciation** using phonetic data

### Phase 3: Hybrid Approach
1. **Use cloud TTS for difficult/rare words**
2. **Use local TTS for common words**
3. **Quality-based selection**

## Implementation Code Examples

### Azure Speech Services
```python
import azure.cognitiveservices.speech as speechsdk

def generate_with_azure(text: str, output_file: str):
    speech_config = speechsdk.SpeechConfig(
        subscription="YOUR_KEY", 
        region="eastus"
    )
    speech_config.speech_synthesis_voice_name = "en-US-JennyNeural"
    
    audio_config = speechsdk.audio.AudioOutputConfig(filename=output_file)
    synthesizer = speechsdk.SpeechSynthesizer(speech_config, audio_config)
    
    result = synthesizer.speak_text_async(text).get()
    return result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted
```

### Google Cloud TTS
```python
from google.cloud import texttospeech

def generate_with_google(text: str, output_file: str):
    client = texttospeech.TextToSpeechClient()
    
    synthesis_input = texttospeech.SynthesisInput(text=text)
    voice = texttospeech.VoiceSelectionParams(
        language_code="en-US",
        name="en-US-Neural2-F",
        ssml_gender=texttospeech.SsmlVoiceGender.FEMALE,
    )
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.LINEAR16
    )
    
    response = client.synthesize_speech(
        input=synthesis_input, voice=voice, audio_config=audio_config
    )
    
    with open(output_file, "wb") as out:
        out.write(response.audio_content)
    return True
```

## Cost Analysis (All FREE)

| Service | Free Limit | Our Usage | Status |
|---------|------------|-----------|--------|
| Azure Speech | 500K chars/month | ~150K chars | ✅ FREE |
| Google Cloud | 1M chars/month | ~150K chars | ✅ FREE |
| Windows SAPI | Unlimited | Any amount | ✅ FREE |
| Amazon Polly | 5M chars/month | ~150K chars | ✅ FREE |

## Quality Comparison

1. **Cloud services** (Azure, Google, Amazon): Near-human quality
2. **Windows SAPI**: Good quality, natural sounding
3. **eSpeak**: Robotic, avoid

## Next Steps

1. **Immediate**: Use improved Windows SAPI (current setup)
2. **Optional**: Set up Azure/Google for premium quality
3. **Long-term**: Hybrid cloud + local approach

## Web App Integration

Update the web app to serve audio files from the `pronunciation_files` directory:

```python
# Add to vocabulary_web_app.py
from fastapi.staticfiles import StaticFiles

app.mount("/pronunciation", StaticFiles(directory="pronunciation_files"), name="pronunciation")
```

This makes the generated files accessible at `/pronunciation/filename.wav`