# Azure Speech Babelon Service

A FastAPI-based RESTful service that provides real-time audio transcription and translation capabilities using Azure Cognitive Services Speech API. The service supports multiple languages and offers both speech-to-text transcription and real-time translation features.

## Features

- **Audio Transcription**: Convert speech to text with language auto-detection
- **Audio Translation**: Real-time translation between multiple languages (Chinese, English, German)
- **Custom Model Support**: Support for Azure Speech custom models
- **Custom Vocabulary**: Enhance recognition accuracy with custom dictionaries
- **Performance Metrics**: Real-time factor (RTF) and processing time tracking
- **Containerized Deployment**: Docker support with CUDA acceleration
- **Automatic Cleanup**: Daily cleanup of temporary audio files

## Supported Languages

- **Chinese (Traditional)**: `zh` → `zh-TW`
- **English**: `en` → `en-US` 
- **German**: `de` → `de-DE`

## Prerequisites

### Azure Speech Service

You need to set up Azure Speech Service and obtain the following credentials:

1. **Subscription Key**: Your Azure Speech Service subscription key
2. **Service Region**: Azure region where your Speech Service is deployed (e.g., `eastus`, `westus2`)
3. **Endpoint ID** (Optional): For custom speech models

### Custom Model Configuration

To use the service, you need to create a configuration file using the `/upload_custom_model` endpoint with the following JSON format:

```json
{
  "name": "your-model-name",
  "SubscriptionKey": "your-azure-subscription-key", 
  "ServiceRegion": "your-azure-region",
  "EndpointId": "your-custom-endpoint-id"  // Optional, only needed for custom models
}
```

**Note**: The `EndpointId` field is optional and only required if you're using Azure Speech custom models. For standard Azure Speech Service, you can omit this field.

## Installation

### Using Docker (Recommended)

```bash
# Build the Docker image
docker build -t azure-speech-babelon .

# Run the container
docker run -p 80:80 -v ./logs:/app/logs azure-speech-babelon
```

### Manual Installation

```bash
# Clone the repository
git clone <repository-url>
cd Azure_Speech_Babelon

# Install dependencies
pip install -r requirements.txt

# Run the service
python main.py
```

## API Documentation

### Base URL
```
http://localhost:80
```

### Endpoints

#### 1. Health Check
```http
GET /
```
**Parameters:**
- `name` (optional): String for personalized greeting

**Response:**
```json
{
  "Hello": "World {name}"
}
```

#### 2. Upload Custom Model Configuration
```http
POST /upload_custom_model
```
**Parameters:**
- `name`: Model configuration name
- `SubscriptionKey`: Azure Speech Service subscription key
- `ServiceRegion`: Azure service region
- `EndpointId`: Custom model endpoint ID (optional)

**Response:**
```json
{
  "status": "OK",
  "message": "Custom model config saved successfully.",
  "data": null
}
```

#### 3. Check Available Models
```http
GET /check_available_models
```
**Response:**
```json
{
  "status": "OK", 
  "message": "Available models retrieved successfully.",
  "data": ["model1", "model2"]
}
```

#### 4. Check Current Model
```http
GET /check_current_model
```
**Response:**
```json
{
  "status": "OK",
  "message": "Current model: model-name",
  "data": "model-name"
}
```

#### 5. Change Custom Model
```http
POST /change_custom_model
```
**Parameters:**
- `name`: Name of the model configuration to switch to

**Response:**
```json
{
  "status": "OK",
  "message": "Custom model changed successfully.",
  "data": null
}
```

#### 6. Update Dictionary
```http
POST /update_dictionary
```
**Parameters:**
- `dictionary`: Comma-separated custom vocabulary words

**Example:**
```
dictionary=word1,word2,word3,專業術語
```

**Response:**
```json
{
  "status": "OK",
  "message": "Dictionary updated with 4 entries.",
  "data": ["word1", "word2", "word3", "專業術語"]
}
```

