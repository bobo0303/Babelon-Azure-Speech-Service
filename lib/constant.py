from pydantic import BaseModel
from typing import Dict

#############################################################################

DEFAULT_CONFIG = '/mnt/lib/Azure_Speech.json'

#############################################################################

WAITING_TIME = 10 # The whisper inference max waiting time (if over the time will stop it)

#############################################################################

class AudioTranscriptionResponse(BaseModel):
    meeting_id: str
    device_id: str
    ori_lang: str
    transcription_text: str
    times: str
    audio_uid: str
    transcribe_time: float
    
#############################################################################

class AudioTranslationResponse(BaseModel):
    meeting_id: str
    device_id: str
    ori_lang: str
    translate_text: Dict[str, str]
    times: str
    audio_uid: str
    translate_time: float
    
#############################################################################

class TextTranslationResponse(BaseModel):
    ori_lang: str
    text: Dict[str, str]
    translate_time: float

#############################################################################

# LANGUAGE_LIST = ['zh', 'en', 'ja', 'ko', "de", "es"]
LANGUAGE_LIST = ['zh', 'en', 'de']
LANGUAGE_MATCH = {"zh": "zh-TW",
                  "en": "en-US",
                  "de": "de-DE"}
LANGUAGE_MATCH_BACK = {"zh-Hant": "zh",
                       "zh-TW": "zh",
                       "en-US": "en",
                       "de-DE": "de"}
DEFAULT_RESULT = {lang: "" for lang in LANGUAGE_LIST}

#############################################################################

# no used just for reference
DEFAULT_PROMPTS = {
    "DEFAULT": "拉貨力道, 出貨力道, 放量, 換機潮, pull in, 曝險, BOM, deal, 急單, foreX, NT dollars, Monitor, china car, DSBG, low temp, Tier 2, Tier 3, Notebook, RD, TV, 8B, In-Cell Touch, Vertical, 主管, Firmware, AecoPost, DaaS, OLED, AmLED, Polarizer, Tartan Display, 達擎, ADP team, Legamaster, AVOCOR, FindARTs, RISEvision, JECTOR, SatisCtrl, Karl Storz, Schwarz, NATISIX",
    "JAMES": "GRC, DSBG, ADP, OLED, SRBG, RBU, In-cel one chip, monitor, Sports Gaming, High Frame Rate Full HD 320Hz, Kiosk, Frank, Vertical, ARHUD, 手扶屏, 空調屏, 後視鏡的屏, 達擎, 產能, 忠達.",
    "SCOTT": "JECTOR, AVOCOR, LegoMaster, RISEvision, Hualien, SatisCtrl, motherson, Kark, Storz, ADP, Aecopost, NATISIX, NanoLumens, FindARTs, AUO, ADP, AHA, E&E, Schwarz, PeosiCo."
}

#############################################################################
