import { IMemoryService } from './types';
import { MemoryItem, MemoryCategory } from '../types/arya';

class MemoryService implements IMemoryService {
  async searchMemories(query: string): Promise<MemoryItem[]> {
    const all = await this.getMemories();
    if (!query.trim()) return all;
    const q = query.toLowerCase();
    return all.filter(
      (m) =>
        m.key.toLowerCase().includes(q) ||
        m.value.toLowerCase().includes(q) ||
        m.category.toLowerCase().includes(q)
    );
  }

  async getMemories(): Promise<MemoryItem[]> {
    try {
      const res = await fetch('/api/memories');
      const data = await res.json();
      if (!data || !data.memories) return [];

      if (Array.isArray(data.memories)) {
        return data.memories.map((m: any) => ({
          id: m.id || `${m.category || 'notes'}:::${m.key}`,
          category: (m.category as MemoryCategory) || 'notes',
          key: m.key,
          value: typeof m.value === 'object' && m.value?.value ? m.value.value : String(m.value || ''),
          tags: m.tags || [],
          updatedAt: m.updated_at || m.updated || 'Recent',
        }));
      }

      if (typeof data.memories === 'object') {
        const result: MemoryItem[] = [];
        for (const [category, items] of Object.entries(data.memories)) {
          if (!items || typeof items !== 'object') continue;
          for (const [k, v] of Object.entries(items as Record<string, any>)) {
            const val = typeof v === 'object' && v?.value ? v.value : String(v || '');
            const upd = typeof v === 'object' && v?.updated ? v.updated : 'Saved';
            result.push({
              id: `${category}:::${k}`,
              category: category as MemoryCategory,
              key: k,
              value: val,
              tags: [],
              updatedAt: upd,
            });
          }
        }
        return result;
      }
      return [];
    } catch (e) {
      console.warn('[MemoryService] getMemories error:', e);
      return [];
    }
  }

  async addMemory(category: MemoryCategory, key: string, value: string, tags?: string[]): Promise<MemoryItem> {
    const res = await fetch('/api/memories', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ category, key, value, tags: tags || [] }),
    });
    const data = await res.json();
    return {
      id: `${category}:::${key}`,
      category,
      key,
      value,
      tags: tags || [],
      updatedAt: 'Just now',
    } as MemoryItem;
  }

  async deleteMemory(id: string): Promise<boolean> {
    try {
      let url = `/api/memories?id=${encodeURIComponent(id)}`;
      if (id.includes(':::')) {
        const [cat, key] = id.split(':::');
        url = `/api/memories?category=${encodeURIComponent(cat)}&key=${encodeURIComponent(key)}`;
      } else {
        url = `/api/memories?category=notes&key=${encodeURIComponent(id)}`;
      }
      const res = await fetch(url, { method: 'DELETE' });
      return res.ok;
    } catch (e) {
      return false;
    }
  }
}

export const memoryService = new MemoryService();

