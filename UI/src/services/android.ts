import { IAndroidService } from './types';
import { IntegrationStatus } from '../types/arya';

class AndroidService implements IAndroidService {
  async requestPairingData(): Promise<{ qrCodeValue: string; pairingCode: string }> {
    return { qrCodeValue: 'dummy_qr_code', pairingCode: '123456' };
  }
  async simulatePairing(): Promise<{ success: boolean; message: string }> {
    try {
        const res = await fetch('/api/phone/qr');
        const data = await res.json();
        return { success: res.ok, message: data.message || 'Ready' };
    } catch(e) { return { success: false, message: 'Error' }; }
  }
  async disconnect(): Promise<{ success: boolean; message: string }> {
    return { success: false, message: 'Not supported' };
  }
  async getStatus(): Promise<IntegrationStatus> {
    try {
      const res = await fetch('/api/phone/status');
      const data = await res.json();
      return { connected: data.status === 'online', statusText: data.status === 'online' ? 'Connected via WSS' : 'Disconnected' };
    } catch (e) {
      return { connected: false, statusText: 'Disconnected' };
    }
  }
}
export const androidService = new AndroidService();
