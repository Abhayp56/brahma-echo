import { IAndroidService } from './types';
import { IntegrationStatus } from '../types/arya';

class MockAndroidService implements IAndroidService {
  private status: IntegrationStatus = {
    connected: false,
    statusText: 'Disconnected',
  };

  async requestPairingData(): Promise<{ qrCodeValue: string; pairingCode: string }> {
    await new Promise((resolve) => setTimeout(resolve, 300));
    const randomCode = Math.floor(100000 + Math.random() * 900000).toString();
    return {
      qrCodeValue: `arya://pair-companion?code=${randomCode}&device=DesktopHost`,
      pairingCode: `${randomCode.slice(0, 3)}-${randomCode.slice(3)}`,
    };
  }

  async simulatePairing(): Promise<{ success: boolean; message: string }> {
    await new Promise((resolve) => setTimeout(resolve, 1800));

    this.status = {
      connected: true,
      statusText: 'Connected (Pixel 8 Pro)',
      connectedAt: new Date().toISOString(),
      details: {
        deviceName: 'Pixel 8 Pro',
        battery: '88%',
        duplexAudioActive: true,
      },
    };

    return {
      success: true,
      message: 'Android Companion App linked! Full-duplex phone voice stream active.',
    };
  }

  async disconnect(): Promise<{ success: boolean; message: string }> {
    await new Promise((resolve) => setTimeout(resolve, 300));
    this.status = {
      connected: false,
      statusText: 'Disconnected',
    };
    return {
      success: true,
      message: 'Android companion app unlinked.',
    };
  }

  async getStatus(): Promise<IntegrationStatus> {
    return this.status;
  }
}

export const androidService = new MockAndroidService();
