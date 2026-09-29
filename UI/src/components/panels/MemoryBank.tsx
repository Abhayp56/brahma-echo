import React, { useEffect, useState } from 'react';
import { Database, Search, Plus, ChevronDown, ChevronRight, Trash2, Tag } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { GlassCard } from '../ui/GlassCard';
import { GlassButton } from '../ui/GlassButton';
import { Modal } from '../ui/Modal';
import { useAryaStore } from '../../store/useAryaStore';
import { MemoryCategory } from '../../types/arya';

const CATEGORIES: MemoryCategory[] = [
  'Personal',
  'Work',
  'Preferences',
  'Contacts',
  'Important Dates',
];

export const MemoryBank: React.FC = () => {
  const memories = useAryaStore((s) => s.memories);
  const loadMemories = useAryaStore((s) => s.loadMemories);
  const addMemoryItem = useAryaStore((s) => s.addMemoryItem);
  const deleteMemoryItem = useAryaStore((s) => s.deleteMemoryItem);
  const memorySearchQuery = useAryaStore((s) => s.memorySearchQuery);
  const setMemorySearchQuery = useAryaStore((s) => s.setMemorySearchQuery);

  const [expandedCategories, setExpandedCategories] = useState<Record<string, boolean>>({
    Personal: true,
    Work: true,
    Preferences: false,
    Contacts: false,
    'Important Dates': false,
  });

  const [showAddModal, setShowAddModal] = useState(false);
  const [newCat, setNewCat] = useState<MemoryCategory>('Personal');
  const [newKey, setNewKey] = useState('');
  const [newValue, setNewValue] = useState('');
  const [newTags, setNewTags] = useState('');

  useEffect(() => {
    loadMemories();
  }, [loadMemories]);

  const toggleCategory = (cat: string) => {
    setExpandedCategories((prev) => ({ ...prev, [cat]: !prev[cat] }));
  };

  const handleAddSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newKey.trim() || !newValue.trim()) return;

    const parsedTags = newTags
      .split(',')
      .map((t) => t.trim())
      .filter(Boolean);

    await addMemoryItem(newCat, newKey.trim(), newValue.trim(), parsedTags);
    setNewKey('');
    setNewValue('');
    setNewTags('');
    setShowAddModal(false);
  };

  const filteredMemories = memories.filter((m) => {
    if (!memorySearchQuery.trim()) return true;
    const q = memorySearchQuery.toLowerCase();
    return (
      m.key.toLowerCase().includes(q) ||
      m.value.toLowerCase().includes(q) ||
      m.category.toLowerCase().includes(q) ||
      m.tags?.some((t) => t.toLowerCase().includes(q))
    );
  });

  return (
    <GlassCard
      title="Supabase Memory Vault"
      icon={<Database className="w-4 h-4 text-white" />}
      action={
        <GlassButton
          onClick={() => setShowAddModal(true)}
          variant="ghost"
          size="sm"
          icon={<Plus className="w-3.5 h-3.5" />}
        >
          Add Memory
        </GlassButton>
      }
      className="w-full"
    >
      <div className="space-y-3">
        {/* Search Input Box */}
        <div className="relative">
          <Search className="w-3.5 h-3.5 text-zinc-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={memorySearchQuery}
            onChange={(e) => setMemorySearchQuery(e.target.value)}
            placeholder="Search categories, keys, or tags..."
            className="glass-input w-full pl-9 pr-3 py-1.5 rounded-xl text-xs placeholder-zinc-400 font-sans"
          />
        </div>

        {/* Categories Accordion */}
        <div className="space-y-2 max-h-80 overflow-y-auto pr-1">
          {CATEGORIES.map((category) => {
            const items = filteredMemories.filter((m) => m.category === category);
            const isExpanded = expandedCategories[category] || memorySearchQuery.length > 0;

            return (
              <div key={category} className="glass-panel rounded-xl border-white/10 overflow-hidden">
                <button
                  onClick={() => toggleCategory(category)}
                  className="w-full px-3.5 py-2.5 flex items-center justify-between text-xs font-semibold text-white bg-white/5 hover:bg-white/10 transition-colors cursor-pointer"
                >
                  <div className="flex items-center gap-2">
                    <motion.div
                      animate={{ rotate: isExpanded ? 90 : 0 }}
                      transition={{ duration: 0.2 }}
                    >
                      <ChevronRight className="w-3.5 h-3.5 text-zinc-400" />
                    </motion.div>
                    <span>{category}</span>
                  </div>
                  <motion.span
                    key={items.length}
                    initial={{ scale: 0.8, opacity: 0.5 }}
                    animate={{ scale: 1, opacity: 1 }}
                    className="px-2 py-0.5 rounded-full bg-white/10 text-[10px] font-mono text-zinc-300"
                  >
                    {items.length} items
                  </motion.span>
                </button>

                {/* Animated Accordion Height */}
                <AnimatePresence initial={false}>
                  {isExpanded && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.25, ease: 'easeInOut' }}
                      className="overflow-hidden"
                    >
                      <div className="p-2 space-y-1.5 border-t border-white/10">
                        {items.length === 0 ? (
                          <div className="text-[11px] text-zinc-400 text-center py-2 font-mono">
                            No memory records found.
                          </div>
                        ) : (
                          items.map((item) => (
                            <motion.div
                              key={item.id}
                              initial={{ opacity: 0, y: 6 }}
                              animate={{ opacity: 1, y: 0 }}
                              exit={{ opacity: 0, scale: 0.95 }}
                              className="glass-panel p-2.5 rounded-lg border-white/10 text-xs flex items-start justify-between group hover:bg-white/10 transition-colors"
                            >
                              <div className="flex-1 pr-2 min-w-0">
                                <div className="flex items-center justify-between gap-2">
                                  <span className="text-white font-semibold truncate">{item.key}</span>
                                  <span className="text-[9px] text-zinc-400 font-mono shrink-0">
                                    {item.updatedAt}
                                  </span>
                                </div>
                                <div className="text-zinc-300 mt-0.5 leading-relaxed break-words text-[11px]">
                                  {item.value}
                                </div>

                                {item.tags && item.tags.length > 0 && (
                                  <div className="flex items-center gap-1.5 mt-1.5 flex-wrap">
                                    {item.tags.map((tag) => (
                                      <span
                                        key={tag}
                                        className="inline-flex items-center gap-1 px-1.5 py-0.2 rounded bg-white/5 text-[9px] font-mono text-zinc-400 border border-white/5"
                                      >
                                        <Tag className="w-2.5 h-2.5" />
                                        {tag}
                                      </span>
                                    ))}
                                  </div>
                                )}
                              </div>

                              <button
                                onClick={() => deleteMemoryItem(item.id)}
                                className="p-1 text-zinc-400 hover:text-rose-400 transition-colors opacity-0 group-hover:opacity-100 cursor-pointer shrink-0"
                                title="Delete memory item"
                              >
                                <Trash2 className="w-3.5 h-3.5" />
                              </button>
                            </motion.div>
                          ))
                        )}
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            );
          })}
        </div>
      </div>

      {/* Add Memory Modal */}
      <Modal
        isOpen={showAddModal}
        onClose={() => setShowAddModal(false)}
        title="Add Memory Record"
        subtitle="Persist intent parameters or user preferences to Supabase memory store"
        maxWidth="md"
      >
        <form onSubmit={handleAddSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-mono text-zinc-300 uppercase tracking-wider mb-1.5">
              Category
            </label>
            <select
              value={newCat}
              onChange={(e) => setNewCat(e.target.value as MemoryCategory)}
              className="glass-input w-full px-3.5 py-2 rounded-xl text-xs text-white"
            >
              {CATEGORIES.map((c) => (
                <option key={c} value={c} className="bg-zinc-900 text-white">
                  {c}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs font-mono text-zinc-300 uppercase tracking-wider mb-1.5">
              Memory Key / Title
            </label>
            <input
              type="text"
              value={newKey}
              onChange={(e) => setNewKey(e.target.value)}
              placeholder="e.g. Preferred Flight Seat"
              className="glass-input w-full px-3.5 py-2 rounded-xl text-xs placeholder-zinc-400"
            />
          </div>

          <div>
            <label className="block text-xs font-mono text-zinc-300 uppercase tracking-wider mb-1.5">
              Value / Description
            </label>
            <textarea
              value={newValue}
              onChange={(e) => setNewValue(e.target.value)}
              placeholder="e.g. Aisle seat near front exit on all long-haul flights"
              rows={3}
              className="glass-input w-full px-3.5 py-2 rounded-xl text-xs placeholder-zinc-400 resize-none"
            />
          </div>

          <div>
            <label className="block text-xs font-mono text-zinc-300 uppercase tracking-wider mb-1.5">
              Tags (comma separated)
            </label>
            <input
              type="text"
              value={newTags}
              onChange={(e) => setNewTags(e.target.value)}
              placeholder="travel, preferences, priority"
              className="glass-input w-full px-3.5 py-2 rounded-xl text-xs placeholder-zinc-400"
            />
          </div>

          <div className="flex items-center justify-end gap-3 pt-3 border-t border-white/10">
            <GlassButton type="button" onClick={() => setShowAddModal(false)} variant="ghost">
              Cancel
            </GlassButton>
            <GlassButton type="submit" variant="silver">
              Save Memory
            </GlassButton>
          </div>
        </form>
      </Modal>
    </GlassCard>
  );
};
