import { IWhatsAppService } from './types';
import { IntegrationStatus } from '../types/arya';

class WhatsAppService implements IWhatsAppService {
  async requestQRCode(): Promise<{ qrCodeValue: string }> {
    try {
      const res = await fetch('/api/whatsapp/qr');
      const data = await res.json();
      return { qrCodeValue: data.qr_data_url || '' };
    } catch (e) {
      return { qrCodeValue: '' };
    }
  }

  async simulateScan(): Promise<{ success: boolean; message: string }> {
    try {
      const res = await fetch('/api/whatsapp/qr');
      const data = await res.json();
      return {
        success: Boolean(data.qr_data_url || data.status === 'authenticated'),
        message: data.status === 'authenticated' ? 'Authenticated' : 'QR ready',
      };
    } catch (e) {
      return { success: false, message: 'Could not connect to WhatsApp gateway' };
    }
  }

  async disconnect(): Promise<{ success: boolean; message: string }> {
    try {
      const res = await fetch('/api/whatsapp/disconnect', { method: 'POST' });
      return { success: res.ok, message: 'Disconnected' };
    } catch (e) {
      return { success: false, message: 'Network error' };
    }
  }

  async getStatus(): Promise<IntegrationStatus> {
    try {
      const res = await fetch('/api/whatsapp/status');
      const data = await res.json();
      const isAuth = data.status === 'authenticated' || data.is_connected === true;
      return {
        connected: isAuth,
        statusText: isAuth ? 'Authenticated' : (data.status || 'Disconnected'),
      };
    } catch (e) {
      return { connected: false, statusText: 'Disconnected' };
    }
  }
}

export const whatsappService = new WhatsAppService();

