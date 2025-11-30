#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""
Valós idejű előadás átírás
===========================

Ez a példa bemutatja, hogyan lehet valós időben átírni egy előadást (hang → szöveg).
Az átírt szöveg megjelenik a böngésző felületén.

Használat:
    python examples/foundational/49-realtime-lecture-qa.py

Szükséges környezeti változók:
- GOOGLE_TEST_CREDENTIALS: Google Cloud credentials (STT-hez)
"""

import os

from dotenv import load_dotenv
from loguru import logger
import time
import aiohttp

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import (
    Frame,
    OutputTransportMessageFrame,
    UserTextFrame,
    TranscriptionFrame,
    TranscriptionUpdateFrame,
    TranscriptionMessage,
    ErrorFrame,
    TextFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.google.stt import GoogleSTTService
from pipecat.transcriptions.language import Language
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.transports.daily.transport import DailyParams
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams

load_dotenv(override=True)


async def start_confai_transcription(task: PipelineTask) -> str | None:
    """Start a remote transcription session at confai and notify UI.

    Returns the `session_id` on success or `None` on failure. On failure
    this helper will also queue error frames to the pipeline and cancel the
    given `task`.
    """
    url = "https://confai.telekom.hu/api/transcription/start"
    timestamp = int(time.time())
    payload = {
        "filename": f"2026-konferencia-{timestamp}",
        "source_identifier": "2026-konferencia",
    }

    confai_key = os.getenv("CONFAI_API_KEY")
    if confai_key:
        headers = {"X-Admin-Key": confai_key}
    else:
        headers = {}
        logger.warning("CONFAI_API_KEY not set — POSTing without X-Admin-Key header")

    try:
        async with aiohttp.ClientSession() as http:
            resp = await http.post(url, json=payload, headers=headers)
            if resp.status != 200:
                err_text = f"Failed to start remote transcription session: HTTP {resp.status}"
                logger.error(err_text)
                try:
                    ui_err = OutputTransportMessageFrame(message={"text": err_text, "type": "error"})
                    await task.queue_frame(ui_err)
                    ui_user_err = UserTextFrame(text=err_text)
                    await task.queue_frame(ui_user_err)
                    await task.queue_frame(ErrorFrame(error=err_text, fatal=True))
                except Exception:
                    logger.exception("Failed to queue error frames")
                await task.cancel()
                return None

            body = await resp.json()
            session_id = body.get("session_id")
            if session_id:
                task._remote_transcription = {"session_id": session_id, "raw": body}
                logger.info(f"Started remote transcription session: {session_id}")
                try:
                    info_text = f"Kapcsolat létrejött a https://confai.telekom.hu/ szolgáltatással. session_id: {session_id}"
                    info_msg = OutputTransportMessageFrame(message={"text": info_text, "type": "chat"})
                    logger.info(f"📤 OutputTransportMessageFrame küldése (session info): {info_text}")
                    await task.queue_frame(info_msg)

                    info_user = UserTextFrame(text=info_text)
                    logger.info(f"📤 UserTextFrame küldése (session info): {info_text}")
                    await task.queue_frame(info_user)
                except Exception:
                    logger.exception("Failed to queue session info frames")
                return session_id
            else:
                err_text = f"Remote transcription start returned no session_id: {body}"
                logger.error(err_text)
                try:
                    ui_err = OutputTransportMessageFrame(message={"text": err_text, "type": "error"})
                    await task.queue_frame(ui_err)
                    ui_user_err = UserTextFrame(text=err_text)
                    await task.queue_frame(ui_user_err)
                    await task.queue_frame(ErrorFrame(error=err_text, fatal=True))
                except Exception:
                    logger.exception("Failed to queue error frames")
                await task.cancel()
                return None
    except Exception as e:
        err_text = f"Error starting remote transcription session: {e}"
        logger.exception(err_text)
        try:
            ui_err = OutputTransportMessageFrame(message={"text": err_text, "type": "error"})
            await task.queue_frame(ui_err)
            ui_user_err = UserTextFrame(text=err_text)
            await task.queue_frame(ui_user_err)
            await task.queue_frame(ErrorFrame(error=err_text, fatal=True))
        except Exception:
            logger.exception("Failed to queue error frames")
        await task.cancel()
        return None


async def finalize_confai_transcription(task: PipelineTask) -> bool:
    """Finalize a remote transcription session at confai using saved session_id.

    Posts {"session_id": "..."} to the finalize endpoint with X-Admin-Key header.
    Returns True on success, False otherwise. Not fatal — used during disconnect.
    """
    if not hasattr(task, "_remote_transcription") or not task._remote_transcription:
        logger.warning("No remote transcription session stored on task; nothing to finalize")
        return False

    session_id = task._remote_transcription.get("session_id")
    if not session_id:
        logger.warning("Remote transcription session info missing session_id; nothing to finalize")
        return False

    url = "https://confai.telekom.hu/api/transcription/finalize"
    payload = {"session_id": session_id}
    confai_key = os.getenv("CONFAI_API_KEY")
    headers = {"X-Admin-Key": confai_key} if confai_key else {}

    try:
        async with aiohttp.ClientSession() as http:
            resp = await http.post(url, json=payload, headers=headers)
            if resp.status != 200:
                err_text = f"Failed to finalize remote transcription session: HTTP {resp.status}"
                logger.error(err_text)
                try:
                    ui_err = OutputTransportMessageFrame(message={"text": err_text, "type": "error"})
                    await task.queue_frame(ui_err)
                    ui_user_err = UserTextFrame(text=err_text)
                    await task.queue_frame(ui_user_err)
                except Exception:
                    logger.exception("Failed to queue finalize error frames")
                return False

            body = await resp.json()
            logger.info(f"Finalized remote transcription session {session_id}: {body}")
            try:
                info_text = f"A távoli átírás befejeződött. session_id: {session_id}"
                info_msg = OutputTransportMessageFrame(message={"text": info_text, "type": "chat"})
                await task.queue_frame(info_msg)
                info_user = UserTextFrame(text=info_text)
                await task.queue_frame(info_user)
            except Exception:
                logger.exception("Failed to queue finalize info frames")
            return True
    except Exception as e:
        err_text = f"Error finalizing remote transcription session: {e}"
        logger.exception(err_text)
        try:
            ui_err = OutputTransportMessageFrame(message={"text": err_text, "type": "error"})
            await task.queue_frame(ui_err)
            ui_user_err = UserTextFrame(text=err_text)
            await task.queue_frame(ui_user_err)
        except Exception:
            logger.exception("Failed to queue finalize exception frames")
        return False


async def append_confai_transcription(task: PipelineTask, content: str) -> bool:
    """Append a piece of transcribed content to the remote confai session.

    Posts {"session_id": "...", "content": "..."} to the append endpoint.
    Returns True on success, False otherwise.
    """
    if not hasattr(task, "_remote_transcription") or not task._remote_transcription:
        logger.debug("No remote transcription session stored on task; skipping append")
        return False

    session_id = task._remote_transcription.get("session_id")
    if not session_id:
        logger.debug("Remote transcription session missing session_id; skipping append")
        return False

    url = "https://confai.telekom.hu/api/transcription/append"
    payload = {"session_id": session_id, "content": content}
    confai_key = os.getenv("CONFAI_API_KEY")
    headers = {"X-Admin-Key": confai_key} if confai_key else {}

    try:
        async with aiohttp.ClientSession() as http:
            resp = await http.post(url, json=payload, headers=headers)
            if resp.status != 200:
                err_text = f"Failed to append to remote transcription session: HTTP {resp.status}"
                logger.error(err_text)
                try:
                    ui_err = OutputTransportMessageFrame(message={"text": err_text, "type": "error"})
                    await task.queue_frame(ui_err)
                except Exception:
                    logger.exception("Failed to queue append error frame")
                return False

            body = await resp.json()
            logger.debug(f"Appended content to session {session_id}: {body}")
            return True
    except Exception as e:
        err_text = f"Error appending to remote transcription session: {e}"
        logger.exception(err_text)
        try:
            ui_err = OutputTransportMessageFrame(message={"text": err_text, "type": "error"})
            await task.queue_frame(ui_err)
        except Exception:
            logger.exception("Failed to queue append exception frame")
        return False



class TranscriptDisplayProcessor(FrameProcessor):
    """Elküldi a transzkripciókat a WebRTC felületre."""
    
    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
                
        # TranscriptionFrame közvetlenül az STT-től
        if isinstance(frame, TranscriptionFrame):
            # Formázott szöveg a felületre
            text = f"🎤 {frame.text}"
            
            logger.info(f"✅ TranscriptionFrame észlelve: {frame.text}")
            
            # OutputTransportMessageFrame küldése a böngésző felületére
            message_frame = OutputTransportMessageFrame(message={"text": text, "type": "chat"})
            logger.info(f"📤 OutputTransportMessageFrame küldése: {text}")
            await self.push_frame(message_frame, FrameDirection.DOWNSTREAM)
            
            user_frame = UserTextFrame(text=text)
            logger.info(f"📤 UserTextFrame küldése: {text}")
            await self.push_frame(user_frame, FrameDirection.DOWNSTREAM)
            # Append the raw transcribed content to remote confai session if available
            try:
                if hasattr(self, "_task") and self._task:
                    # Send the raw transcription text (without emoji prefix)
                    await append_confai_transcription(self._task, frame.text)
                else:
                    logger.debug("‼️ No task attached to TranscriptDisplayProcessor; skipping confai append")
            except Exception:
                logger.exception("‼️ Error while appending transcription to confai")
        
        # Továbbítjuk az eredeti frame-et is
        await self.push_frame(frame, direction)


class TranscriptionLogger(FrameProcessor):
    """Egyszerű logger a transzkripciók konzolra írásához."""

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        # Ha TranscriptionFrame érkezik
        if isinstance(frame, TranscriptionFrame):
            logger.info(f"📝 {frame.user_id or 'user'}: {frame.text}")

        # Ha TranscriptionUpdateFrame (több üzenet) érkezik
        if isinstance(frame, TranscriptionUpdateFrame):
            for msg in frame.messages:
                if isinstance(msg, TranscriptionMessage):
                    timestamp = f"[{msg.timestamp}] " if msg.timestamp else ""
                    logger.info(f"📝 {timestamp}{msg.role}: {msg.content}")

        # Továbbítjuk az eredeti frame-et
        await self.push_frame(frame, direction)


# Transport paraméterek - csak audio input és text output
transport_params = {
    "daily": lambda: DailyParams(
        audio_in_enabled=True,
        audio_out_enabled=False,  # Nincs bot audio
        video_out_enabled=False,  # Nincs bot video
        text_output_enabled=True,  # Text output a transkripcióhoz
        vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=0.5)),
    ),
    "twilio": lambda: FastAPIWebsocketParams(
        audio_in_enabled=True,
        audio_out_enabled=False,  # Nincs bot audio
        video_out_enabled=False,  # Nincs bot video
        text_output_enabled=True,  # Text output a transkripcióhoz
        vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=0.5)),
    ),
    "webrtc": lambda: TransportParams(
        audio_in_enabled=True,
        audio_out_enabled=False,  # Nincs bot audio
        video_out_enabled=False,  # Nincs bot video
        text_output_enabled=True,  # Text output a transkripcióhoz
        vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=0.5)),
    ),
}


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments):
    logger.info("🎤 Valós idejű átírás indítása...")

    # Szolgáltatások inicializálása
    credentials_path = os.getenv("GOOGLE_TEST_CREDENTIALS")
    
    # STT - átíráshoz
    stt = GoogleSTTService(
        params=GoogleSTTService.InputParams(languages=Language.HU, model="chirp_3"),
        credentials_path=credentials_path,
        location="eu",
    )

    # Transcript display + logger
    transcript_display = TranscriptDisplayProcessor()
    transcription_logger = TranscriptionLogger()

    # Pipeline összeállítása - STT → logger → display → output
    pipeline = Pipeline(
        [
            transport.input(),  # Audio input
            stt,  # Speech-to-Text
            transcription_logger,  # Konzol loggolás
            transcript_display,  # Transcript megjelenítés a felületen
            transport.output(),  # Text output a felületre
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
        idle_timeout_secs=runner_args.pipeline_idle_timeout_secs,
    )

    # Make the task available to processors so they can access session info
    # (used by confai helpers: start/finalize/append)
    try:
        transcript_display._task = task
        transcription_logger._task = task
    except Exception:
        logger.debug("Could not attach task to processors")

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info("✅ Kliens csatlakozott - átírás elkezdődött")
        logger.info("💡 Az elhangzott szöveg megjelenik a böngészőben\n")

        # Start remote transcription session (helper handles errors)
        await start_confai_transcription(task)

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("❌ Kliens lecsatlakozott")
        # Attempt to finalize remote transcription session before cancelling
        try:
            await finalize_confai_transcription(task)
        except Exception:
            logger.exception("Error while finalizing remote transcription on disconnect")

        await task.cancel()

    runner = PipelineRunner(handle_sigint=runner_args.handle_sigint)

    await runner.run(task)


async def bot(runner_args: RunnerArguments):
    """Main bot entry point compatible with Pipecat Cloud."""
    transport = await create_transport(runner_args, transport_params)
    await run_bot(transport, runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
