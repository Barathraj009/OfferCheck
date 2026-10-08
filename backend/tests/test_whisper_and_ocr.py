"""Comprehensive test for Whisper Audio Transcription (WAV + WebM/Opus) and OCR Regression."""
import asyncio
import io
import math
from pathlib import Path
import sys
import wave
import av
import httpx
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.main import app


def create_sine_wav() -> bytes:
    """Create a 1-second 440Hz sine wave WAV file in memory."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        samples = bytearray()
        for i in range(16000):
            val = int(32767 * 0.5 * math.sin(2 * math.pi * 440 * i / 16000))
            samples.extend(val.to_bytes(2, byteorder="little", signed=True))
        wf.writeframes(samples)
    return buf.getvalue()


def create_opus_webm(wav_bytes: bytes) -> bytes:
    """Encode WAV bytes into a WebM (Opus) container using PyAV."""
    in_buf = io.BytesIO(wav_bytes)
    out_buf = io.BytesIO()
    
    input_container = av.open(in_buf, format="wav")
    output_container = av.open(out_buf, mode="w", format="webm")
    stream = output_container.add_stream("opus", rate=48000)
    stream.layout = "mono"

    for frame in input_container.decode(audio=0):
        for packet in stream.encode(frame):
            output_container.mux(packet)
    for packet in stream.encode():
        output_container.mux(packet)
        
    output_container.close()
    input_container.close()
    return out_buf.getvalue()


async def main():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        print("\n==========================================")
        print("TEST 1: Whisper Health Check")
        print("==========================================")
        res_health = await client.get("/api/whisper/health")
        print(f"Status: {res_health.status_code}, Body: {res_health.json()}")
        assert res_health.status_code == 200
        assert res_health.json().get("available") is True, "Whisper model should be available"

        print("\n==========================================")
        print("TEST 2: WAV Audio Transcription")
        print("==========================================")
        wav_bytes = create_sine_wav()
        res_wav = await client.post(
            "/api/whisper-transcribe",
            files={"file": ("speech.wav", wav_bytes, "audio/wav")}
        )
        print(f"Status: {res_wav.status_code}, Body: {res_wav.json()}")
        assert res_wav.status_code == 200
        assert res_wav.json().get("success") is True

        print("\n==========================================")
        print("TEST 3: WebM (Opus) Microphone Audio Transcription")
        print("==========================================")
        webm_bytes = create_opus_webm(wav_bytes)
        res_webm = await client.post(
            "/api/whisper-transcribe",
            files={"file": ("recording.webm", webm_bytes, "audio/webm")}
        )
        print(f"Status: {res_webm.status_code}, Body: {res_webm.json()}")
        assert res_webm.status_code == 200
        assert res_webm.json().get("success") is True

        print("\n==========================================")
        print("TEST 4: OCR Regression Check (PNG Screenshot)")
        print("==========================================")
        img = Image.new("RGB", (350, 80), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)
        draw.text((15, 30), "Offer: Double Your ETH in 24h", fill=(0, 0, 0))
        img_buf = io.BytesIO()
        img.save(img_buf, format="PNG")
        
        res_ocr = await client.post(
            "/api/ocr?lang=eng",
            files={"file": ("screenshot.png", img_buf.getvalue(), "image/png")}
        )
        print(f"Status: {res_ocr.status_code}, Body: {res_ocr.json()}")
        assert res_ocr.status_code == 200
        assert res_ocr.json().get("empty") is False
        assert len(res_ocr.json().get("text", "")) > 0

        print("\n==========================================")
        print("TEST 5: OCR Regression Check (PDF Document)")
        print("==========================================")
        with open(r"G:\Projects\offercheck\test_valid.pdf", "rb") as f:
            pdf_bytes = f.read()
        res_pdf = await client.post(
            "/api/ocr?lang=eng",
            files={"file": ("offer.pdf", pdf_bytes, "application/pdf")}
        )
        print(f"Status: {res_pdf.status_code}, Body: {res_pdf.json()}")
        assert res_pdf.status_code == 200
        assert res_pdf.json().get("empty") is False
        assert "USDT" in res_pdf.json().get("text", "")

        print("\n==========================================")
        print("ALL TESTS (WHISPER + OCR) PASSED SUCCESSFULLY!")
        print("==========================================")


if __name__ == "__main__":
    asyncio.run(main())
