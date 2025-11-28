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

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import (
    Frame,
    OutputTransportMessageFrame,
    TranscriptionFrame,
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
            message_frame = OutputTransportMessageFrame(message={"text": text})
            logger.info(f"📤 OutputTransportMessageFrame küldése: {text}")
            await self.push_frame(message_frame, FrameDirection.DOWNSTREAM)
        
        # Továbbítjuk az eredeti frame-et is
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

    # Transcript display processor - elküldi a szöveget a felületre
    transcript_display = TranscriptDisplayProcessor()

    # Pipeline összeállítása - STT → display → output
    pipeline = Pipeline(
        [
            transport.input(),  # Audio input
            stt,  # Speech-to-Text
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

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info("✅ Kliens csatlakozott - átírás elkezdődött")
        logger.info("💡 Az elhangzott szöveg megjelenik a böngészőben\n")

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("❌ Kliens lecsatlakozott")
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
