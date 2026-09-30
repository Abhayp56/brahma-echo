import { useAryaStore } from '../store/useAryaStore';
import { audioPlayer } from './audioPlayer';

class WebSocketService {
  private ws: WebSocket | null = null;
  private reconnectTimer: any = null;
  
  public connect() {
    if (this.ws) return;
    
    // Attempt to get token from existing dashboard login, otherwise default
    const token = sessionStorage.getItem('brahma_token') || 'local_dev_token';
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    // Use the actual host or default to localhost:8000 for dev
    const host = window.location.port === '5173' ? '127.0.0.1:8000' : window.location.host;
    
    const wsUrl = `${protocol}//${host}/ws?token=${token}`;
    
    try {
      this.ws = new WebSocket(wsUrl);
      
      this.ws.onopen = () => {
        console.log('[Brahma WS] Connected to backend');
        // Let the store know we are connected
        useAryaStore.setState((state) => ({
          desktopAgentState: { ...state.desktopAgentState, connected: true }
        }));
      };
      
      this.ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          this.handleMessage(data);
        } catch (e) {
          console.error('[Brahma WS] Failed to parse message', e);
        }
      };
      
      this.ws.onclose = () => {
        console.log('[Brahma WS] Disconnected');
        this.ws = null;
        useAryaStore.setState((state) => ({
          desktopAgentState: { ...state.desktopAgentState, connected: false }
        }));
        
        // Auto reconnect
        this.reconnectTimer = setTimeout(() => this.connect(), 3000);
      };
    } catch (error) {
      console.error('[Brahma WS] Connection error:', error);
      this.reconnectTimer = setTimeout(() => this.connect(), 3000);
    }
  }
  
  private handleMessage(data: any) {
    const store = useAryaStore.getState();
    
    switch (data.type) {
      case 'audio_chunk':
        // Real-time 24kHz PCM chunk from Gemini Live
        if (data.data) {
          audioPlayer.playPcmChunk(data.data);
        }
        break;

      case 'turn_complete':
        // Assistant finished speaking current turn
        audioPlayer.onTurnComplete();
        break;

      case 'transcript':
        // Real-time transcript from AI
        if (data.role === 'task_progress') {
          store.addTranscriptMessage({
            sender: 'system',
            text: `⚡ ${data.text}`,
          });
        } else if (data.role === 'assistant') {
          store.addTranscriptMessage({
            sender: 'arya',
            text: data.text,
          });
        } else if (data.role === 'user') {
          // Verify if not duplicate
          const lastMsg = store.transcript[store.transcript.length - 1];
          if (!lastMsg || lastMsg.text !== data.text || lastMsg.sender !== 'user') {
            store.addTranscriptMessage({
              sender: 'user',
              text: data.text,
            });
          }
        } else {
          store.addTranscriptMessage({
            sender: data.sender || 'arya',
            text: data.text,
          });
        }
        break;

      case 'phone_status':
        useAryaStore.setState((state) => ({
          integrations: {
            ...state.integrations,
            android: {
              connected: Boolean(data.connected),
              statusText: data.connected ? 'Online via Cloud WSS' : 'Disconnected',
              details: data.phone_info || state.integrations.android.details,
            },
          },
        }));
        break;

      case 'whatsapp_status': {
        const isAuth = (data.data?.status || data.status) === 'authenticated';
        const statusText = data.data?.status || data.status || 'Disconnected';
        useAryaStore.setState((state) => ({
          integrations: {
            ...state.integrations,
            whatsapp: {
              connected: isAuth,
              statusText: isAuth ? 'Authenticated' : statusText,
            },
          },
        }));
        break;
      }

      case 'whatsapp_message': {
        const payload = data.data || {};
        const sender = payload.sender || payload.push_name || 'WhatsApp Contact';
        const msgText = payload.text || payload.body || 'New message';
        store.addToast({
          title: `WhatsApp from ${sender}`,
          description: msgText,
          type: 'info',
        });
        break;
      }
        
      case 'metrics':
        // System metrics from Python psutil
        useAryaStore.setState({ metrics: data.data });
        break;
        
      case 'briefing':
        // Daily briefing
        useAryaStore.setState({ briefing: data.data });
        break;
        
      case 'action_response':
        store.addToast({
          title: data.title || 'Action Completed',
          description: data.message,
          type: data.success ? 'success' : 'error'
        });
        break;
        
      case 'history_entry':
        // Used to load past messages
        if (data.role && data.content) {
          store.addTranscriptMessage({
            sender: data.role === 'user' ? 'user' : 'arya',
            text: data.content,
          });
        }
        break;
    }
  }
  
  public sendCommand(text: string) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      // cloud_server.py accepts text_command and command
      this.ws.send(JSON.stringify({ type: 'text_command', text }));
    }
  }
  
  public sendAction(action: string, payload?: any) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: 'action', action, payload }));
    } else {
       useAryaStore.getState().addToast({
         title: 'Connection Error',
         description: 'Cannot send action. Backend not connected.',
         type: 'error'
       });
    }
  }
}

export const wsService = new WebSocketService();

