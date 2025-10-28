from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, File, Form
import os  
import time  
import pytz  
import logging  
import uvicorn  
import datetime  
from threading import Thread, Event  
from api.azure_speech import AzureSpeechModel  
from lib.base_object import BaseResponse, Status
from lib.constant import AudioTranscriptionResponse, AudioTranslationResponse, LANGUAGE_LIST, DEFAULT_RESULT
from api.utils import write_txt

if not os.path.exists("./audio"):  
    os.mkdir("./audio")  
if not os.path.exists("./logs"):  
    os.mkdir("./logs")  
    
# Configure logging  
log_format = "%(asctime)s - %(message)s"  # Output timestamp and message content  
log_file = "logs/app.log"  
logging.basicConfig(level=logging.INFO, format=log_format)  
  
# Create a file handler  
file_handler = logging.handlers.RotatingFileHandler(  
    log_file, maxBytes=10*1024*1024, backupCount=5  
)  
file_handler.setFormatter(logging.Formatter(log_format))  
  
# Create a console handler  
console_handler = logging.StreamHandler()  
console_handler.setFormatter(logging.Formatter(log_format))  
  
logger = logging.getLogger(__name__)  
logger.setLevel(logging.INFO)  # Ensure logger level is set to INFO or lower  
  
# Clear existing handlers to prevent duplicate logs  
if not logger.handlers:  
    logger.addHandler(file_handler)  
    logger.addHandler(console_handler)  # Add console handler 

logger.propagate = False  
  
# Configure UTC+8 time  
utc_now = datetime.datetime.now(pytz.utc)  
tz = pytz.timezone('Asia/Taipei')  
local_now = utc_now.astimezone(tz)  
  
