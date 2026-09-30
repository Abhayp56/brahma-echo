import { IWhatsAppService } from './types';
import { IntegrationStatus } from '../types/arya';

class WhatsAppService implements IWhatsAppService {
  async requestQRCode(): Promise<{ qrCodeValue: string }> {
    return { qrCodeValue: 'dummy_wa_qr_code' };
  }
  async simulateScan(): Promise<{ success: boolean; message: string }> {
    try {
        const res = await fetch('/api/whatsapp/qr');
        const data = await res.json();
        return { success: res.ok, message: data.message || 'QR ready' };
    } catch(e) { return { success: false, message: 'Network error'}; }
  }
  async disconnect(): Promise<{ success: boolean; message: string }> {
    try {
        const res = await fetch('/api/whatsapp/disconnect', { method: 'POST' });
        return { success: res.ok, message: 'Disconnected' };
    } catch(e) { return { success: false, message: 'Network error'}; }
  }
  async getStatus(): Promise<IntegrationStatus> {
    try {
      const res = await fetch('/api/whatsapp/status');
      const data = await res.json();
      return { connected: data.status === 'authenticated', statusText: data.status };
    } catch (e) {
      return { connected: false, statusText: 'Disconnected' };
    }
  }
}
export const whatsappService = new WhatsAppService();
