import soundfile as sf
import logging

logger = logging.getLogger(__name__)

def get_audio_duration(audio_file_path):
    """
    Get audio duration using soundfile (faster than librosa for metadata only).
    
    Args:
        audio_file_path: Path to audio file
        
    Returns:
        float: Audio duration in seconds, or None if failed
    """
    try:
        # Use soundfile to get audio info without loading the entire file
        info = sf.info(audio_file_path)
        duration = info.frames / info.samplerate
        logger.debug(f" | Audio duration calculated using soundfile: {duration:.2f}s | ")
        return duration
    except Exception as e:
        logger.warning(f" | Failed to get audio duration using soundfile: {e} | ")
        return None

def calculate_rtf(result, audio_file_path, processing_time):
    """
    Calculate Real Time Factor (RTF) for speech processing.
    
    Args:
        result: Azure Speech SDK result object containing duration information
        audio_file_path (str): Path to the audio file for fallback duration calculation
        processing_time (float): Time taken to process the audio
        
    Returns:
        float: Real Time Factor (processing_time / audio_duration), 0.0 if calculation fails
    """
    try:
        # Handle Azure Speech duration units (100ns ticks)
        azure_duration_seconds = 0
        if isinstance(result.duration, int):
            # Azure Speech returns duration in 100-nanosecond ticks
            # 1 second = 10,000,000 ticks (10^7)
            azure_duration_seconds = result.duration / 10000000.0
        elif hasattr(result.duration, 'total_seconds'):
            azure_duration_seconds = result.duration.total_seconds()
        else:
            azure_duration_seconds = float(result.duration) if result.duration else 0
        
        # If Azure provides valid duration, use it
        if azure_duration_seconds > 0:
            return processing_time / azure_duration_seconds
        
        # Fallback to soundfile for audio duration if Azure doesn't provide it
        file_duration = get_audio_duration(audio_file_path)
        if file_duration and file_duration > 0:
            return processing_time / file_duration
        
        # If both methods fail, return 0.0
        return 0.0
        
    except Exception as e:
        logger.warning(f" | Could not calculate RTF: {e} | ")
        return 0.0