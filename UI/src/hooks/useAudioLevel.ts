import { useEffect, useRef } from 'react';
import { useAryaStore } from '../store/useAryaStore';

export interface AudioLevels {
  level: number; // Overall smoothed 0 to 1
  low: number;   // Bass / Low band (20Hz - 250Hz)
  mid: number;   // Mid band (250Hz - 2000Hz)
  high: number;  // Treble / High band (2000Hz - 8000Hz)
}

export const useAudioLevel = (): React.RefObject<AudioLevels> => {
  const micEnabled = useAryaStore((s) => s.micEnabled);
  const levelsRef = useRef<AudioLevels>({ level: 0, low: 0, mid: 0, high: 0 });

  const audioCtxRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const animFrameRef = useRef<number | null>(null);

  useEffect(() => {
    if (!micEnabled) {
      // Clean up audio hardware stream when mic disabled
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
      }
      if (audioCtxRef.current && audioCtxRef.current.state !== 'closed') {
        audioCtxRef.current.close().catch(() => {});
        audioCtxRef.current = null;
      }
      levelsRef.current = { level: 0, low: 0, mid: 0, high: 0 };
      return;
    }

    let isSubscribed = true;

    async function initAudio() {
      try {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
          console.warn('getUserMedia is not supported on this browser');
          return;
        }

        const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
        if (!isSubscribed) {
          stream.getTracks().forEach((track) => track.stop());
          return;
        }

        streamRef.current = stream;

        const AudioContextClass = window.AudioContext || (window as any).webkitAudioContext;
        const ctx = new AudioContextClass();
        audioCtxRef.current = ctx;

        const analyser = ctx.createAnalyser();
        analyser.fftSize = 256;
        analyser.smoothingTimeConstant = 0.8;
        analyserRef.current = analyser;

        const source = ctx.createMediaStreamSource(stream);
        source.connect(analyser);

        const bufferLength = analyser.frequencyBinCount;
        const dataArray = new Uint8Array(bufferLength);

        // Smooth level tracking values
        let smoothLevel = 0;
        let smoothLow = 0;
        let smoothMid = 0;
        let smoothHigh = 0;

        const tick = () => {
          if (!analyserRef.current || !isSubscribed) return;

          analyserRef.current.getByteFrequencyData(dataArray);

          // Bin calculations
          let sumLow = 0, countLow = 0;
          let sumMid = 0, countMid = 0;
          let sumHigh = 0, countHigh = 0;
          let totalSum = 0;

          for (let i = 0; i < bufferLength; i++) {
            const val = dataArray[i] / 255;
            totalSum += val;

            if (i < 8) {
              sumLow += val;
              countLow++;
            } else if (i < 32) {
              sumMid += val;
              countMid++;
            } else if (i < 96) {
              sumHigh += val;
              countHigh++;
            }
          }

          const rawLevel = totalSum / bufferLength;
          const rawLow = countLow > 0 ? sumLow / countLow : 0;
          const rawMid = countMid > 0 ? sumMid / countMid : 0;
          const rawHigh = countHigh > 0 ? sumHigh / countHigh : 0;

          // Exponential smoothing
          smoothLevel = smoothLevel * 0.75 + rawLevel * 0.25;
          smoothLow = smoothLow * 0.75 + rawLow * 0.25;
          smoothMid = smoothMid * 0.75 + rawMid * 0.25;
          smoothHigh = smoothHigh * 0.75 + rawHigh * 0.25;

          levelsRef.current = {
            level: Math.min(1, smoothLevel * 2.5),
            low: Math.min(1, smoothLow * 2.5),
            mid: Math.min(1, smoothMid * 2.5),
            high: Math.min(1, smoothHigh * 2.5),
          };

          animFrameRef.current = requestAnimationFrame(tick);
        };

        tick();
      } catch (err) {
        console.warn('Audio input permission or device unavailable:', err);
        // Fallback to zero levels if mic denied
        if (isSubscribed) {
          levelsRef.current = { level: 0, low: 0, mid: 0, high: 0 };
        }
      }
    }

    initAudio();

    return () => {
      isSubscribed = false;
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
      }
      if (audioCtxRef.current && audioCtxRef.current.state !== 'closed') {
        audioCtxRef.current.close().catch(() => {});
        audioCtxRef.current = null;
      }
    };
  }, [micEnabled]);

  return levelsRef;
};

