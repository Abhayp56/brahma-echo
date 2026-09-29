import React, { useEffect } from 'react';
import { AppShell } from './components/layout/AppShell';
import { wsService } from './services/websocket';

export function App() {
  useEffect(() => {
    wsService.connect();
  }, []);

  return <AppShell />;
}

export default App;
