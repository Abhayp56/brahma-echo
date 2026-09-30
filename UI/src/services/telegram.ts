import { ITelegramService } from './types';
import { TelegramConfig, IntegrationStatus } from '../types/arya';

class TelegramService implements ITelegramService {
  async connect(config: TelegramConfig): Promise<{ success: boolean; message: string }> {
    try {
      const res = await fetch('/api/telegram/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config)
      });
      const data = await res.json();
      return { success: res.ok, message: data.message || 'Configured telegram' };
    } catch (e) {
      return { success: false, message: 'Network error' };
    }
  }

  async disconnect(): Promise<{ success: boolean; message: string }> {
    return { success: false, message: 'Not supported' };
  }

  async getStatus(): Promise<IntegrationStatus> {
    try {
      const res = await fetch('/api/telegram/status');
      const data = await res.json();
      return {
        connected: data.configured,
        statusText: data.configured ? `Bot Token: ${data.bot_token.substring(0, 10)}...` : 'Disconnected',
      };
    } catch (e) {
      return { connected: false, statusText: 'Disconnected' };
    }
  }
}
export const telegramService = new TelegramService();
