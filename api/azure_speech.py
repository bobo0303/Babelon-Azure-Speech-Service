import os  
import time  
import json
import logging  
import threading
import logging.handlers
import azure.cognitiveservices.speech as speechsdk

from lib.constant import DEFAULT_CONFIG, LANGUAGE_LIST, LANGUAGE_MATCH, LANGUAGE_MATCH_BACK, WAITING_TIME
from api.audio_utils import calculate_rtf
  
logger = logging.getLogger(__name__)  
  
# Configure logger settings (if not already configured)
if not logger.handlers:  
    log_format = "%(asctime)s - %(message)s"  
    log_file = "logs/app.log"  
    logging.basicConfig(level=logging.INFO, format=log_format)  
  
    # Create file handler with rotation (max 10MB per file, keep 5 backups)
    file_handler = logging.handlers.RotatingFileHandler(  
        log_file, maxBytes=10*1024*1024, backupCount=5  
    )  
    file_handler.setFormatter(logging.Formatter(log_format))  
  
    # Create console handler for real-time output
    console_handler = logging.StreamHandler()  
    console_handler.setFormatter(logging.Formatter(log_format))  
  
    logger.addHandler(file_handler)  
    logger.addHandler(console_handler)  
  
logger.setLevel(logging.INFO)  
logger.propagate = False  

##############################################################################  

