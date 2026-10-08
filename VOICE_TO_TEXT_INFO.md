## Voice-to-text model
The "Check an Offer" page uses the browser's built-in Web Speech API (SpeechRecognition / webkitSpeechRecognition). No server-side ASR model is used by the app.

Details:
- Implementation: frontend/src/pages/Check.tsx — toggleVoice() creates SpeechRecognition instance with r.lang = lang.speech (e.g. en-IN/hi-IN etc), continuous true, interimResults false, appends final transcript to form.text.
- Provider: browser-native. On Chrome/Edge this is typically Google's cloud speech recognition service (depends on browser/version/network). On other browsers varies.
- Zero-cost: no paid API key configured by app; uses user's browser capabilities.
