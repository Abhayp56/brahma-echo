import React, { useEffect } from 'react';
import { AppShell } from './components/layout/AppShell';
import { wsService } from './services/websocket';
import { speechService } from './services/speechRecognition';
import { useAryaStore } from './store/useAryaStore';

export function App() {
  const micEnabled = useAryaStore((s) => s.micEnabled);

  useEffect(() => {
    wsService.connect();
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

