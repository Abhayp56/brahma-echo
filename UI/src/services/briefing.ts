import { IBriefingService } from './types';
import { BriefingData, BriefingTodo, BriefingScheduleItem } from '../types/arya';
import { generateId } from '../lib/utils';

/**
 * DailyBriefingService
 * Persists briefings per calendar day (brahma_briefing_YYYY-MM-DD).
 * Initializes once each day, carries over uncompleted tasks from yesterday,
 * and fetches real-time weather from the Cloud Brain.
 */
class PersistentDailyBriefingService implements IBriefingService {
  private getTodayKey(): string {
    const d = new Date();
    const year = d.getFullYear();
    const month = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `brahma_briefing_${year}-${month}-${day}`;
  }

  private loadSavedBriefing(key: string): BriefingData | null {
    try {
      const raw = localStorage.getItem(key);
      if (raw) return JSON.parse(raw);
    } catch (e) {
      console.warn('[Briefing] Failed to parse saved briefing:', e);
    }
    return null;
  }

  private saveBriefing(key: string, data: BriefingData): void {
    try {
      localStorage.setItem(key, JSON.stringify(data));
    } catch (e) {
      console.warn('[Briefing] Failed to save briefing to localStorage:', e);
    }
  }

  private getPreviousUncompletedTodos(): BriefingTodo[] {
    try {
      const keys = Object.keys(localStorage)
        .filter((k) => k.startsWith('brahma_briefing_'))
        .sort()
        .reverse();

      const todayKey = this.getTodayKey();
      for (const k of keys) {
        if (k !== todayKey) {
          const past = this.loadSavedBriefing(k);
          if (past && Array.isArray(past.todos)) {
            const unfinished = past.todos.filter((t) => !t.completed);
            if (unfinished.length > 0) {
              return unfinished;
            }
          }
        }
      }
    } catch (e) {
      // ignore
    }
    return [];
  }

  async getBriefing(): Promise<BriefingData> {
    const todayKey = this.getTodayKey();
    const now = new Date();
    const timeStr = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    const dateStr = now.toLocaleDateString([], { weekday: 'long', month: 'short', day: 'numeric' });

    let current = this.loadSavedBriefing(todayKey);

    if (!current) {
      // First run of the day: create brand new briefing entry for today
      const rolledOver = this.getPreviousUncompletedTodos();
      current = {
        userName: 'Operator',
        time: timeStr,
        date: dateStr,
        location: 'Local System',
        weatherTemp: '--°C',
        weatherCondition: 'Synchronizing...',
        weatherIcon: 'sun',
        headlines: [
          {
            id: 'h_1',
            title: 'Arya Cloud Neural Brain & Local Orchestration Online',
            source: 'Brahma Echo',
            category: 'System',
            timeAgo: 'Today',
          },
        ],
        todos: rolledOver.length > 0 ? rolledOver : [
          { id: generateId('todo'), text: 'Define daily system workflow & targets', completed: false, priority: 'high' }
        ],
        schedule: [],
      };
      this.saveBriefing(todayKey, current);
    } else {
      current.time = timeStr;
      current.date = dateStr;
    }

    // Refresh live weather from Cloud Brain
    try {
      const weatherRes = await fetch('/api/utility/weather');
      if (weatherRes.ok) {
        const wData = await weatherRes.json();
        if (wData.temperature !== undefined) {
          current.weatherTemp = `${Math.round(wData.temperature)}°C`;
          current.weatherCondition = wData.condition || 'Clear Sky';
          if (wData.location) current.location = wData.location;
          this.saveBriefing(todayKey, current);
        }
      }
    } catch (e) {
      // Keep cached weather on network error
    }

    return { ...current };
  }

  async toggleTodo(id: string): Promise<boolean> {
    const todayKey = this.getTodayKey();
    const current = this.loadSavedBriefing(todayKey);
    if (!current) return false;

    current.todos = current.todos.map((todo) =>
      todo.id === id ? { ...todo, completed: !todo.completed } : todo
    );
    this.saveBriefing(todayKey, current);
    return true;
  }

  async addTodo(text: string, priority: 'low' | 'medium' | 'high' = 'medium'): Promise<BriefingTodo> {
    const todayKey = this.getTodayKey();
    let current = this.loadSavedBriefing(todayKey);
    if (!current) {
      current = await this.getBriefing();
    }

    const newTodo: BriefingTodo = {
      id: generateId('todo'),
      text,
      completed: false,
      priority,
    };
    current.todos.push(newTodo);
    this.saveBriefing(todayKey, current);
    return newTodo;
  }

  async deleteTodo(id: string): Promise<boolean> {
    const todayKey = this.getTodayKey();
    const current = this.loadSavedBriefing(todayKey);
    if (!current) return false;

    current.todos = current.todos.filter((t) => t.id !== id);
    this.saveBriefing(todayKey, current);
    return true;
  }

  async addScheduleItem(time: string, title: string, location?: string): Promise<void> {
    const todayKey = this.getTodayKey();
    const current = this.loadSavedBriefing(todayKey);
    if (!current) return;

    const newItem: BriefingScheduleItem = {
      id: generateId('sch'),
      time,
      title,
      location: location || 'Workspace',
      type: 'task',
    };
    current.schedule.push(newItem);
    this.saveBriefing(todayKey, current);
  }
}

export const briefingService = new PersistentDailyBriefingService();
