import React, { useState, useRef } from 'react';
import { UploadCloud, FileText, CheckCircle2, Loader2, Trash2, FolderPlus } from 'lucide-react';
import { Modal } from '../ui/Modal';
import { GlassButton } from '../ui/GlassButton';
import { useAryaStore } from '../../store/useAryaStore';
import { AnalyzedFile } from '../../types/arya';
import { formatBytes, generateId } from '../../lib/utils';
import { aiReaderService } from '../../services';

export const AIReaderModal: React.FC = () => {
  const activeModal = useAryaStore((s) => s.activeModal);
  const setActiveModal = useAryaStore((s) => s.setActiveModal);
  const addToast = useAryaStore((s) => s.addToast);
  const sendUserQuery = useAryaStore((s) => s.sendUserQuery);

  const [files, setFiles] = useState<AnalyzedFile[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const isOpen = activeModal === 'ai-reader';

  const handleClose = () => {
    setActiveModal('none');
  };

  const handleAddFiles = (newFiles: FileList | File[]) => {
    const fileListArray = Array.from(newFiles);
    const mapped: AnalyzedFile[] = fileListArray.map((f) => ({
      id: generateId('file'),
      name: f.name,
      size: f.size,
      type: f.type || 'document',
      status: 'queued',
      progress: 0,
    }));
    setFiles((prev) => [...prev, ...mapped]);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleAddFiles(e.dataTransfer.files);
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      handleAddFiles(e.target.files);
    }
  };

  const removeFile = (id: string) => {
    setFiles((prev) => prev.filter((f) => f.id !== id));
  };

  const startAnalysis = async () => {
    if (files.length === 0) return;
    setIsAnalyzing(true);

    // Simulate progressive analysis for each file
    for (let i = 0; i <= 100; i += 20) {
      await new Promise((res) => setTimeout(res, 250));
      setFiles((prev) =>
        prev.map((f) => ({
          ...f,
          status: i === 100 ? 'completed' : 'analyzing',
          progress: i,
        }))
      );
    }

    setIsAnalyzing(false);

    const fileNames = files.map((f) => f.name).join(', ');
    addToast({
      title: 'AI Analysis Complete',
      description: `Ingested & extracted insights from: ${fileNames}`,
      type: 'success',
    });

    sendUserQuery(`Analyze ingested files: ${fileNames}`);
    handleClose();
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      title="AI Reader & Document Analyser"
      subtitle="Ingest PDF, Markdown, JSON, or codebase files for automated intent analysis"
      maxWidth="xl"
    >
      <div className="space-y-5">
        {/* Drop Zone */}
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setIsDragging(true);
          }}
          onDragLeave={() => setIsDragging(false)}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
          className={`glass-panel border-dashed p-8 rounded-2xl flex flex-col items-center justify-center text-center cursor-pointer transition-all ${
            isDragging
              ? 'border-white/50 bg-white/10 shadow-[0_0_25px_rgba(255,255,255,0.15)]'
              : 'border-white/20 hover:border-white/35 hover:bg-white/5'
          }`}
        >
          <input
            ref={fileInputRef}
            type="file"
            multiple
            className="hidden"
            onChange={handleFileSelect}
          />
          <div className="w-12 h-12 rounded-xl glass-panel border-white/20 flex items-center justify-center mb-3">
            <UploadCloud className="w-6 h-6 text-white" />
          </div>
          <h4 className="text-sm font-semibold text-white">
            Drag & drop files or click to browse
          </h4>
          <p className="text-xs text-zinc-400 mt-1">
            Supports PDF, DOCX, TXT, JSON, MD, or project directories
          </p>
        </div>

        {/* Selected File List */}
        {files.length > 0 && (
          <div className="space-y-2.5 max-h-48 overflow-y-auto pr-1">
            <div className="flex items-center justify-between text-xs font-mono text-zinc-400">
              <span>QUEUED FILES ({files.length})</span>
              <button
                onClick={() => setFiles([])}
                className="text-rose-400 hover:underline cursor-pointer"
              >
                Clear all
              </button>
            </div>

            {files.map((file) => (
              <div
                key={file.id}
                className="glass-panel p-3 rounded-xl flex items-center justify-between border-white/10 text-xs"
              >
                <div className="flex items-center gap-3 min-w-0 flex-1">
                  <FileText className="w-4 h-4 text-zinc-300 shrink-0" />
                  <div className="min-w-0 flex-1">
                    <div className="text-white font-medium truncate">{file.name}</div>
                    <div className="text-[10px] text-zinc-400 font-mono">
                      {formatBytes(file.size)} • Status: {file.status}
                    </div>
                  </div>
                </div>

                {/* Progress bar / Delete button */}
                <div className="flex items-center gap-3 ml-3">
                  {isAnalyzing && (
                    <div className="w-24 bg-white/10 h-1.5 rounded-full overflow-hidden">
                      <div
                        className="bg-white h-full transition-all duration-200"
                        style={{ width: `${file.progress}%` }}
                      />
                    </div>
                  )}

                  {file.status === 'completed' ? (
                    <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                  ) : isAnalyzing ? (
                    <Loader2 className="w-4 h-4 text-white animate-spin" />
                  ) : (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        removeFile(file.id);
                      }}
                      className="text-zinc-400 hover:text-rose-400 transition-colors p-1"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Actions Footer */}
        <div className="flex items-center justify-end gap-3 pt-3 border-t border-white/10">
          <GlassButton onClick={handleClose} variant="ghost">
            Cancel
          </GlassButton>
          <GlassButton
            onClick={startAnalysis}
            variant="silver"
            disabled={files.length === 0 || isAnalyzing}
            icon={isAnalyzing ? <Loader2 className="w-4 h-4 animate-spin" /> : <FolderPlus className="w-4 h-4" />}
          >
            {isAnalyzing ? 'Analysing Documents...' : `Analyse (${files.length})`}
          </GlassButton>
        </div>
      </div>
    </Modal>
  );
};

export const AIReaderButton: React.FC = () => {
  const setActiveModal = useAryaStore((s) => s.setActiveModal);

  return (
    <GlassButton
      icon={<FileText className="w-4 h-4 text-white" />}
      onClick={() => setActiveModal('ai-reader')}
      variant="default"
      size="md"
    >
      AI Reader & Analyser
    </GlassButton>
  );
};
