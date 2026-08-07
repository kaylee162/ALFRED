import { useCallback, useEffect, useRef, useState } from "react";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

const MAX_SPEECH_CHUNK_CHARACTERS = 220;

const AUDIO_PLAYBACK_RATE = 1.12;

type VoiceState = "idle" | "loading" | "speaking" | "error";

type SpeechCallbacks = {
  onStart?: () => void;
  onProgress?: (progress: number) => void;
  onEnd?: () => void;
  onError?: () => void;
};

interface UseAlfredVoiceResult {
  voiceState: VoiceState;
  voiceEnabled: boolean;
  setVoiceEnabled: (enabled: boolean) => void;
  speak: (text: string, callbacks?: SpeechCallbacks) => Promise<void>;
  stopSpeaking: () => void;
  unlockVoice: () => Promise<void>;
}

function splitSpeechText(text: string): string[] {
  const normalized = text.replace(/\s+/g, " ").trim();
  if (!normalized) return [];

  const sentences = normalized.match(/[^.!?]+[.!?]+|[^.!?]+$/g) ?? [normalized];
  const chunks: string[] = [];

  for (const sentenceValue of sentences) {
    let sentence = sentenceValue.trim();
    if (!sentence) continue;

    while (sentence.length > MAX_SPEECH_CHUNK_CHARACTERS) {
      const candidate = sentence.slice(0, MAX_SPEECH_CHUNK_CHARACTERS + 1);
      const splitAt = Math.max(
        candidate.lastIndexOf(", "),
        candidate.lastIndexOf("; "),
        candidate.lastIndexOf(": "),
        candidate.lastIndexOf(" "),
      );
      const safeSplit = splitAt >= 80 ? splitAt + 1 : MAX_SPEECH_CHUNK_CHARACTERS;
      chunks.push(sentence.slice(0, safeSplit).trim());
      sentence = sentence.slice(safeSplit).trim();
    }

    if (sentence) chunks.push(sentence);
  }

  return chunks;
}

export function useAlfredVoice(): UseAlfredVoiceResult {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const audioUrlsRef = useRef<string[]>([]);
  const animationFrameRef = useRef<number | null>(null);
  const requestControllersRef = useRef<AbortController[]>([]);
  const generationRef = useRef(0);

  const [voiceState, setVoiceState] = useState<VoiceState>("idle");
  const [voiceEnabled, setVoiceEnabledState] = useState<boolean>(() => {
    return localStorage.getItem("alfredVoiceEnabled") !== "false";
  });

  const clearCurrentAudio = useCallback(() => {
    generationRef.current += 1;

    requestControllersRef.current.forEach((controller) => controller.abort());
    requestControllersRef.current = [];

    if (animationFrameRef.current !== null) {
      window.cancelAnimationFrame(animationFrameRef.current);
      animationFrameRef.current = null;
    }

    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
      audioRef.current.src = "";
      audioRef.current = null;
    }

    audioUrlsRef.current.forEach((url) => URL.revokeObjectURL(url));
    audioUrlsRef.current = [];
  }, []);

  const stopSpeaking = useCallback(() => {
    clearCurrentAudio();
    setVoiceState("idle");
  }, [clearCurrentAudio]);

  const unlockVoice = useCallback(async () => {
    const audio = new Audio();
    audio.muted = true;
    try {
      await audio.play();
    } catch {
      // The browser may reject a source-less element. The user gesture still
      // gives the later playback request the best chance of succeeding.
    } finally {
      audio.pause();
      audio.muted = false;
    }
  }, []);

  const setVoiceEnabled = useCallback(
    (enabled: boolean) => {
      localStorage.setItem("alfredVoiceEnabled", String(enabled));
      setVoiceEnabledState(enabled);
      if (!enabled) stopSpeaking();
    },
    [stopSpeaking],
  );

  const fetchSpeechChunk = useCallback(async (text: string): Promise<string> => {
    const controller = new AbortController();
    requestControllersRef.current.push(controller);

    const response = await fetch(`${API_BASE_URL}/voice/speak`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
      signal: controller.signal,
    });

    requestControllersRef.current = requestControllersRef.current.filter(
      (item) => item !== controller,
    );

    if (!response.ok) {
      throw new Error(`Voice request failed: ${response.status}`);
    }

    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    audioUrlsRef.current.push(url);
    return url;
  }, []);

  const speak = useCallback(
    async (text: string, callbacks: SpeechCallbacks = {}): Promise<void> => {
      if (!voiceEnabled || !text.trim()) return;

      clearCurrentAudio();
      const generation = generationRef.current;
      const chunks = splitSpeechText(text);
      if (!chunks.length) return;

      const totalCharacters = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
      const chunkPromises = new Map<number, Promise<string>>();
      let completedCharacters = 0;
      let hasStarted = false;

      const prefetch = (index: number) => {
        if (index >= chunks.length || chunkPromises.has(index)) return;
        chunkPromises.set(index, fetchSpeechChunk(chunks[index]));
      };

      setVoiceState("loading");
      prefetch(0);
      prefetch(1);

      try {
        for (let index = 0; index < chunks.length; index += 1) {
          if (generationRef.current !== generation) return;

          prefetch(index);
          prefetch(index + 1);
          const audioUrl = await chunkPromises.get(index)!;
          if (generationRef.current !== generation) return;

          const audio = new Audio(audioUrl);
          audio.preload = "auto";
          audio.playbackRate = AUDIO_PLAYBACK_RATE;
          audio.defaultPlaybackRate = AUDIO_PLAYBACK_RATE;
          audio.preservesPitch = true;
          audioRef.current = audio;
          
          await new Promise<void>((resolve, reject) => {
            const reportProgress = () => {
              if (generationRef.current !== generation || audioRef.current !== audio) {
                return;
              }

              const duration = Number.isFinite(audio.duration) ? audio.duration : 0;
              const localProgress = duration > 0 ? audio.currentTime / duration : 0;
              const overallProgress =
                (completedCharacters + chunks[index].length * localProgress) /
                totalCharacters;
              callbacks.onProgress?.(Math.min(1, Math.max(0, overallProgress)));

              if (!audio.paused && !audio.ended) {
                animationFrameRef.current = window.requestAnimationFrame(reportProgress);
              }
            };

            audio.onplay = () => {
              setVoiceState("speaking");
              if (!hasStarted) {
                hasStarted = true;
                callbacks.onStart?.();
              }
              animationFrameRef.current = window.requestAnimationFrame(reportProgress);
            };
            audio.onended = () => resolve();
            audio.onerror = () => reject(new Error("Audio playback failed."));

            void audio.play().catch(reject);
          });

          completedCharacters += chunks[index].length;
          callbacks.onProgress?.(Math.min(1, completedCharacters / totalCharacters));

          // Keep two sentences prepared ahead of playback without waiting for
          // the entire answer before Alfred begins speaking.
          prefetch(index + 2);
        }

        callbacks.onProgress?.(1);
        callbacks.onEnd?.();
        clearCurrentAudio();
        setVoiceState("idle");
      } catch (error: any) {
        if (error?.name === "AbortError" || generationRef.current !== generation) return;
        console.error("Alfred voice error:", error);
        callbacks.onError?.();
        clearCurrentAudio();
        setVoiceState("error");
      }
    },
    [clearCurrentAudio, fetchSpeechChunk, voiceEnabled],
  );

  useEffect(() => clearCurrentAudio, [clearCurrentAudio]);

  return {
    voiceState,
    voiceEnabled,
    setVoiceEnabled,
    speak,
    stopSpeaking,
    unlockVoice,
  };
}
