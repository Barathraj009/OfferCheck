## Check an Offer Page — Status Report

### Purpose
Input form to collect offer text, optional URL/token/chain/contract, select mode (demo/live), load sample scenarios, transcribe via voice, extract text from image (OCR), and submit for analysis.

### Current State: Functional
- Imports: ApiError, getScenarios, ocrImage from ../api; types from ../types
- Props: form, setForm, health, healthErr, error, onSubmit
- State: scenarios, listening, note, ocrBusy, localErr
- Language selection (10 Indian langs) for speech/OCR/explanation context
- Sample scenarios loaded on mount (getScenarios) with visual selection
- Form fields: text (with maxLength from health), URL, token name, chain, contract address
- Chain dropdown populated from health.chains + Solana/Other (marked "cannot be verified yet")
- Voice: SpeechRecognition API (with graceful fallback), toggles listening, appends transcript
- OCR: file upload (png/jpeg/webp, <=5MB) via ocrImage -> appends text + note
- Validation: requires at least one of text/url/token_name/contract_address; shows localErr or field errors
- Submission: calls onSubmit(form) which triggers App.analyze -> routes /analysis -> /report
- Accessibility: labels, aria-invalid, aria-describedby, role="alert"/"status", focusable main, skip link context via App

### Integration
- API: analyze(form) posts all fields to /api/analyze (timeout 180s)
- OCR: /api/ocr via ocrImage
- Health: drives defaults (max_input_chars, chains, mode)
- Routes: /#/check, /#/analysis, /#/report

### Tests/Build
- Backend 70/70 unit OK; 46/46 integration OK
- Frontend builds clean (tsc + vite)

### Notes
- UI complete and wired; no dead UI. OCR/voice optional. Zero-cost preserved.
