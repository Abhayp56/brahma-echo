import { create } from 'zustand';
import {
  VoiceState,
  IntegrationId,
  IntegrationStatus,
  TranscriptMessage,
  MemoryItem,
  MemoryCategory,
  BriefingData,
  SystemMetricData,
  DesktopAgentState,
  ToastNotification,
  ActionModalType,
} from '../types/arya';
import {
  telegramService,
  whatsappService,
  androidService,
  memoryService,
  briefingService,
  desktopAgentService,
} from '../services';
import { generateId, formatTime } from '../lib/utils';

interface AryaState {
  // 3D & Voice
  voiceState: VoiceState;
  micEnabled: boolean;
  
  // Modals & UI
  activeModal: ActionModalType;
  toasts: ToastNotification[];

  // Desktop Agent
  desktopAgentState: DesktopAgentState;

  // Integrations
  integrations: Record<IntegrationId, IntegrationStatus>;

  // Data Panels
  transcript: TranscriptMessage[];
  memories: MemoryItem[];
  memorySearchQuery: string;
  briefing: BriefingData | null;
  metrics: SystemMetricData | null;

  // Actions
  setVoiceState: (state: VoiceState) => void;
  setMicEnabled: (enabled: boolean) => void;
  toggleMic: () => void;

  setActiveModal: (modal: ActionModalType) => void;
  addToast: (toast: Omit<ToastNotification, 'id'>) => void;
  removeToast: (id: string) => void;

  // Desktop Agent
  toggleDesktopAgent: () => Promise<void>;

  // Integrations Actions
  loadIntegrationStatuses: () => Promise<void>;
  connectTelegram: (config: { botToken: string; botName: string; chatId: string }) => Promise<boolean>;
  disconnectTelegram: () => Promise<void>;
  connectWhatsApp: () => Promise<{ success: boolean; message: string }>;
  disconnectWhatsApp: () => Promise<void>;
  connectAndroid: () => Promise<{ success: boolean; message: string }>;
  disconnectAndroid: () => Promise<void>;

  // Chat & Transcript Actions
  addTranscriptMessage: (msg: Omit<TranscriptMessage, 'id' | 'timestamp'>) => void;
  sendUserQuery: (text: string) => Promise<void>;
  triggerMockConversationStream: () => void;

  // Memory Actions
  loadMemories: () => Promise<void>;
  addMemoryItem: (category: MemoryCategory, key: string, value: string, tags?: string[]) => Promise<void>;
  deleteMemoryItem: (id: string) => Promise<void>;
  setMemorySearchQuery: (query: string) => void;

  // Briefing Actions
  loadBriefing: () => Promise<void>;
  toggleBriefingTodo: (id: string) => Promise<void>;
  addBriefingTodo: (text: string) => Promise<void>;

  // Metrics
  setMetrics: (metrics: SystemMetricData) => void;
}

const INITIAL_TRANSCRIPT: TranscriptMessage[] = [
  {
    id: 'msg_1',
    sender: 'system',
    text: 'Arya Voice & Desktop Neural Link initialized. Standby for queries.',
    timestamp: '09:00:00 AM',
  },
  {
    id: 'msg_2',
    sender: 'arya',
    text: 'Good morning Alex. All desktop agents, memory banks, and schedule briefings are synchronized. How can I assist your workflow today?',
    timestamp: '09:00:05 AM',
    emotion: 'welcoming',
  },
];

