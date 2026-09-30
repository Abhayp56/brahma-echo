/**
 * audioPlayer.ts — Real-time Web Audio PCM Stream Player for Gemini Live
 * Handles 24kHz raw PCM16 audio chunks sent from the Cloud Brain backend over WebSocket.
 */

import { useAryaStore } from '../store/useAryaStore';

class AudioPlayerService {
  private audioCtx: AudioContext | null = null;
  private analyser: AnalyserNode | null = null;
  private nextAudioTime = 0;
  private isSpeaking = false;
  private playbackTimer: any = null;
  private analyserData: Uint8Array | null = null;

  public init() {
    if (!this.audioCtx) {
      const AudioContextClass = window.AudioContext || (window as any).webkitAudioContext;
      this.audioCtx = new AudioContextClass({ sampleRate: 24000 });
      this.analyser = this.audioCtx.createAnalyser();
      this.analyser.fftSize = 256;
      this.analyser.smoothingTimeConstant = 0.8;
      this.analyserData = new Uint8Array(this.analyser.frequencyBinCount);
    }
    if (this.audioCtx.state === 'suspended') {
      this.audioCtx.resume().catch(() => {});
    }
  }

  /**
   * Decodes and enqueues a base64-encoded 24kHz raw PCM16 audio chunk.
   */
  public playPcmChunk(b64Data: string) {
    try {
      this.init();
      if (!this.audioCtx || !this.analyser) return;

      this.isSpeaking = true;
      useAryaStore.getState().setVoiceState('speaking');

      // Convert base64 to binary
      const binaryString = window.atob(b64Data);
      const len = binaryString.length;
      const bytes = new Uint8Array(len);
      for (let i = 0; i < len; i++) {
        bytes[i] = binaryString.charCodeAt(i);
      }

      // Convert PCM16 (Int16) to Float32 [-1.0, 1.0]
      const int16Array = new Int16Array(bytes.buffer);
      const float32Array = new Float32Array(int16Array.length);
      for (let i = 0; i < int16Array.length; i++) {
        float32Array[i] = int16Array[i] / 32768.0;
      }

      // Create AudioBuffer (single channel, 24kHz)
      const audioBuffer = this.audioCtx.createBuffer(1, float32Array.length, 24000);
      audioBuffer.getChannelData(0).set(float32Array);

      // Create buffer source node
      const source = this.audioCtx.createBufferSource();
      source.buffer = audioBuffer;

      // Connect source -> analyser -> destination (speakers)
      source.connect(this.analyser);
      this.analyser.connect(this.audioCtx.destination);

      // Schedule seamless gapless playback
      const now = this.audioCtx.currentTime;
      if (this.nextAudioTime < now) {
        this.nextAudioTime = now;
      }
      source.start(this.nextAudioTime);
      this.nextAudioTime += audioBuffer.duration;

      // Reset turn timeout
      clearTimeout(this.playbackTimer);
      source.onended = () => {
        if (this.audioCtx && this.audioCtx.currentTime >= this.nextAudioTime - 0.05) {
          this.checkDoneSpeaking();
        }
      };
    } catch (err) {
      console.error('[AudioPlayer] PCM playback error:', err);
    }
  }

  public onTurnComplete() {
    if (!this.audioCtx) {
      this.isSpeaking = false;
      useAryaStore.getState().setVoiceState('idle');
      return;
    }
    const remainingSec = Math.max(0, this.nextAudioTime - this.audioCtx.currentTime);
    const waitMs = Math.round(remainingSec * 1000) + 300;
    clearTimeout(this.playbackTimer);
    this.playbackTimer = setTimeout(() => {
      this.checkDoneSpeaking();
    }, waitMs);
  }

  private checkDoneSpeaking() {
    this.isSpeaking = false;
    const store = useAryaStore.getState();
    if (store.voiceState === 'speaking') {
      store.setVoiceState(store.micEnabled ? 'listening' : 'idle');
    }
  }

  public stop() {
    clearTimeout(this.playbackTimer);
    this.nextAudioTime = 0;
    this.isSpeaking = false;
    const store = useAryaStore.getState();
    store.setVoiceState(store.micEnabled ? 'listening' : 'idle');
  }

  public getAudioLevels(): { level: number; low: number; mid: number; high: number } | null {
    if (!this.analyser || !this.analyserData || !this.isSpeaking) return null;
    this.analyser.getByteFrequencyData(this.analyserData as any);

    const bufferLength = this.analyserData.length;
    let sumLow = 0, countLow = 0;
    let sumMid = 0, countMid = 0;
    let sumHigh = 0, countHigh = 0;
    let totalSum = 0;

    for (let i = 0; i < bufferLength; i++) {
      const val = this.analyserData[i] / 255;
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

    return {
      level: Math.min(1, (totalSum / bufferLength) * 2.8),
      low: Math.min(1, (countLow > 0 ? sumLow / countLow : 0) * 2.8),
      mid: Math.min(1, (countMid > 0 ? sumMid / countMid : 0) * 2.8),
      high: Math.min(1, (countHigh > 0 ? sumHigh / countHigh : 0) * 2.8),
    };
  }
}

export const audioPlayer = new AudioPlayerService();