class AzureSpeechModel:  
    """
    Azure Speech Service Model for speech recognition and translation.
    
    This class provides a delayed configuration architecture where Azure SDK 
    objects are created dynamically during inference to ensure thread safety.
    """
    
    def __init__(self, config_path=DEFAULT_CONFIG):  
        """
        Initialize the Model class with basic configuration attributes.
        
        Args:
            config_path (str): Path to the configuration JSON file
        """  
        with open(config_path, 'r') as config_file:
            config = json.load(config_file)

        # Store basic configuration that will be used to create SDK objects later
        self.model_version = config.get("name", None)
        self.subscription_key = config.get("SubscriptionKey", None)
        self.service_region = config.get("ServiceRegion", None)
        self.endpoint_id = config.get("EndpointId", None)  # Custom model endpoint
        self.dict = []  # Custom vocabulary dictionary
        
    def change_custom_model(self, config_path):
        """
        Change the model configuration to a different Azure Speech model.
        
        Args:
            config_path (str): Path to the new configuration JSON file
            
        Returns:
            bool: True if configuration change was successful, False otherwise
        """
        with open(config_path, 'r') as config_file:
            config = json.load(config_file)

        new_version = config.get("name", None)
        new_subscription_key = config.get("SubscriptionKey", None)
        new_service_region = config.get("ServiceRegion", None)
        new_endpoint_id = config.get("EndpointId", None)

        # Validate required configuration parameters
        if new_version is not None and new_subscription_key is not None and new_service_region is not None:
            logger.info(f" | Changed from '{self.model_version}' to '{new_version}' successfully | ")
            self.model_version = new_version
            self.subscription_key = new_subscription_key
            self.service_region = new_service_region
            self.endpoint_id = new_endpoint_id
            return True
        else:   
            logger.error(f" | Failed to change model configuration. Return to original version. | ")
            return False
        
    def update_dict(self, dictionary):  
        """
        Update the custom vocabulary dictionary used for improved recognition.
        
        Args:
            dictionary (list): List of custom words/phrases to enhance recognition
        """
        self.dict = dictionary
        logger.info(f" | Updated dictionary with {len(self.dict)} entries. | ")
        
    def _set_dict(self, prev_text, recognizer):
        """
        Configure phrase list grammar for improved speech recognition accuracy.
        
        Args:
            prev_text (str): Previous text to add as context vocabulary
            recognizer: Azure Speech recognizer instance
        """
        start_time = time.time()
        words = list(self.dict)  
        words.extend(prev_text)
        
        # Setup phrase list (if vocabulary exists)
        if words:
            phrase_list = speechsdk.PhraseListGrammar.from_recognizer(recognizer)
            for word in words:
                if word.strip():  # Ensure not empty string
                    phrase_list.addPhrase(word.strip())
            logger.debug(f" | Added {len(words)} phrases to recognition grammar | ")
        logger.debug(f" | Setup PhraseList time: {time.time() - start_time:.2f} | ")
    
    def _configure_timeout_settings(self, config):
        """
        Configure extended timeout settings for longer audio files.
        
        Args:
            config: Azure Speech config instance (SpeechConfig or SpeechTranslationConfig)
        """
        # Configure extended timeout settings for longer audio files
        config.set_property(
            speechsdk.PropertyId.SpeechServiceConnection_EndSilenceTimeoutMs, "5000"  # 5 seconds
        )
        config.set_property(
            speechsdk.PropertyId.SpeechServiceConnection_InitialSilenceTimeoutMs, "10000"  # 10 seconds
        )
        # Disable audio logging for privacy and performance optimization
        config.set_property(
            speechsdk.PropertyId.SpeechServiceConnection_EnableAudioLogging, "false"
        )
        logger.debug(" | Configured extended timeout settings (EndSilence: 5s, InitialSilence: 10s) | ")

    # def _recognize_with_timeout(self, recognizer, operation_name="Recognition"):
    #     """
    #     Generic timeout wrapper for Azure Speech recognition operations.
        
    #     Args:
    #         recognizer: Azure Speech recognizer instance
    #         operation_name (str): Name of the operation for logging
            
    #     Returns:
    #         tuple: (result, timeout_occurred)
    #             - result: Recognition result or None if timeout
    #             - timeout_occurred (bool): True if timeout occurred
    #     """

    #     result = None
    #     timeout_occurred = False
        
    #     def timeout_handler():
    #         nonlocal timeout_occurred
    #         time.sleep(WAITING_TIME)
    #         if result is None:  # Still running
    #             timeout_occurred = True
    #             logger.warning(f" | {operation_name} has exceeded the upper limit time and has been stopped | ")
    #             try:
    #                 # Use unified method for all recognizer types
    #                 recognizer.stop_continuous_recognition()
    #                 logger.debug(f" | Called stop_continuous_recognition() | ")
    #             except Exception as e:
    #                 logger.error(f" | Failed to stop recognizer: {e} | ")
        
    #     # Start timeout timer
    #     timeout_thread = threading.Thread(target=timeout_handler)
    #     timeout_thread.daemon = True
    #     timeout_thread.start()
        
    #     try:
    #         result = recognizer.recognize_once()
    #     except Exception as e:
    #         if timeout_occurred:
    #             logger.info(f" | {operation_name} stopped due to timeout | ")
    #             return None, True
    #         else:
    #             raise e
        
    #     return result, timeout_occurred
    
    def _continuous_recognition_with_timeout(self, recognizer, operation_name="Recognition", is_translation=False):
        """
        Universal continuous recognition wrapper for both speech recognition and translation.
        
        Args:
            recognizer: Azure Speech recognizer instance (SpeechRecognizer or TranslationRecognizer)
            operation_name (str): Name of the operation for logging
            is_translation (bool): True for TranslationRecognizer, False for SpeechRecognizer
            
        Returns:
            tuple: For translation: (combined_transcription, combined_translations, timeout_occurred)
                   For recognition: (combined_text, timeout_occurred)
        """

        # Common variables
        transcription_results = []
        translation_results = {} if is_translation else None
        recognition_done = False
        timeout_occurred = False
        
        def stop_recognizer_async(reason="unknown"):
            """
            Unified asynchronous method to stop the recognizer without blocking.
            
            Args:
                reason (str): Reason for stopping (for logging)
            
            Returns:
                threading.Thread: The thread handling the stop operation
            """
            def stop_worker():
                try:
                    recognizer.stop_continuous_recognition()
                    logger.debug(f" | {operation_name} recognizer stopped successfully ({reason}) | ")
                except Exception as e:
                    logger.error(f" | Failed to stop continuous {operation_name.lower()} ({reason}): {e} | ")
            
            stop_thread = threading.Thread(target=stop_worker)
            stop_thread.daemon = True
            stop_thread.start()
            return stop_thread
        
        def on_result_received(evt):
            if evt.result.text:
                transcription_results.append(evt.result.text)
                logger.debug(f" | {operation_name} segment: {evt.result.text} | ")
                
                # Handle translation results if this is a translation operation
                if is_translation and hasattr(evt.result, 'translations'):
                    for target_lang in evt.result.translations:
                        if target_lang not in translation_results:
                            translation_results[target_lang] = []
                        translation_results[target_lang].append(evt.result.translations[target_lang])
                        logger.debug(f" | {target_lang}: {evt.result.translations[target_lang]} | ")
        
        def on_canceled(evt):
            nonlocal recognition_done
            recognition_done = True
            logger.debug(f" | {operation_name} canceled: {evt.result.cancellation_details} | ")
        
        def on_session_stopped(evt):
            nonlocal recognition_done
            recognition_done = True
            logger.debug(f" | {operation_name} session stopped | ")
        
        def timeout_handler():
            nonlocal timeout_occurred, recognition_done
            time.sleep(WAITING_TIME)
            if not recognition_done:
                timeout_occurred = True
                logger.warning(f" | {operation_name} has exceeded the upper limit time and has been stopped. | ")
                stop_recognizer_async("timeout")
        
        # Connect callbacks - handle both SpeechRecognizer and TranslationRecognizer
        recognizer.recognized.connect(on_result_received)
        recognizer.canceled.connect(on_canceled) 
        recognizer.session_stopped.connect(on_session_stopped)
        
        # Optional: Connect recognizing event for intermediate results (mainly for TranslationRecognizer)
        if hasattr(recognizer, 'recognizing') and is_translation:
            recognizer.recognizing.connect(lambda evt: None)
        
        # Start timeout timer
        timeout_thread = threading.Thread(target=timeout_handler)
        timeout_thread.daemon = True
        timeout_thread.start()
        
        try:
            # Start continuous recognition
            recognizer.start_continuous_recognition()
            
            # Wait for recognition to complete or timeout
            while not recognition_done and not timeout_occurred:
                time.sleep(0.1)
                
            # Stop recognition asynchronously to avoid blocking
            stop_thread = stop_recognizer_async("normal completion")
            
            # Give the stop operation a moment to complete, but don't wait too long
            stop_thread.join(timeout=2.0)  # Wait up to 2 seconds for graceful shutdown
            
        except Exception as e:
            if timeout_occurred:
                logger.info(f" | {operation_name} stopped due to timeout | ")
            else:
                raise e
        
        # Combine all results with intelligent spacing
        if transcription_results:
            # Join segments and clean up spacing
            combined_text = " ".join(transcription_results).strip()
            
            # Clean up excessive spacing for Chinese text
            import re
            # Remove multiple spaces between Chinese characters
            combined_text = re.sub(r'(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])', '', combined_text)
            # Remove spaces around Chinese punctuation
            combined_text = re.sub(r'\s*([，。？！；：])\s*', r'\1', combined_text)
            # Clean up any remaining multiple spaces
            combined_text = re.sub(r'\s+', ' ', combined_text).strip()
            
            combined_transcription = combined_text
        else:
            combined_transcription = ""
        
        if is_translation:
            # Return translation format: (transcription, translations_dict, timeout)
            combined_translations = {}
            for target_lang, segments in translation_results.items():
                # Join segments and clean up spacing for translations
                joined_text = " ".join(segments).strip()
                
                # Clean up excessive spacing for Chinese text in translations
                import re
                joined_text = re.sub(r'(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])', '', joined_text)
                joined_text = re.sub(r'\s*([，。？！；：])\s*', r'\1', joined_text)
                joined_text = re.sub(r'\s+', ' ', joined_text).strip()
                
                combined_translations[target_lang] = joined_text
            return combined_transcription, combined_translations, timeout_occurred
        else:
            # Return recognition format: (text, timeout)
            return combined_transcription, timeout_occurred
    

    def transcribe(self, audio_file_path, ori, prev_text=""):  
        """
        Perform speech-to-text transcription on the given audio file.
        
        Args:
            audio_file_path (str): Path to the audio file to transcribe
            ori (str): Language code (e.g., 'zh-TW', 'en-US') or None for auto-detection
            prev_text (str): Previous text to add as context vocabulary for better accuracy
            
        Returns:
            tuple: (transcribed_text, rtf, inference_time, detected_language)
                - transcribed_text (str): The transcribed text result
                - rtf (float): Real Time Factor (processing_time / audio_duration)
                - inference_time (float): Total processing time in seconds
                - detected_language (str): Detected or specified language code
        """
        start_time = time.time()
        language = ori  
        
        try:
            # Create speech_config dynamically for thread safety
            speech_config = speechsdk.SpeechConfig(
                subscription=self.subscription_key,
                region=self.service_region
            )
            
            # Configure extended timeout settings for longer audio files
            self._configure_timeout_settings(speech_config)
            
            # Configure custom endpoint (if available)
            if self.endpoint_id:
                speech_config.endpoint_id = self.endpoint_id
                logger.debug(f" | Using custom model with endpoint_id: {self.endpoint_id} | ")
            
            # Create audio configuration
            audio_config = speechsdk.audio.AudioConfig(filename=audio_file_path)
            
            # Create recognizer based on language specification
            if language is None or language.strip() == "":
                # Enable automatic language detection
                auto_detect_source_language_config = speechsdk.languageconfig.AutoDetectSourceLanguageConfig(
                    languages=["zh-TW", "en-US", "de-DE"])
                
                recognizer = speechsdk.SpeechRecognizer(
                    speech_config=speech_config, 
                    auto_detect_source_language_config=auto_detect_source_language_config,
                    audio_config=audio_config
                )
            else:
                # Language matching and configuration for specified language
                language = LANGUAGE_MATCH.get(language, language)
                speech_config.speech_recognition_language = language

                recognizer = speechsdk.SpeechRecognizer(
                    speech_config=speech_config,
                    audio_config=audio_config
                )
                
            logger.debug(f" | Recognizer created time: {time.time() - start_time:.2f} | ")
            
            # Apply custom vocabulary and previous text context
            self._set_dict(prev_text, recognizer)
            
            # Perform speech recognition with timeout using continuous recognition
            logger.info(f" | Starting transcription for {audio_file_path} | ")
            
            transcription_text, timeout_occurred = self._continuous_recognition_with_timeout(recognizer, "Transcription", is_translation=False)
            
            if timeout_occurred:
                return "", 0, time.time() - start_time, "unknown"
            
            # Process recognition results
            if transcription_text:
                logger.debug(f" | Transcription successful: {transcription_text} | ")
            else:
                logger.warning(f" | No speech could be recognized | ")
            
            # Calculate performance metrics
            end_time = time.time()
            inference_time = end_time - start_time
            
            # Calculate RTF (Real Time Factor) - use dummy result for continuous recognition
            dummy_result = type('Result', (), {
                'duration': None,
                'text': transcription_text
            })()
            rtf = calculate_rtf(dummy_result, audio_file_path, inference_time)

            # Extract detected language from auto-detection results (only if auto-detection was used)
            if ori is None or ori.strip() == "":
                # For continuous recognition, we need to detect language from the text
                logger.info(f" | No source language specified. Using text-based detection | ")
                # Fallback: If we have text, detect language from content
                if transcription_text:
                    # Check if text contains Chinese characters
                    has_chinese = any('\u4e00' <= char <= '\u9fff' for char in transcription_text)
                    if has_chinese:
                        language = "zh-TW"
                        logger.debug(f" | Detected Chinese characters, setting language to zh-TW | ")
                    else:
                        # Simple heuristic for other languages
                        language = "en-US"  # Default to English if no Chinese detected
                        logger.debug(f" | No Chinese characters detected, defaulting to en-US | ")
                else:
                    language = "unknown"
            else:
                # Specific language was provided, use the mapped language
                language = LANGUAGE_MATCH.get(ori, ori)
                logger.debug(f" | Used specified language: {language} (original: {ori}) | ")

            return transcription_text, rtf, inference_time, language
            
        except Exception as e:
            logger.error(f" | Transcription error: {e} | ")
            return "", 0, time.time() - start_time, "unknown"


    def translate(self, audio_file_path, ori, prev_text=""):
        """
        Perform speech-to-text translation from audio file to multiple target languages.

        Args:
            audio_file_path (str): Path to the audio file to translate
            ori (str): The source language code of the audio content
            prev_text (str): Previous text to add as context vocabulary for better accuracy
            
        Returns:
            tuple: (transcription_text, translations_dict, rtf, translation_time)
                - transcription_text (str): Original transcribed text in source language
                - translations_dict (dict): Dictionary with language codes as keys and translations as values
                - rtf (float): Real Time Factor (processing_time / audio_duration)
                - translation_time (float): Total processing time in seconds
        """  
        start_time = time.time()  
        language = ori  
        
        try:
            # Create translation_config dynamically for thread safety
            translation_config = speechsdk.translation.SpeechTranslationConfig(
                subscription=self.subscription_key,
                region=self.service_region
            )
            
            # Configure extended timeout settings for longer audio files
            self._configure_timeout_settings(translation_config)
            
            # Configure custom endpoint (if available)
            if self.endpoint_id:
                translation_config.endpoint_id = self.endpoint_id
                logger.debug(f" | Using custom model with endpoint_id: {self.endpoint_id} | ")
            
            # Create audio configuration
            audio_config = speechsdk.audio.AudioConfig(filename=audio_file_path)

            # Configure source language (must be specified for translation)
            if language:
                language = LANGUAGE_MATCH.get(language, language)
                translation_config.speech_recognition_language = language
            else:
                # Use default language if none specified
                language = "zh-TW"  
                translation_config.speech_recognition_language = language
                logger.info(f" | No source language specified, using default: {language} | ")
            
            # Configure target languages for translation
            for target_lang in LANGUAGE_LIST:
                target_lang = LANGUAGE_MATCH.get(target_lang, target_lang)
                translation_config.add_target_language(target_lang)
                
                # Special handling for Traditional Chinese variants
                if target_lang in ['zh-Hant', 'zh-TW']:
                    translation_config.set_property(
                        property_id=speechsdk.PropertyId.SpeechServiceConnection_TranslationToLanguages,
                        value="zh-Hant"
                    )

            # Create translation recognizer
            recognizer = speechsdk.translation.TranslationRecognizer(
                translation_config=translation_config,
                audio_config=audio_config
            )

            logger.debug(f" | Translation recognizer created time: {time.time() - start_time:.2f} | ")

            # Apply custom vocabulary and previous text context
            self._set_dict(prev_text, recognizer)

            # Perform translation recognition with timeout
            logger.info(f" | Starting translation for {audio_file_path} | ")
            
            # Use continuous translation for longer audio files
            transcription_text, raw_translations, timeout_occurred = self._continuous_recognition_with_timeout(recognizer, "Translation", is_translation=True)
            
            if timeout_occurred:
                return "", {}, 0, time.time() - start_time
            
            # Process translation results
            translations_text = {}
            
            if transcription_text:
                logger.debug(f" | Translation successful: {transcription_text} | ")
                
                # Convert raw translations to expected format
                for target_lang, translation in raw_translations.items():
                    match_back_language = LANGUAGE_MATCH_BACK.get(target_lang, target_lang)
                    translations_text[match_back_language] = translation
                    logger.debug(f" | {match_back_language}: {translation} | ")
            else:
                logger.warning(f" | No speech could be recognized for translation | ")
            
            # Calculate performance metrics
            end_time = time.time()
            translate_time = end_time - start_time
            
            # Calculate RTF (Real Time Factor) - use dummy result for continuous translation
            # Create a mock result object for RTF calculation with proper attributes
            dummy_result = type('Result', (), {
                'duration': None,  # Use 'duration' instead of 'audio_duration'
                'text': transcription_text
            })()
            rtf = calculate_rtf(dummy_result, audio_file_path, translate_time)

            return transcription_text, translations_text, rtf, translate_time

        except Exception as e:
            logger.error(f" | Translation error: {e} | ")
            return "", {}, 0, time.time() - start_time

    def key_test(self, subscription_key=None, service_region=None, endpoint_id=None, name=None):
        """
        Test Azure Speech Service configuration parameters for validity.
        
        Args:
            subscription_key (str): Azure Speech Service subscription key
            service_region (str): Azure service region (e.g., 'eastus', 'westus2')
            endpoint_id (str, optional): Custom model endpoint ID
            
        Returns:
            tuple: (is_valid, error_message)
                - is_valid (bool): True if configuration is valid, False otherwise
                - error_message (str): Error description if validation failed, empty if successful
        """
        error_message = ""
        is_valid = False
        
        if name is not None:
            config_path = f"./lib/{name}.json"
            if os.path.exists(config_path):
                with open(config_path, 'r') as config_file:
                    config = json.load(config_file)
                subscription_key = config.get("SubscriptionKey", subscription_key)
                service_region = config.get("ServiceRegion", service_region)
                endpoint_id = config.get("EndpointId", endpoint_id)
            else:
                error_message = "The custom model config path does not exist, please check the path."
                logger.error(f" | {error_message} | ")
                return False, error_message
        
        try:
            # Create speech_config dynamically for testing
            speech_config = speechsdk.SpeechConfig(
                subscription=subscription_key,
                region=service_region
            )
            
            # Configure custom endpoint (if provided)
            if endpoint_id is not None:
                speech_config.endpoint_id = endpoint_id
                logger.debug(f" | Testing custom model with endpoint_id: {endpoint_id} | ")

            # Create a minimal audio configuration using push stream (no hardware dependency)
            push_stream = speechsdk.audio.PushAudioInputStream()
            audio_config = speechsdk.audio.AudioConfig(stream=push_stream)
            
            # Set language for testing
            speech_config.speech_recognition_language = "en-US"
            
            # Set short timeout for quick validation
            speech_config.set_property(speechsdk.PropertyId.SpeechServiceConnection_InitialSilenceTimeoutMs, "1000")

            # Create recognizer to validate configuration
            recognizer = speechsdk.SpeechRecognizer(
                speech_config=speech_config,
                audio_config=audio_config
            )
            
            # Push a small amount of silence data to trigger connection test
            silence_data = bytes(1600)  # 100ms of 16kHz silence
            push_stream.write(silence_data)
            push_stream.close()
            
            # Test connection with recognition attempt
            result = recognizer.recognize_once()
    
            # Process test results
            if result.reason == speechsdk.ResultReason.Canceled:
                cancellation_details = result.cancellation_details
                if cancellation_details.reason == speechsdk.CancellationReason.Error:
                    error_details = cancellation_details.error_details
                    
                    # Specific error classification
                    if "401" in error_details or "Unauthorized" in error_details:
                        error_message = "Invalid subscription key"
                    elif "404" in error_details or "Not Found" in error_details:
                        error_message = "Invalid endpoint_id or service region"
                    elif "403" in error_details or "Forbidden" in error_details:
                        error_message = "Access denied or quota exceeded"
                    elif "Connection" in error_details or "timeout" in error_details.lower():
                        error_message = "Network connection issue or invalid region"
                    else:
                        error_message = f"Configuration error: {error_details}"
                    logger.error(f" | Key test failed: {error_message} | ")
                else:
                    # Non-error cancellation (e.g., no speech detected) means config is valid
                    is_valid = True
                    logger.info(" | Configuration test successful - credentials are valid | ")
            elif result.reason in [speechsdk.ResultReason.RecognizedSpeech, speechsdk.ResultReason.NoMatch]:
                # Either case means the configuration worked
                is_valid = True
                logger.info(" | Configuration test successful - credentials are valid | ")
            else:
                error_message = f"Unexpected test result: {result.reason}"
                logger.warning(f" | {error_message} | ")
            
        except Exception as e:
            error_message = f"Configuration test exception: {str(e)}"
            logger.error(f" | {error_message} | ")
            
        return is_valid, error_message