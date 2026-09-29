export type VoiceState = 'idle' | 'listening' | 'thinking' | 'speaking';

export type IntegrationId = 'telegram' | 'whatsapp' | 'android';

export interface IntegrationStatus {
  connected: boolean;
  statusText?: string;
  connectedAt?: string;
  details?: Record<string, any>;
}

export interface TelegramConfig {
  botToken: string;
  botName: string;
  chatId: string;
}

export type MemoryCategory = 'Personal' | 'Work' | 'Preferences' | 'Contacts' | 'Important Dates';

export interface MemoryItem {
  id: string;
  category: MemoryCategory;
  key: string;
  value: string;
  updatedAt: string;
  tags?: string[];
}

export interface SystemMetricData {
  cpuUsage: number; // 0-100
  ramUsage: number; // 0-100
  ramUsedGB: number;
  ramTotalGB: number;
  diskUsage: number; // 0-100
  diskUsedGB: number;
  diskTotalGB: number;
  neuralLinkHealth: 'optimal' | 'degraded' | 'offline';
  networkHealth: 'optimal' | 'degraded' | 'offline';
  latencyMs: number;
}

export interface TranscriptMessage {
  id: string;
  sender: 'user' | 'arya' | 'system';
  text: string;
  timestamp: string;
  emotion?: string;
  isStreaming?: boolean;
}

export interface BriefingTodo {
  id: string;
  text: string;
  completed: boolean;
  priority?: 'low' | 'medium' | 'high';
}

export interface BriefingScheduleItem {
  id: string;
  time: string;
  title: string;
  location?: string;
  type: 'meeting' | 'task' | 'call';
}

export interface BriefingNewsItem {
  id: string;
  title: string;
  source: string;
  category: string;
  timeAgo: string;
}

export interface BriefingData {
  userName: string;
  time: string;
  date: string;
  location: string;
  weatherTemp: string;
  weatherCondition: string;
  weatherIcon: string;
  headlines: BriefingNewsItem[];
  todos: BriefingTodo[];
  schedule: BriefingScheduleItem[];
}

export interface DesktopAgentState {
  connected: boolean;
  version: string;
  hostname: string;
  lastHeartbeat: string;
}

export interface ToastNotification {
  id: string;
  title: string;
  description?: string;
  type: 'info' | 'success' | 'warning' | 'error';
  duration?: number;
}

export interface AnalyzedFile {
  id: string;
  name: string;
  size: number;
  type: string;
  path?: string;
  status: 'queued' | 'analyzing' | 'completed' | 'error';
  progress: number;
  summary?: string;
}

export type ActionModalType = 'none' | 'integrations' | 'telegram' | 'whatsapp' | 'android' | 'ai-reader';