export const useAryaStore = create<AryaState>((set, get) => ({
  voiceState: 'idle',
  micEnabled: true,
  activeModal: 'none',
  toasts: [],

  desktopAgentState: {
    connected: true,
    version: 'v2.4.0-stable',
    hostname: 'ALEX-WORKSTATION-X1',
    lastHeartbeat: '1s ago',
  },

  integrations: {
    telegram: { connected: false, statusText: 'Disconnected' },
    whatsapp: { connected: false, statusText: 'Disconnected' },
    android: { connected: false, statusText: 'Disconnected' },
  },

  transcript: INITIAL_TRANSCRIPT,
  memories: [],
  memorySearchQuery: '',
  briefing: null,
  metrics: null,

  setVoiceState: (voiceState) => set({ voiceState }),

  setMicEnabled: (micEnabled) => set({ micEnabled }),

  toggleMic: () => {
    const current = get().micEnabled;
    const next = !current;
    set({ micEnabled: next });
    get().addToast({
      title: next ? 'Microphone Active' : 'Microphone Muted',
      description: next ? 'Arya is listening for voice input.' : 'Voice input muted. Type in the input box.',
      type: 'info',
    });
  },

  setActiveModal: (activeModal) => set({ activeModal }),

  addToast: (toast) => {
    const id = generateId('toast');
    const newToast: ToastNotification = { id, ...toast, duration: toast.duration || 4000 };
    set((state) => ({ toasts: [...state.toasts, newToast] }));

    // Auto remove
    setTimeout(() => {
      get().removeToast(id);
    }, newToast.duration);
  },

  removeToast: (id) => set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) })),

  toggleDesktopAgent: async () => {
    const currentState = get().desktopAgentState;
    const newState = await desktopAgentService.toggleConnection(!currentState.connected);
    set({ desktopAgentState: newState });
    get().addToast({
      title: newState.connected ? 'Desktop Agent Connected' : 'Desktop Agent Disconnected',
      description: newState.connected
        ? `Linked to ${newState.hostname} (${newState.version})`
        : 'System metrics and automation commands paused.',
      type: newState.connected ? 'success' : 'warning',
    });
  },

  loadIntegrationStatuses: async () => {
    const tg = await telegramService.getStatus();
    const wa = await whatsappService.getStatus();
    const an = await androidService.getStatus();
    set({
      integrations: {
        telegram: tg,
        whatsapp: wa,
        android: an,
      },
    });
  },

  connectTelegram: async (config) => {
    const res = await telegramService.connect(config);
    if (res.success) {
      const status = await telegramService.getStatus();
      set((state) => ({
        integrations: { ...state.integrations, telegram: status },
      }));
      get().addToast({
        title: 'Telegram Connected',
        description: res.message,
        type: 'success',
      });
      return true;
    } else {
      get().addToast({
        title: 'Connection Failed',
        description: res.message,
        type: 'error',
      });
      return false;
    }
  },

  disconnectTelegram: async () => {
    await telegramService.disconnect();
    const status = await telegramService.getStatus();
    set((state) => ({
      integrations: { ...state.integrations, telegram: status },
    }));
    get().addToast({
      title: 'Telegram Disconnected',
      description: 'Bot link closed.',
      type: 'info',
    });
  },

  connectWhatsApp: async () => {
    const res = await whatsappService.simulateScan();
    if (res.success) {
      const status = await whatsappService.getStatus();
      set((state) => ({
        integrations: { ...state.integrations, whatsapp: status },
      }));
      get().addToast({
        title: 'WhatsApp Connected',
        description: res.message,
        type: 'success',
      });
    } else {
      get().addToast({
        title: 'WhatsApp Scan Failed',
        description: res.message,
        type: 'error',
      });
    }
    return res;
  },

  disconnectWhatsApp: async () => {
    await whatsappService.disconnect();
    const status = await whatsappService.getStatus();
    set((state) => ({
      integrations: { ...state.integrations, whatsapp: status },
    }));
    get().addToast({
      title: 'WhatsApp Disconnected',
      description: 'Headless bot unlinked.',
      type: 'info',
    });
  },

  connectAndroid: async () => {
    const res = await androidService.simulatePairing();
    if (res.success) {
      const status = await androidService.getStatus();
      set((state) => ({
        integrations: { ...state.integrations, android: status },
      }));
      get().addToast({
        title: 'Android Companion Paired',
        description: res.message,
        type: 'success',
      });
    } else {
      get().addToast({
        title: 'Android Pairing Failed',
        description: res.message,
        type: 'error',
      });
    }
    return res;
  },

  disconnectAndroid: async () => {
    await androidService.disconnect();
    const status = await androidService.getStatus();
    set((state) => ({
      integrations: { ...state.integrations, android: status },
    }));
    get().addToast({
      title: 'Android Unlinked',
      description: 'Voice call stream closed.',
      type: 'info',
    });
  },

  addTranscriptMessage: (msg) => {
    const newMessage: TranscriptMessage = {
      id: generateId('msg'),
      timestamp: formatTime(),
      ...msg,
    };
    set((state) => ({ transcript: [...state.transcript, newMessage] }));
  },

  sendUserQuery: async (text: string) => {
    if (!text.trim()) return;
    
    // Add user message locally for immediate feedback
    get().addTranscriptMessage({ sender: 'user', text });
    set({ voiceState: 'thinking' });
    
    // Send to backend via websocket
    const { wsService } = await import('../services/websocket');
    wsService.sendCommand(text);
  },

  triggerMockConversationStream: () => {
    const sampleConversations = [
      {
        user: "Arya, search my Memory Bank for Marcus's emergency number.",
        arya: "Found: Marcus Thorne (+1-555-019-9944), DevOps Escalation Lead.",
      },
      {
        user: "Can you queue the Q4 Architecture PDF for deep intent analysis?",
        arya: "Ingesting Q4 Architecture PDF into AI Reader. Extracting core diagrams and requirements.",
      },
      {
        user: "Check my remaining tasks for today.",
        arya: "You have 3 pending tasks: 'Review Q4 Architecture Proposal', 'Confirm Android Companion voice bitrate', and 'Sync with Sarah'.",
      },
    ];

    const chosen = sampleConversations[Math.floor(Math.random() * sampleConversations.length)];

    set({ voiceState: 'listening' });
    setTimeout(() => {
      get().addTranscriptMessage({ sender: 'user', text: chosen.user });
      set({ voiceState: 'thinking' });

      setTimeout(() => {
        set({ voiceState: 'speaking' });
        get().addTranscriptMessage({ sender: 'arya', text: chosen.arya });

        setTimeout(() => {
          set({ voiceState: 'idle' });
        }, 2500);
      }, 1400);
    }, 800);
  },

  loadMemories: async () => {
    const data = await memoryService.getMemories();
    set({ memories: data });
  },

  addMemoryItem: async (category, key, value, tags) => {
    const newItem = await memoryService.addMemory(category, key, value, tags);
    set((state) => ({ memories: [newItem, ...state.memories] }));
    get().addToast({
      title: 'Memory Stored',
      description: `Added "${key}" under ${category}.`,
      type: 'success',
    });
  },

  deleteMemoryItem: async (id) => {
    const success = await memoryService.deleteMemory(id);
    if (success) {
      set((state) => ({ memories: state.memories.filter((m) => m.id !== id) }));
      get().addToast({
        title: 'Memory Erased',
        description: 'Item removed from Supabase memory vault.',
        type: 'info',
      });
    }
  },

  setMemorySearchQuery: (memorySearchQuery) => set({ memorySearchQuery }),

  loadBriefing: async () => {
    const briefing = await briefingService.getBriefing();
    set({ briefing });
  },

  toggleBriefingTodo: async (id) => {
    await briefingService.toggleTodo(id);
    const briefing = await briefingService.getBriefing();
    set({ briefing });
  },

  addBriefingTodo: async (text) => {
    await briefingService.addTodo(text);
    const briefing = await briefingService.getBriefing();
    set({ briefing });
    get().addToast({
      title: 'Task Added',
      description: `New to-do created: "${text}"`,
      type: 'success',
    });
  },

  setMetrics: (metrics) => set({ metrics }),
}));
