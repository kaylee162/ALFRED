import { useCallback, useEffect, useRef, useState } from "react";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

type VoiceState = "idle" | "loading" | "speaking" | "error";

type BrowserAudioContext = AudioContext;

export function useAlfredVoice() {
  const audioContextRef = useRef<BrowserAudioContext | null>(null);
  const sourceRef = useRef<AudioBufferSourceNode | null>(null);
  const requestControllerRef = useRef<AbortController | null>(null);
  const requestIdRef = useRef(0);

  const [voiceState, setVoiceState] = useState<VoiceState>("idle");
  const [voiceEnabled, setVoiceEnabledState] = useState(
    () => localStorage.getItem("alfredVoiceEnabled") !== "false",
  );

  const getAudioContext = useCallback((): BrowserAudioContext => {
    if (!audioContextRef.current) {
      const AudioContextClass =
        window.AudioContext ||
        (window as typeof window & { webkitAudioContext?: typeof AudioContext })
          .webkitAudioContext;

      if (!AudioContextClass) {
        throw new Error("This browser does not support Web Audio playback.");
      }

      audioContextRef.current = new AudioContextClass();
    }

    return audioContextRef.current;
  }, []);

  const unlockVoice = useCallback(async (): Promise<void> => {
    try {
      const context = getAudioContext();
      if (context.state === "suspended") {
        await context.resume();
      }
    } catch (error) {
      console.error("Unable to unlock ALFRED voice playback:", error);
      setVoiceState("error");
    }
  }, [getAudioContext]);

  const clearCurrentAudio = useCallback(() => {
    requestIdRef.current += 1;
    requestControllerRef.current?.abort();
    requestControllerRef.current = null;

    if (sourceRef.current) {
      try {
        sourceRef.current.onended = null;
        sourceRef.current.stop();
      } catch {
        // The source may already have ended. Nothing else is required.
      }
      sourceRef.current.disconnect();
      sourceRef.current = null;
    }
  }, []);

  const stopSpeaking = useCallback(() => {
    clearCurrentAudio();
    setVoiceState("idle");
  }, [clearCurrentAudio]);

  const setVoiceEnabled = useCallback(
    (enabled: boolean) => {
      localStorage.setItem("alfredVoiceEnabled", String(enabled));
      setVoiceEnabledState(enabled);
      if (!enabled) stopSpeaking();
    },
    [stopSpeaking],
  );

  const speak = useCallback(
    async (text: string): Promise<void> => {
      const normalizedText = text.trim();
      if (!voiceEnabled || !normalizedText) return;

      clearCurrentAudio();
      const currentRequestId = requestIdRef.current;
      const controller = new AbortController();
      requestControllerRef.current = controller;
      setVoiceState("loading");

      try {
        const context = getAudioContext();
        if (context.state === "suspended") {
          await context.resume();
        }

        const response = await fetch(`${API_BASE_URL}/voice/speak`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: normalizedText }),
          signal: controller.signal,
        });

        if (!response.ok) {
          const errorBody = await response.json().catch(() => null);
          throw new Error(
            errorBody?.detail || `Voice request failed: ${response.status}`,
          );
        }

        const audioBytes = await response.arrayBuffer();
        if (!audioBytes.byteLength) {
          throw new Error("Voice endpoint returned empty audio.");
        }

        if (currentRequestId !== requestIdRef.current) return;

        const audioBuffer = await context.decodeAudioData(audioBytes.slice(0));
        if (currentRequestId !== requestIdRef.current) return;

        const source = context.createBufferSource();
        source.buffer = audioBuffer;
        source.connect(context.destination);
        sourceRef.current = source;

        source.onended = () => {
          if (sourceRef.current === source) {
            source.disconnect();
            sourceRef.current = null;
            setVoiceState("idle");
          }
        };

        source.start(0);
        setVoiceState("speaking");
      } catch (error) {
        if ((error as Error)?.name === "AbortError") return;
        console.error("ALFRED voice error:", error);
        clearCurrentAudio();
        setVoiceState("error");
      }
    },
    [clearCurrentAudio, getAudioContext, voiceEnabled],
  );

  useEffect(() => {
    return () => {
      clearCurrentAudio();
      const context = audioContextRef.current;
      audioContextRef.current = null;
      if (context && context.state !== "closed") {
        void context.close();
      }
    };
  }, [clearCurrentAudio]);

  return {
    voiceState,
    voiceEnabled,
    setVoiceEnabled,
    speak,
    stopSpeaking,
    unlockVoice,
  };
}
