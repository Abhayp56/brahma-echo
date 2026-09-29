import { ITelegramService } from './types';
import { TelegramConfig, IntegrationStatus } from '../types/arya';

class MockTelegramService implements ITelegramService {
  private status: IntegrationStatus = {
    connected: false,
    statusText: 'Disconnected',
  };

  async connect(config: TelegramConfig): Promise<{ success: boolean; message: string }> {
    // Validate empty fields
    if (!config.botToken.trim() || !config.botName.trim() || !config.chatId.trim()) {
      return {
        success: false,
        message: 'Please fill in all required Telegram bot fields.',
      };
    }

    if (!config.botToken.includes(':')) {
      return {
        success: false,
        message: 'Invalid Telegram bot token format. Token must contain a colon (e.g., 123456:ABC...).',
      };
    }

    // Simulate connection delay
    await new Promise((resolve) => setTimeout(resolve, 800));

    this.status = {
      connected: true,
      statusText: `Connected to @${config.botName.replace(/^@/, '')}`,
      connectedAt: new Date().toISOString(),
      details: {
        botName: config.botName,
        chatId: config.chatId,
      },
    };

    return {
      success: true,
      message: `Telegram bot @${config.botName} linked successfully! Notifications active.`,
    };
  }

  async disconnect(): Promise<{ success: boolean; message: string }> {
    await new Promise((resolve) => setTimeout(resolve, 400));
    this.status = {
      connected: false,
      statusText: 'Disconnected',
    };
    return {
      success: true,
      message: 'Telegram integration disconnected.',
    };
  }

  async getStatus(): Promise<IntegrationStatus> {
    return this.status;
  }
}

export const telegramService = new MockTelegramService();
