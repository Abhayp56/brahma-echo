import { IWhatsAppService } from './types';
import { IntegrationStatus } from '../types/arya';

class MockWhatsAppService implements IWhatsAppService {
  private status: IntegrationStatus = {
    connected: false,
    statusText: 'Disconnected',
  };

  async requestQRCode(): Promise<{ qrCodeValue: string }> {
    await new Promise((resolve) => setTimeout(resolve, 300));
    const token = `arya_wa_session_${Math.random().toString(36).substring(2, 10)}_${Date.now()}`;
    return {
      qrCodeValue: `https://arya.ai/wa-auth?session=${token}`,
    };
  }

  async simulateScan(): Promise<{ success: boolean; message: string }> {
    // 85% chance of success to test error flows cleanly
    const isSuccess = Math.random() > 0.15;
    await new Promise((resolve) => setTimeout(resolve, 1500));

    if (isSuccess) {
      this.status = {
        connected: true,
        statusText: 'Connected (Headless Web Bot)',
        connectedAt: new Date().toISOString(),
        details: {
          phoneNumber: '+1 (555) 019-2834',
          sessionActive: true,
        },
      };
      return {
        success: true,
        message: 'WhatsApp Headless Bot paired successfully! Arya is now listening for incoming messages.',
      };
    } else {
      return {
        success: false,
        message: 'QR code scan timed out or device rejected pairing. Please try scanning again.',
      };
    }
  }

  async disconnect(): Promise<{ success: boolean; message: string }> {
    await new Promise((resolve) => setTimeout(resolve, 300));
    this.status = {
      connected: false,
      statusText: 'Disconnected',
    };
    return {
      success: true,
      message: 'WhatsApp bot unlinked.',
    };
  }

  async getStatus(): Promise<IntegrationStatus> {
    return this.status;
  }
}

export const whatsappService = new MockWhatsAppService();
