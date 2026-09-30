import { IAndroidService } from './types';
import { IntegrationStatus } from '../types/arya';

class AndroidService implements IAndroidService {
  async requestPairingData(): Promise<{ qrCodeValue: string; pairingCode: string }> {
    try {
      const res = await fetch('/api/phone/qr');
      const data = await res.json();
      return {
        qrCodeValue: data.qr_data_url || 'https://brahma-connect',
        pairingCode: data.code || 'CLOUD',
      };
    } catch (e) {
      return { qrCodeValue: '', pairingCode: 'OFFLINE' };
    }
  }

  async simulatePairing(): Promise<{ success: boolean; message: string }> {
    try {
      const res = await fetch('/api/phone/status');
      const data = await res.json();
      return {
        success: Boolean(data.connected),
        message: data.connected ? 'Phone companion online' : 'Scan the QR code with Brahma Connect',
      };
    } catch (e) {
      return { success: false, message: 'Could not connect to cloud server' };
    }
  }

  async triggerCall(reason?: string): Promise<{ success: boolean; message: string }> {
    try {
      const res = await fetch('/api/phone/call', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ caller: 'JARVIS', reason: reason || 'Voice Call from Web UI' }),
      });
      const data = await res.json();
      return { success: res.ok, message: data.message || 'Call triggered' };
    } catch (e: any) {
      return { success: false, message: e.message || 'Call error' };
    }
  }

  async disconnect(): Promise<{ success: boolean; message: string }> {
    return { success: true, message: 'Disconnected' };
  }

  async getStatus(): Promise<IntegrationStatus> {
    try {
      const res = await fetch('/api/phone/status');
      const data = await res.json();
      const isOnline = Boolean(data.connected);
      return {
        connected: isOnline,
        statusText: isOnline ? 'Connected via Cloud WSS' : 'Disconnected',
        details: data.phone_info,
      };
    } catch (e) {
      return { connected: false, statusText: 'Disconnected' };
    }
  }
}

export const androidService = new AndroidService();

