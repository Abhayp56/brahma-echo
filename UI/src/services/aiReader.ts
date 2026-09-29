import { IAIReaderService } from './types';
import { AnalyzedFile } from '../types/arya';
import { generateId, formatBytes } from '../lib/utils';

class MockAIReaderService implements IAIReaderService {
  async analyzeFiles(files: File[]): Promise<AnalyzedFile[]> {
    return files.map((file) => ({
      id: generateId('file'),
      name: file.name,
      size: file.size,
      type: file.type || 'document',
      status: 'queued',
      progress: 0,
    }));
  }
}

export const aiReaderService = new MockAIReaderService();
