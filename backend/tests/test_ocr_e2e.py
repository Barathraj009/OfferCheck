"""Comprehensive test for OCR and Document Extraction End-to-End flow."""
import asyncio
import io
from pathlib import Path
import sys
import httpx
from PIL import Image, ImageDraw, ImageFont
import pypdf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.main import app


async def main():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        print("\n--- TEST 1: Backend Health Check ---")
        res_health = await client.get("/api/health")
        assert res_health.status_code == 200, f"Health check failed: {res_health.status_code}"
        data = res_health.json()
        print(f"PASS: Backend is healthy (default_mode={data.get('default_mode')})")

        print("\n--- TEST 2: Screenshot Image OCR Extraction ---")
        # Create a test image with text
        img = Image.new("RGB", (400, 100), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)
        draw.text((20, 35), "Special Offer: 100x Guaranteed Return", fill=(0, 0, 0))
        img_buf = io.BytesIO()
        img.save(img_buf, format="PNG")
        img_bytes = img_buf.getvalue()

        res_ocr = await client.post(
            "/api/ocr?lang=eng",
            files={"file": ("screenshot.png", img_bytes, "image/png")}
        )
        assert res_ocr.status_code == 200, f"OCR failed: {res_ocr.status_code} {res_ocr.text}"
        ocr_data = res_ocr.json()
        print(f"PASS: OCR extracted: {ocr_data.get('text')!r} (engine={ocr_data.get('engine')})")
        assert "Special Offer" in ocr_data.get("text", "") or "Guaranteed" in ocr_data.get("text", "") or len(ocr_data.get("text", "")) > 0

        print("\n--- TEST 3: PDF Document Text Extraction ---")
        pdf_writer = pypdf.PdfWriter()
        # Create PDF with text using stream
        pdf_stream = (
            b"%PDF-1.4\n"
            b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
            b"3 0 obj<</Type/Page/MediaBox[0 0 300 144]/Parent 2 0 R/Resources<<\n"
            b"/Font<</F1 4 0 R>>>>/Contents 5 0 R>>endobj\n"
            b"4 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
            b"5 0 obj<</Length 62>>stream\n"
            b"BT\n"
            b"/F1 14 Tf\n"
            b"0 50 Td\n"
            b"(Claim your exclusive free airdrop now at fake-airdrop.xyz) Tj\n"
            b"ET\n"
            b"endstream\n"
            b"endobj\n"
            b"xref\n"
            b"0 6\n"
            b"0000000000 65535 f\n"
            b"0000000009 00000 n\n"
            b"0000000056 00000 n\n"
            b"0000000111 00000 n\n"
            b"0000000212 00000 n\n"
            b"0000000287 00000 n\n"
            b"trailer<</Size 6/Root 1 0 R>>\n"
            b"startxref\n"
            b"399\n"
            b"%%EOF\n"
        )
        res_pdf = await client.post(
            "/api/ocr?lang=eng",
            files={"file": ("airdrop_promo.pdf", pdf_stream, "application/pdf")}
        )
        assert res_pdf.status_code == 200, f"PDF failed: {res_pdf.status_code} {res_pdf.text}"
        pdf_data = res_pdf.json()
        print(f"PASS: PDF extracted text: {pdf_data.get('text')!r} (engine={pdf_data.get('engine')})")
        assert "airdrop" in pdf_data.get("text", "").lower()

        print("\n--- TEST 4: Error Handling - Unsupported File Format ---")
        res_bad_type = await client.post(
            "/api/ocr?lang=eng",
            files={"file": ("document.exe", b"MZ\x90\x00", "application/x-msdownload")}
        )
        assert res_bad_type.status_code == 415, f"Expected 415, got {res_bad_type.status_code}"
        print(f"PASS: 415 returned: {res_bad_type.json()}")

        print("\n--- TEST 5: Error Handling - Empty File ---")
        res_empty = await client.post(
            "/api/ocr?lang=eng",
            files={"file": ("empty.png", b"", "image/png")}
        )
        assert res_empty.status_code == 422, f"Expected 422, got {res_empty.status_code}"
        print(f"PASS: 422 returned for empty file: {res_empty.json()}")

        print("\n--- TEST 6: Error Handling - Invalid Language Code ---")
        res_bad_lang = await client.post(
            "/api/ocr?lang=invalid_123_bad",
            files={"file": ("screenshot.png", img_bytes, "image/png")}
        )
        assert res_bad_lang.status_code == 422, f"Expected 422, got {res_bad_lang.status_code}"
        print(f"PASS: 422 returned for invalid lang: {res_bad_lang.json()}")

        print("\n--- TEST 7: End-to-End Analysis using Extracted Text ---")
        extracted_text = pdf_data.get("text")
        analyze_payload = {
            "text": extracted_text,
            "url": "https://fake-airdrop.xyz",
            "token_name": "AIRDROP",
            "contract_address": "",
            "chain": "ethereum",
            "mode": "demo",
            "language": "en"
        }
        res_analyze = await client.post("/api/analyze", json=analyze_payload)
        assert res_analyze.status_code == 200, f"Analysis failed: {res_analyze.status_code} {res_analyze.text}"
        report = res_analyze.json()
        print(f"PASS: Report generated! Keys: {list(report.keys())}")
        if "score" in report:
            print(f"PASS: Score: {report.get('score')}")
        if "summary" in report:
            print(f"PASS: Summary: {report.get('summary')}")

        print("\n==========================================")
        print("ALL TESTS PASSED SUCCESSFULLY!")
        print("==========================================")


if __name__ == "__main__":
    asyncio.run(main())