#### 7. Audio Transcription
```http
POST /transcription
```
**Parameters:**
- `file`: Audio file (multipart/form-data)
- `meeting_id`: Meeting identifier
- `device_id`: Device identifier  
- `audio_uid`: Unique audio segment identifier
- `times`: Timestamp (datetime format)
- `o_lang`: Original language code (optional, auto-detect if empty)
- `prev_text`: Previous text for context (optional)

**Response:**
```json
{
  "status": "OK",
  "message": "zh: 您好世界",
  "data": {
    "meeting_id": "123",
    "device_id": "123", 
    "ori_lang": "zh",
    "transcription_text": "您好世界",
    "times": "2023-10-22 10:30:00",
    "audio_uid": "123",
    "transcribe_time": 1.25
  }
}
```

#### 8. Audio Translation
```http
POST /translate
```
**Parameters:**
- `file`: Audio file (multipart/form-data)
- `meeting_id`: Meeting identifier
- `device_id`: Device identifier
- `audio_uid`: Unique audio segment identifier  
- `times`: Timestamp (datetime format)
- `o_lang`: Original language code (default: "zh")
- `prev_text`: Previous text for context (optional)

**Response:**
```json
{
  "status": "OK",
  "message": "ZH: 您好世界 | EN: Hello World | DE: Hallo Welt",
  "data": {
    "meeting_id": "123",
    "device_id": "123",
    "ori_lang": "zh", 
    "translate_text": {
      "zh": "您好世界",
      "en": "Hello World", 
      "de": "Hallo Welt"
    },
    "times": "2023-10-22 10:30:00",
    "audio_uid": "123",
    "translate_time": 2.15
  }
}
```

## Response Format

All API responses follow this structure:

```json
{
  "status": "OK|FAILED",
  "message": "Human-readable message",
  "data": "Response data or null"
}
```

## Audio File Requirements

- **Format**: WAV files are recommended
- **Sample Rate**: 16kHz preferred
- **Channels**: Mono or stereo
- **Duration**: No specific limit, but longer files may take more time to process

## Performance Metrics

The service provides performance metrics in responses:

- **RTF (Real Time Factor)**: Ratio of processing time to audio duration
- **Processing Time**: Total time taken for transcription/translation in seconds

RTF < 1.0 indicates real-time performance (faster than audio duration).

## Configuration

### Environment Variables

- `PORT`: Service port (default: 80)
- `TZ`: Timezone (default: Asia/Taipei)

### Logging

- **Log Level**: INFO
- **Log Location**: `./logs/app.log`
- **Log Rotation**: 10MB max size, 5 backup files
- **Log Format**: `%(asctime)s - %(message)s`

## Development

### Project Structure

```
├── main.py                 # FastAPI application entry point
├── requirements.txt        # Python dependencies
├── Dockerfile             # Container configuration
├── api/
│   ├── azure_speech.py    # Azure Speech Service integration
│   ├── audio_utils.py     # Audio processing utilities
│   └── utils.py           # General utilities
├── lib/
│   ├── base_object.py     # Base response models
│   ├── constant.py        # Constants and data models
│   └── [model-configs]    # Model configuration files (confidential)
├── audio/                 # Temporary audio file storage
└── logs/                  # Application logs
```

### Adding New Languages

To add support for new languages:

1. Update `LANGUAGE_LIST` in `lib/constant.py`
2. Add language mappings in `LANGUAGE_MATCH` and `LANGUAGE_MATCH_BACK`
3. Ensure Azure Speech Service supports the target language

## Troubleshooting

### Common Issues

1. **Invalid Configuration**: Verify Azure Speech Service credentials and region
2. **Audio Format Issues**: Ensure audio files are in supported formats
3. **Memory Issues**: Check available system memory for large audio files
4. **Network Issues**: Verify connectivity to Azure services

### Error Codes

- `OK`: Request processed successfully
- `FAILED`: Request failed, check error message for details

## Security Notes

- Configuration files in the `lib/` directory contain sensitive credentials
- Never commit Azure subscription keys to version control
- Use environment variables or secure vaults for production deployments
- The service automatically cleans up uploaded audio files daily

## License

[Add your license information here]

## Support

[Add your support contact information here]