model = AzureSpeechModel()  
waiting_list = []
sse_stop_event = Event()  # Global event to control SSE connection
service_stop_event = Event()  

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler for startup and shutdown events.
    """
    # Startup
    logger.info(f" | ##################################################### | ")  
    logger.info(f" | Azure Speech Babelon Service Starting... | ")
    logger.info(f" | ##################################################### | ")  
    
    try:
        # Initialize and validate Azure Speech Model
        logger.info(f" | Initializing Azure Speech Model... | ")
        if model.subscription_key is None or model.service_region is None:
            logger.error(f" | Azure Speech configuration is incomplete! | ")
            raise ValueError("Azure Speech configuration is incomplete")
        
        # Test model configuration
        logger.info(f" | Testing Azure Speech configuration... | ")
        is_valid, error_msg = model.key_test(
            model.subscription_key, 
            model.service_region, 
            model.endpoint_id
        )
        if not is_valid:
            logger.error(f" | Azure Speech configuration test failed: {error_msg} | ")
            raise ValueError(f"Azure Speech configuration invalid: {error_msg}")
        
        logger.info(f" | Azure Speech Model initialized successfully | ")
        logger.info(f" | Model: {model.model_version} | Region: {model.service_region} | ")
        
        # Clean up old audio files
        logger.info(f" | Cleaning up old audio files... | ")
        delete_old_audio_files()
        
        # Start daily task scheduling  
        logger.info(f" | Starting background task scheduler... | ")
        task_thread = Thread(target=schedule_daily_task, args=(service_stop_event,))  
        task_thread.daemon = True  # Make it a daemon thread for proper cleanup
        task_thread.start()
        
        logger.info(f" | ##################################################### | ")  
        logger.info(f" | Azure Speech Babelon Service Started Successfully! | ")
        logger.info(f" | ##################################################### | ")  
        
    except Exception as e:
        logger.error(f" | Failed to start service: {e} | ")
        raise  # Re-raise to prevent service from starting
    
    yield  # Application starts receiving requests
    
    # Shutdown
    logger.info(f" | ##################################################### | ")  
    logger.info(f" | Azure Speech Babelon Service Shutting Down... | ")
    logger.info(f" | ##################################################### | ")  
    
    try:
        # Stop background tasks
        logger.info(f" | Stopping background tasks... | ")
        service_stop_event.set()  
        
        # Wait for background thread to finish (with timeout)
        if task_thread.is_alive():
            task_thread.join(timeout=5.0)  # 5 second timeout
            if task_thread.is_alive():
                logger.warning(f" | Background task did not stop gracefully | ")
        
        # Stop any running SSE connections
        logger.info(f" | Stopping SSE connections... | ")
        sse_stop_event.set()
        
        # Clean up model resources if needed
        if hasattr(model, 'close'):
            logger.info(f" | Cleaning up model resources... | ")
            model.close()
        
        # Final cleanup of temporary files
        logger.info(f" | Performing final cleanup... | ")
        delete_old_audio_files()
        
        logger.info(f" | ##################################################### | ")  
        logger.info(f" | Azure Speech Babelon Service Stopped Successfully! | ")
        logger.info(f" | ##################################################### | ")  
        
    except Exception as e:
        logger.error(f" | Error during shutdown: {e} | ")

app = FastAPI(lifespan=lifespan)

##############################################################################  

@app.get("/")  
def HelloWorld(name:str=None):  
    return {"Hello": f"World {name}"}  

##############################################################################  

@app.post("/update_dictionary")
async def update_dictionary(dictionary: str = Form(...)):
    """
    Update dictionary with comma-separated words.
    Input: "a,b, c,d,e" -> Output: ["a", "b", "c", "d", "e"]
    """
    if not dictionary.strip():
        # Clear dictionary if empty string
        model.update_dict([])
        logger.info(f" | Dictionary has been cleared. | ")
        return BaseResponse(message=" | Dictionary has been cleared. | ", data=[])

    # Split by comma and clean up each word
    words = [word.strip() for word in dictionary.split(',')]
    # Remove empty strings
    words = [word for word in words if word]
    
    logger.info(f" | Input dictionary string: {dictionary} | ")
    logger.info(f" | Processed dictionary list: {words} | ")
    
    # Update model dictionary
    model.update_dict(words)
    logger.info(f" | Dictionary updated with {len(words)} entries. | ")
    
    return BaseResponse(message=f" | Dictionary updated with {len(words)} entries. | ", data=words)

@app.get("/check_available_models")
async def check_available_models():
    """
    Check available models.
    """
    available_models = os.listdir("./lib")
    available_models = [model_name.replace(".json", "") for model_name in available_models if model_name.endswith(".json")]
    logger.info(f" | Available models: {available_models} | ")
    return BaseResponse(message=f" | Available models retrieved successfully. | '{available_models}' | ", data=available_models)

@app.get("/check_current_model")
async def check_current_model():
    """
    Check the current model configuration.
    """
    if model.model_version is None:
        return BaseResponse(status=Status.FAILED, message=" | No model is currently loaded. | ", data=None)
    else:
        logger.info(f" | Current model: {model.model_version} | ")
        return BaseResponse(message=f" | Current model: {model.model_version} | ", data=model.model_version)

@app.post("/change_custom_model")
async def change_custom_model(name: str = Form(...)):
    """
    Change the custom model configuration.
    """
    config_path = f"./lib/{name}.json"
    if not os.path.exists(config_path):
        return BaseResponse(status=Status.FAILED, message=" | The custom model config path does not exist, please check the path. | ", data=None)

    valid, _ = model.key_test(name=name)
    if valid:
        if model.change_custom_model(config_path):
            return BaseResponse(message=" | Custom model changed successfully. | ", data=None)
    else:
        return BaseResponse(status=Status.FAILED, message=" | Failed to change model configuration. Return to original version. | ", data=None)

@app.post("/upload_custom_model")
async def upload_custom_model(name: str = Form(...),
                              SubscriptionKey: str = Form(...), 
                              ServiceRegion: str = Form(...), 
                              EndpointId: str = Form(...)):
    """
    Upload a custom model for Azure Speech Service.
    """
    if not SubscriptionKey or not ServiceRegion:
        return BaseResponse(status=Status.FAILED, message=" | SubscriptionKey and ServiceRegion are required. | ", data=None)

    valid, message = model.key_test(SubscriptionKey, ServiceRegion, EndpointId)
    
    if valid:
        config_path = f"./lib/{name}.json"
        if EndpointId is None:
            open(config_path, 'w').write(f'{{"name": "{name}", \n"SubscriptionKey": "{SubscriptionKey}", \n"ServiceRegion": "{ServiceRegion}"}}')
        else:
            open(config_path, 'w').write(f'{{"name": "{name}", \n"SubscriptionKey": "{SubscriptionKey}", \n"ServiceRegion": "{ServiceRegion}", \n"EndpointId": "{EndpointId}"}}')
        return BaseResponse(message=f" | Custom model config saved successfully. | ", data=None)
    else:
        return BaseResponse(status=Status.FAILED, message=f" | Upload failed | {message} | ", data=None)
    

@app.post("/transcription")
async def transcription(
    file: UploadFile = File(...),  
    meeting_id: str = Form(123),  
    device_id: str = Form(123),  
    audio_uid: str = Form(123),  
    times: datetime.datetime = Form(...),  
    o_lang: str = Form(""),  
    prev_text: str = Form(""),
):  
    
    # Convert times to string format  
    times = str(times)  
    # Convert original language to lowercase  
    if o_lang is not None:
        o_lang = o_lang.lower()  
    
    # Create response data structure  
    response_data = AudioTranscriptionResponse(  
        meeting_id=meeting_id,  
        device_id=device_id,  
        ori_lang=o_lang,  
        transcription_text="",
        times=str(times),  
        audio_uid=audio_uid,  
        transcribe_time=0.0,  
    )  
  
    # Save the uploaded audio file  
    file_name = times + ".wav"  
    audio_buffer = f"audio/{file_name}"  
    with open(audio_buffer, 'wb') as f:  
        f.write(file.file.read())  
  
    # Check if the audio file exists  
    if not os.path.exists(audio_buffer):  
        return BaseResponse(status=Status.FAILED, message=" | The audio file does not exist, please check the audio path. | ", data=response_data)  
  
    # Check if the model has been loaded  
    if model.model_version is None:  
        return BaseResponse(status=Status.FAILED, message=" | model haven't been load successfully. may out of memory please check again | ", data=response_data)  

    # Check if the languages are in the supported language list  
    if o_lang not in LANGUAGE_LIST and o_lang is not None and o_lang != "":  
        logger.info(f" | The original language is not in LANGUAGE_LIST: {LANGUAGE_LIST}. | ")  
        return BaseResponse(status=Status.FAILED, message=f" | The original language is not in LANGUAGE_LIST: {LANGUAGE_LIST}. | ", data=response_data)  
  
    try:  
        # main transcription process
        transcription_text, rtf, transcription_time, language = model.transcribe(audio_buffer, o_lang, prev_text=prev_text)
        
        # Remove the audio buffer file  
        if os.path.exists(audio_buffer):
            os.remove(audio_buffer)  
  
        # Get the result from the queue  
        response_data.transcription_text = transcription_text
        response_data.transcribe_time = transcription_time  

        logger.debug(response_data.model_dump_json())  
        logger.info(f" | device_id: {response_data.device_id} | audio_uid: {response_data.audio_uid} | language: {language} | ")  
        logger.info(f" | Transcription: {transcription_text} | ")
        logger.info(f" | RTF: {rtf:.2f} | transcribe time: {transcription_time:.2f} seconds. |")  
        state = Status.OK
        
        if transcription_text == "" and rtf == 0 and language == "unknown":
            state = Status.FAILED

        return BaseResponse(status=state, message=f" | {language}: {response_data.transcription_text} | ", data=response_data)  
    except Exception as e:  
        logger.error(f" | Transcription() error: {e} | ")  
        return BaseResponse(status=Status.FAILED, message=f" | Transcription() error: {e} | ", data=response_data)  
    
    
@app.post("/translate")
async def translate(
    file: UploadFile = File(...),  
    meeting_id: str = Form(123),  
    device_id: str = Form(123),  
    audio_uid: str = Form(123),  
    times: datetime.datetime = Form(...),  
    o_lang: str = Form("zh"),  
    prev_text: str = Form(""),
):  
    """  
    Transcribe and translate an audio file.  
      
    This endpoint receives an audio file and its associated metadata, and  
    performs transcription and translation on the audio file.  
      
    :param file: UploadFile  
        The audio file to be transcribed.  
    :param meeting_id: str  
        The ID of the meeting.  
    :param device_id: str  
        The ID of the device.  
    :param audio_uid: str  
        The unique ID of the audio.  
    :param times: datetime.datetime  
        The start time of the audio.  
    :param o_lang: str  
        The original language of the audio.  
    :param prev_text: str
        The previous text for context (will be overridden by global previous translation)
    :rtype: BaseResponse  
        A response containing the transcription results.  
    """  
    
    # Convert times to string format  
    times = str(times)  
    # Convert original language and target language to lowercase  
    o_lang = o_lang.lower()  
    
    # Create response data structure  
    response_data = AudioTranslationResponse(  
        meeting_id=meeting_id,  
        device_id=device_id,  
        ori_lang=o_lang,  
        translate_text=DEFAULT_RESULT.copy(),  
        times=str(times),  
        audio_uid=audio_uid,  
        translate_time=0.0,  
    )  
  
    # Save the uploaded audio file  
    file_name = times + ".wav"  
    audio_buffer = f"audio/{file_name}"  
    with open(audio_buffer, 'wb') as f:  
        f.write(file.file.read())  
  
    # Check if the audio file exists  
    if not os.path.exists(audio_buffer):  
        return BaseResponse(status=Status.FAILED, message=" | The audio file does not exist, please check the audio path. | ", data=response_data)  
  
    # Check if the model has been loaded  
    if model.model_version is None:  
        return BaseResponse(status=Status.FAILED, message=" | model haven't been load successfully. may out of memory please check again | ", data=response_data)  
  
    # Check if the languages are in the supported language list  
    if o_lang not in LANGUAGE_LIST:  
        logger.info(f" | The original language is not in LANGUAGE_LIST: {LANGUAGE_LIST}. | ")  
        return BaseResponse(status=Status.FAILED, message=f" | The original language is not in LANGUAGE_LIST: {LANGUAGE_LIST}. | ", data=response_data)  
  
    try:  
        # main translation process
        transcription_text, translated_text, rtf, translate_time = model.translate(audio_buffer, o_lang, prev_text=prev_text)    
  
        # Remove the audio buffer file  
        if os.path.exists(audio_buffer):
            os.remove(audio_buffer)  
  
        # Get the result 
        if translated_text is {}:
            response_data.translate_text[o_lang] = transcription_text
        else:
            response_data.translate_text = translated_text
        response_data.translate_time = translate_time
        zh_text = response_data.translate_text.get("zh", "")
        en_text = response_data.translate_text.get("en", "")
        de_text = response_data.translate_text.get("de", "")

        logger.debug(response_data.model_dump_json())  
        logger.info(f" | device_id: {response_data.device_id} | audio_uid: {response_data.audio_uid} | original language: {o_lang} |")  
        logger.info(f" | {'#' * 75} | ")
        logger.info(f" | ZH: {zh_text} | ")  
        logger.info(f" | EN: {en_text} | ")  
        logger.info(f" | DE: {de_text} | ")  
        logger.info(f" | {'#' * 75} | ")
        logger.info(f" | RTF: {rtf:.2f} | translate time: {translate_time:.2f} seconds. | ")  
        state = Status.OK

        if transcription_text == "" and translated_text is {} and rtf == 0:
            state = Status.FAILED

        # write_txt(zh_text, en_text, de_text, meeting_id, audio_uid, times)
        return BaseResponse(status=state, message=f" | ZH: {zh_text} | EN: {en_text} | DE: {de_text} | ", data=response_data)  
    except Exception as e:  
        logger.error(f" | translate() error: {e} | ")  
        return BaseResponse(status=Status.FAILED, message=f" | translate() error: {e} | ", data=response_data)  


##############################################################################

# Clean up audio files  
def delete_old_audio_files():  
    """  
    The process of deleting old audio files  
    :param  
    ----------  
    None: The function does not take any parameters  
    :rtype  
    ----------  
    None: The function does not return any value  
    :logs  
    ----------  
    Deleted old files  
    """  
    current_time = time.time()  
    audio_dir = "./audio"  
    for filename in os.listdir(audio_dir):  
        if filename == "test.wav":  # Skip specific file  
            continue  
        file_path = os.path.join(audio_dir, filename)  
        if os.path.isfile(file_path):  
            file_creation_time = os.path.getctime(file_path)  
            # Delete files older than a day  
            if current_time - file_creation_time > 24 * 60 * 60:  
                os.remove(file_path)  
                logger.info(f" | Deleted old file: {file_path} | ")  
                
    config_path = "./lib"
    for filename in os.listdir(config_path):
        if filename.endswith(".json"):
            file_path = os.path.join(config_path, filename)  
            if os.path.isfile(file_path):  
                file_creation_time = os.path.getctime(file_path)  
                # Delete files older than 30 days  
                if current_time - file_creation_time > 30 * 24 * 60 * 60:  
                    os.remove(file_path)  
                    logger.info(f" | Deleted old config: {file_path} | ")

# Daily task scheduling  
def schedule_daily_task(stop_event):  
    """
    Background task that runs daily cleanup operations.
    """
    logger.info(f" | Daily task scheduler started | ")
    last_cleanup_day = None
    
    while not stop_event.is_set():  
        try:
            # Get current time in local timezone
            utc_now = datetime.datetime.now(pytz.utc)  
            tz = pytz.timezone('Asia/Taipei')  
            current_local_time = utc_now.astimezone(tz)
            current_day = current_local_time.date()
            
            # Check if it's midnight (00:00-00:01) and we haven't cleaned today
            if (current_local_time.hour == 0 and 
                current_local_time.minute == 0 and 
                last_cleanup_day != current_day):
                
                logger.info(f" | Running daily cleanup task... | ")
                delete_old_audio_files()  
                last_cleanup_day = current_day
                logger.info(f" | Daily cleanup completed | ")
                
                # Sleep for 60 seconds to prevent multiple triggers
                if not stop_event.wait(60):
                    continue
                    
            # Check every 30 seconds
            if stop_event.wait(30):
                break
                
        except Exception as e:
            logger.error(f" | Error in daily task scheduler: {e} | ")
            # Wait a bit before retrying
            if stop_event.wait(60):
                break
    
    logger.info(f" | Daily task scheduler stopped | ")  
  
if __name__ == "__main__":  
    port = int(os.environ.get("PORT", 80))  
    uvicorn.config.LOGGING_CONFIG["formatters"]["default"]["fmt"] = "%(asctime)s [%(name)s] %(levelprefix)s %(message)s"  
    uvicorn.config.LOGGING_CONFIG["formatters"]["access"]["fmt"] = '%(asctime)s [%(name)s] %(levelprefix)s %(client_addr)s - "%(request_line)s" %(status_code)s'  
    uvicorn.run(app, log_level='info', host='0.0.0.0', port=port)   
    
    
 