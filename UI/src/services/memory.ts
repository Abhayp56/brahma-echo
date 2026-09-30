import { IMemoryService } from './types';
import { MemoryItem, MemoryCategory } from '../types/arya';

class MemoryService implements IMemoryService {
  async searchMemories(query: string): Promise<MemoryItem[]> {
    return [];
  }
  async getMemories(): Promise<MemoryItem[]> {
    try {
      const res = await fetch('/api/memories');
      const data = await res.json();
      if (data.memories) {
          return data.memories.map((m: any) => ({
              id: m.id || m.key,
              category: m.category || 'Personal',
              key: m.key,
              value: m.value,
              tags: m.tags || [],
              updatedAt: m.updated_at || 'Just now'
          }));
      }
      return [];
    } catch (e) {
      return [];
    }
  }

  async addMemory(category: MemoryCategory, key: string, value: string, tags?: string[]): Promise<MemoryItem> {
    const res = await fetch('/api/memories', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ category, key, value, tags: tags || [] })
    });
    const data = await res.json();
    return { id: data.id || key, category, key, value, tags, updatedAt: 'Just now' } as MemoryItem;
  }

  async deleteMemory(id: string): Promise<boolean> {
    try {
        const res = await fetch(`/api/memories?id=${id}`, { method: 'DELETE' });
        return res.ok;
    } catch(e) { return false; }
  }
}
export const memoryService = new MemoryService();
