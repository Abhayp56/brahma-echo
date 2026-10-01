import {
  TelegramConfig,
  IntegrationStatus,
  MemoryItem,
  MemoryCategory,
  BriefingData,
  BriefingTodo,
  SystemMetricData,
  DesktopAgentState,
  AnalyzedFile,
} from '../types/arya';

export interface ITelegramService {
  connect(config: TelegramConfig): Promise<{ success: boolean; message: string }>;
  disconnect(): Promise<{ success: boolean; message: string }>;
  getStatus(): Promise<IntegrationStatus>;
}

export interface IWhatsAppService {
  requestQRCode(): Promise<{ qrCodeValue: string }>;
  simulateScan(): Promise<{ success: boolean; message: string }>;
  disconnect(): Promise<{ success: boolean; message: string }>;
  getStatus(): Promise<IntegrationStatus>;
}

export interface IAndroidService {
  requestPairingData(): Promise<{ qrCodeValue: string; pairingCode: string }>;
  simulatePairing(): Promise<{ success: boolean; message: string }>;
  disconnect(): Promise<{ success: boolean; message: string }>;
  getStatus(): Promise<IntegrationStatus>;
}

export interface IMemoryService {
  getMemories(): Promise<MemoryItem[]>;
  addMemory(category: MemoryCategory, key: string, value: string, tags?: string[]): Promise<MemoryItem>;
  deleteMemory(id: string): Promise<boolean>;
  searchMemories(query: string): Promise<MemoryItem[]>;
}

export interface IBriefingService {
  getBriefing(): Promise<BriefingData>;
  toggleTodo(id: string): Promise<boolean>;
  addTodo(text: string, priority?: 'low' | 'medium' | 'high'): Promise<BriefingTodo>;
  deleteTodo?(id: string): Promise<boolean>;
  addScheduleItem?(time: string, title: string, location?: string): Promise<void>;
}

export interface IMetricsService {
  subscribeMetrics(callback: (metrics: SystemMetricData) => void): () => void;
}

export interface IDesktopAgentService {
  getStatus(): Promise<DesktopAgentState>;
  toggleConnection(connected?: boolean): Promise<DesktopAgentState>;
  executeCommand(action: 'gods-eye' | 'holographic-board' | 'ai-reader' | 'system-command', payload?: any): Promise<{ success: boolean; message: string }>;
}

export interface IAIReaderService {
  analyzeFiles(files: File[]): Promise<AnalyzedFile[]>;
}
