/**
 * useSpeechRecognition — a thin React hook over the browser's built-in
 * Web Speech API (window.SpeechRecognition / webkitSpeechRecognition).
 *
 * Free, no backend, no audio upload. Works in Chrome/Edge; in browsers that
 * lack it (Firefox/Safari) `supported` is false and the UI falls back to
 * typing in the textarea.
 *
 * Returns:
 *   supported    — boolean: is the API available in this browser?
 *   listening    — boolean: is the mic currently capturing?
 *   transcript   — the recognized text so far
 *   setTranscript— lets the page edit the text (the textarea is bound to this)
 *   start/stop    — control the mic
 *   reset         — clear the transcript
 */
import { useCallback, useEffect, useRef, useState } from "react";

export function useSpeechRecognition({ lang = "en-IN" } = {}) {
    const [supported, setSupported] = useState(false);
    const [listening, setListening] = useState(false);
    const [transcript, setTranscript] = useState("");
    const recognitionRef = useRef(null);

    useEffect(() => {
        if (typeof window === "undefined") return;
        const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SR) {
            setSupported(false);
            return;
        }
        setSupported(true);

        const rec = new SR();
        rec.lang = lang;
        rec.continuous = true;       // keep listening across pauses
        rec.interimResults = true;   // stream partial words as they're heard

        rec.onresult = (event) => {
            // event.results holds ALL chunks (interim + final) for this session.
            // Concatenating each chunk's best alternative gives the full text.
            let text = "";
            for (let i = 0; i < event.results.length; i++) {
                text += event.results[i][0].transcript;
            }
            setTranscript(text);
        };
        rec.onend = () => setListening(false);
        rec.onerror = () => setListening(false);

        recognitionRef.current = rec;
        return () => {
            try { rec.stop(); } catch { /* already stopped */ }
        };
    }, [lang]);

    const start = useCallback(() => {
        const rec = recognitionRef.current;
        if (!rec) return;
        setTranscript("");
        try {
            rec.start();
            setListening(true);
        } catch { /* start() throws if already running — ignore */ }
    }, []);

    const stop = useCallback(() => {
        const rec = recognitionRef.current;
        if (!rec) return;
        try { rec.stop(); } catch { /* already stopped */ }
        setListening(false);
    }, []);

    const reset = useCallback(() => setTranscript(""), []);

    return { supported, listening, transcript, setTranscript, start, stop, reset };
}
