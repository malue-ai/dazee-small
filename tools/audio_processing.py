"""
audio_processing — Audio processing tool for TTS, STT, and audio understanding.

Provides the main model with audio capabilities as a callable tool:
- TTS (Text-to-Speech): Convert text to audio using OpenAI/Qwen audio APIs
- STT (Speech-to-Text): Transcribe audio files using Whisper/Qwen Audio
- Understand: Analyze audio content using multimodal models
"""

import base64
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

import aiofiles

from logger import get_logger

from core.tool.types import BaseTool, ToolContext

logger = get_logger("tools.audio_processing")


class AudioProcessingTool(BaseTool):
    """
    Audio processing tool supporting TTS, STT, and audio understanding.

    Designed to be called by the main model when audio capabilities are needed,
    such as generating voice messages, transcribing audio, or understanding
    audio content.
    """

    name = "audio_processing"
    description = (
        "Audio processing: text-to-speech (TTS), speech-to-text (STT), "
        "and audio content understanding. Use for generating voice messages, "
        "transcribing audio files, or analyzing audio content."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["tts", "stt", "understand"],
                "description": (
                    "Operation type: "
                    "tts = text to speech, "
                    "stt = speech to text (transcription), "
                    "understand = audio content analysis"
                ),
            },
            "text": {
                "type": "string",
                "description": "Input text for TTS action",
            },
            "audio_url": {
                "type": "string",
                "description": "Audio file path or URL for STT/understand actions",
            },
            "voice": {
                "type": "string",
                "description": "TTS voice (optional, default depends on provider)",
            },
            "model": {
                "type": "string",
                "description": "Model to use (optional, auto-selected if not specified)",
            },
            "format": {
                "type": "string",
                "description": "Output audio format (optional, default: wav)",
                "enum": ["wav", "mp3", "opus", "aac", "flac", "pcm"],
            },
        },
        "required": ["action"],
    }
    execution_timeout = 120

    async def execute(self, params: Dict[str, Any], context: ToolContext) -> Dict[str, Any]:
        """Execute audio processing action."""
        action = params.get("action", "")

        if action == "tts":
            return await self._handle_tts(params, context)
        elif action == "stt":
            return await self._handle_stt(params, context)
        elif action == "understand":
            return await self._handle_understand(params, context)
        else:
            return {"success": False, "error": f"Unknown action: {action}"}

    async def _handle_tts(self, params: Dict[str, Any], context: ToolContext) -> Dict[str, Any]:
        """Text-to-Speech: convert text to audio file."""
        text = params.get("text", "")
        if not text:
            return {"success": False, "error": "Missing 'text' parameter for TTS"}

        voice = params.get("voice", "alloy")
        audio_format = params.get("format", "wav")
        model = params.get("model", "")

        try:
            provider, client = await self._get_tts_client(model)

            if provider == "openai":
                tts_model = model or "tts-1"
                response = await client.audio.speech.create(
                    model=tts_model,
                    voice=voice,
                    input=text,
                    response_format=audio_format,
                )
                audio_bytes = response.content

            elif provider == "qwen":
                from openai import AsyncOpenAI as QwenClient

                qwen_client = QwenClient(
                    api_key=os.getenv("DASHSCOPE_API_KEY", ""),
                    base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
                )
                tts_model = model or "qwen-omni-turbo"
                qwen_voice = voice if voice != "alloy" else "Cherry"

                response = await qwen_client.chat.completions.create(
                    model=tts_model,
                    messages=[{"role": "user", "content": [{"type": "text", "text": text}]}],
                    modalities=["text", "audio"],
                    audio={"voice": qwen_voice, "format": audio_format},
                    stream=True,
                )

                audio_data_chunks = []
                async for chunk in response:
                    if chunk.choices:
                        delta = chunk.choices[0].delta
                        if hasattr(delta, "audio") and delta.audio:
                            data = getattr(delta.audio, "data", None)
                            if data:
                                audio_data_chunks.append(data)

                if audio_data_chunks:
                    full_b64 = "".join(audio_data_chunks)
                    audio_bytes = base64.b64decode(full_b64)
                else:
                    return {"success": False, "error": "Qwen TTS returned no audio data"}
            else:
                return {"success": False, "error": f"Unsupported TTS provider: {provider}"}

            file_path = await self._save_audio_file(
                audio_bytes, audio_format, context
            )

            return {
                "success": True,
                "file_path": str(file_path),
                "format": audio_format,
                "size_bytes": len(audio_bytes),
                "message": f"Audio generated ({len(audio_bytes)} bytes), saved to {file_path}",
            }

        except Exception as e:
            logger.error(f"TTS failed: {e}", exc_info=True)
            return {"success": False, "error": f"TTS failed: {str(e)}"}

    async def _handle_stt(self, params: Dict[str, Any], context: ToolContext) -> Dict[str, Any]:
        """Speech-to-Text: transcribe audio file."""
        audio_url = params.get("audio_url", "")
        if not audio_url:
            return {"success": False, "error": "Missing 'audio_url' parameter for STT"}

        model = params.get("model", "")

        try:
            audio_path = Path(audio_url)
            if not audio_path.exists():
                return {"success": False, "error": f"Audio file not found: {audio_url}"}

            provider, client = await self._get_stt_client(model)

            if provider == "openai":
                stt_model = model or "whisper-1"
                with open(audio_path, "rb") as f:
                    transcript = await client.audio.transcriptions.create(
                        model=stt_model,
                        file=f,
                    )
                text = transcript.text

            elif provider == "qwen":
                audio_bytes = audio_path.read_bytes()
                b64_data = base64.standard_b64encode(audio_bytes).decode("utf-8")
                audio_format = audio_path.suffix.lstrip(".")

                from openai import AsyncOpenAI as QwenClient

                qwen_client = QwenClient(
                    api_key=os.getenv("DASHSCOPE_API_KEY", ""),
                    base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
                )
                stt_model = model or "qwen-audio-turbo"

                response = await qwen_client.chat.completions.create(
                    model=stt_model,
                    messages=[{
                        "role": "user",
                        "content": [
                            {
                                "type": "input_audio",
                                "input_audio": {
                                    "data": b64_data,
                                    "format": audio_format or "wav",
                                },
                            },
                            {
                                "type": "text",
                                "text": "Please transcribe this audio accurately.",
                            },
                        ],
                    }],
                )
                text = response.choices[0].message.content or ""
            else:
                return {"success": False, "error": f"Unsupported STT provider: {provider}"}

            return {
                "success": True,
                "transcript": text,
                "audio_file": str(audio_url),
                "message": f"Transcription complete ({len(text)} characters)",
            }

        except Exception as e:
            logger.error(f"STT failed: {e}", exc_info=True)
            return {"success": False, "error": f"STT failed: {str(e)}"}

    async def _handle_understand(
        self, params: Dict[str, Any], context: ToolContext
    ) -> Dict[str, Any]:
        """Audio understanding: analyze audio content with a multimodal model."""
        audio_url = params.get("audio_url", "")
        if not audio_url:
            return {"success": False, "error": "Missing 'audio_url' parameter for understand"}

        model = params.get("model", "")

        try:
            audio_path = Path(audio_url)
            if not audio_path.exists():
                return {"success": False, "error": f"Audio file not found: {audio_url}"}

            audio_bytes = audio_path.read_bytes()
            b64_data = base64.standard_b64encode(audio_bytes).decode("utf-8")
            audio_format = audio_path.suffix.lstrip(".")

            provider, client = await self._get_audio_understand_client(model)

            if provider == "openai":
                understand_model = model or "gpt-4o-audio-preview"
                response = await client.chat.completions.create(
                    model=understand_model,
                    modalities=["text"],
                    messages=[{
                        "role": "user",
                        "content": [
                            {
                                "type": "input_audio",
                                "input_audio": {
                                    "data": b64_data,
                                    "format": audio_format or "wav",
                                },
                            },
                            {
                                "type": "text",
                                "text": (
                                    "Analyze this audio. Describe its content, "
                                    "including speech content, tone, background sounds, "
                                    "and any other notable characteristics."
                                ),
                            },
                        ],
                    }],
                )
                analysis = response.choices[0].message.content or ""

            elif provider == "qwen":
                from openai import AsyncOpenAI as QwenClient

                qwen_client = QwenClient(
                    api_key=os.getenv("DASHSCOPE_API_KEY", ""),
                    base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
                )
                understand_model = model or "qwen-omni-turbo"

                accumulated = ""
                response = await qwen_client.chat.completions.create(
                    model=understand_model,
                    messages=[{
                        "role": "user",
                        "content": [
                            {
                                "type": "input_audio",
                                "input_audio": {
                                    "data": b64_data,
                                    "format": audio_format or "wav",
                                },
                            },
                            {
                                "type": "text",
                                "text": (
                                    "Analyze this audio. Describe its content, "
                                    "including speech content, tone, background sounds, "
                                    "and any other notable characteristics."
                                ),
                            },
                        ],
                    }],
                    modalities=["text"],
                    stream=True,
                )
                async for chunk in response:
                    if chunk.choices and chunk.choices[0].delta.content:
                        accumulated += chunk.choices[0].delta.content
                analysis = accumulated
            else:
                return {
                    "success": False,
                    "error": f"Unsupported audio understanding provider: {provider}",
                }

            return {
                "success": True,
                "analysis": analysis,
                "audio_file": str(audio_url),
                "message": f"Audio analysis complete ({len(analysis)} characters)",
            }

        except Exception as e:
            logger.error(f"Audio understanding failed: {e}", exc_info=True)
            return {"success": False, "error": f"Audio understanding failed: {str(e)}"}

    async def _get_tts_client(self, model: str = "") -> tuple:
        """Get appropriate TTS client based on model or available API keys."""
        return await self._get_audio_client(model, prefer_openai_model="tts-1")

    async def _get_stt_client(self, model: str = "") -> tuple:
        """Get appropriate STT client based on model or available API keys."""
        return await self._get_audio_client(model, prefer_openai_model="whisper-1")

    async def _get_audio_understand_client(self, model: str = "") -> tuple:
        """Get appropriate audio understanding client."""
        return await self._get_audio_client(model, prefer_openai_model="gpt-4o-audio-preview")

    async def _get_audio_client(
        self, model: str = "", prefer_openai_model: str = ""
    ) -> tuple:
        """
        Determine provider and create client based on model name or available keys.

        Returns:
            (provider_name, client) tuple
        """
        qwen_models = {"qwen-omni-turbo", "qwen3-omni-flash", "qwen-audio-turbo"}

        if model and any(m in model for m in qwen_models):
            from openai import AsyncOpenAI

            return "qwen", AsyncOpenAI(
                api_key=os.getenv("DASHSCOPE_API_KEY", ""),
                base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
            )

        openai_key = os.getenv("OPENAI_API_KEY", "")
        dashscope_key = os.getenv("DASHSCOPE_API_KEY", "")

        if openai_key:
            from openai import AsyncOpenAI

            return "openai", AsyncOpenAI(api_key=openai_key)

        if dashscope_key:
            from openai import AsyncOpenAI

            return "qwen", AsyncOpenAI(
                api_key=dashscope_key,
                base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
            )

        return "openai", None

    async def _save_audio_file(
        self,
        audio_bytes: bytes,
        audio_format: str,
        context: ToolContext,
    ) -> Path:
        """Save audio bytes to a file in the instance storage directory."""
        from utils.app_paths import get_storage_dir

        output_dir = get_storage_dir() / "audio_output"
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = int(time.time() * 1000)
        filename = f"audio_{timestamp}.{audio_format}"
        file_path = output_dir / filename

        async with aiofiles.open(file_path, "wb") as f:
            await f.write(audio_bytes)

        logger.info(f"🎵 Audio saved: {file_path} ({len(audio_bytes)} bytes)")
        return file_path
