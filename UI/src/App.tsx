import React, { useEffect } from 'react';
import { AppShell } from './components/layout/AppShell';
import { wsService } from './services/websocket';
import { speechService } from './services/speechRecognition';
import { audioPlayer } from './services/audioPlayer';
import { useAryaStore } from './store/useAryaStore';

export function App() {
  const micEnabled = useAryaStore((s) => s.micEnabled);

  useEffect(() => {
    wsService.connect();

    // Unlock browser audio context on first user interaction (click, keypress, touch)
    const unlockAudio = () => {
      audioPlayer.unlock();
      window.removeEventListener('click', unlockAudio);
      window.removeEventListener('keydown', unlockAudio);
      window.removeEventListener('touchstart', unlockAudio);
    };
    window.addEventListener('click', unlockAudio, { once: true });
    window.addEventListener('keydown', unlockAudio, { once: true });
    window.addEventListener('touchstart', unlockAudio, { once: true });
  }, []);

  useEffect(() => {
    if (micEnabled) {
      speechService.start();
    } else {
      speechService.stop();
    }
  }, [micEnabled]);

  return <AppShell />;
}

export default App;
