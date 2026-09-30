/**
 * speechRecognition.ts — Browser Speech-to-Text Controller
 * Captures user voice commands and dispatches them to the Cloud Brain.
 */

import { useAryaStore } from '../store/useAryaStore';
import { audioPlayer } from './audioPlayer';

class SpeechRecognitionService {
  private recognition: any = null;
  private isListening = false;
  private autoRestart = true;
  private restartTimer: any = null;

  constructor() {
    this.init();
  }

  private init() {
    if (typeof window === 'undefined') return;
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) {
      console.warn('[Speech] Web Speech API not supported in this browser.');
      return;
    }

    try {
      this.recognition = new SpeechRecognition();
      this.recognition.continuous = true;
      this.recognition.interimResults = false;
      this.recognition.lang = 'en-US';

      this.recognition.onstart = () => {
        this.isListening = true;
        const store = useAryaStore.getState();
        if (store.voiceState !== 'speaking' && store.voiceState !== 'thinking') {
          store.setVoiceState('listening');
        }
      };

      this.recognition.onresult = (event: any) => {
        const results = event.results;
        if (!results || results.length === 0) return;
        const lastResult = results[results.length - 1];
        if (lastResult.isFinal) {
          const text = lastResult[0].transcript.trim();
          if (text) {
            console.log('[Speech Recognized]:', text);
            // Stop any ongoing AI audio playback when user starts a new command
            audioPlayer.stop();
            useAryaStore.getState().sendUserQuery(text);
          }
        }
      };

      this.recognition.onerror = (event: any) => {
        if (event.error === 'no-speech') {
          // Normal timeout, ignore and keep alive if autoRestart is on
          return;
        }
        if (event.error === 'not-allowed') {
          console.warn('[Speech] Microphone access denied.');
          this.autoRestart = false;
          useAryaStore.getState().setMicEnabled(false);
          useAryaStore.getState().addToast({
            title: 'Microphone Blocked',
            description: 'Please allow microphone access in your browser address bar.',
            type: 'error',
          });
          return;
        }
        console.warn('[Speech Error]:', event.error);
      };

      this.recognition.onend = () => {
        this.isListening = false;
        const store = useAryaStore.getState();
        if (store.micEnabled && this.autoRestart) {
          clearTimeout(this.restartTimer);
          this.restartTimer = setTimeout(() => {
            if (useAryaStore.getState().micEnabled) {
              this.start();
            }
          }, 350);
        } else {
          if (store.voiceState === 'listening') {
            store.setVoiceState('idle');
          }
        }
      };
    } catch (e) {
      console.warn('[Speech] Failed to initialize SpeechRecognition:', e);
    }
  }

  public start() {
    if (!this.recognition || this.isListening) return;
    this.autoRestart = true;
    try {
      this.recognition.start();
    } catch (err: any) {
      // If already started, ignore error
      if (err.name !== 'InvalidStateError') {
        console.warn('[Speech] start error:', err);
      }
    }
  }

  public stop() {
    this.autoRestart = false;
    clearTimeout(this.restartTimer);
    if (!this.recognition || !this.isListening) return;
    try {
      this.recognition.stop();
    } catch (err) {
      console.warn('[Speech] stop error:', err);
    }
    this.isListening = false;
  }
}

export const speechService = new SpeechRecognitionService();
