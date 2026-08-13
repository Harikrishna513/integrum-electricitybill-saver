"use client";

import { useRef, useState } from "react";

type UploadMode = "single" | "multiple";

type QueuedFile = {
  id: string;
  file: File;
};

type Props = {
  disabled?: boolean;
  onUploadSingle: (file: File) => Promise<void>;
  onUploadMultiple: (files: File[]) => Promise<void>;
};

export function UploadPanel({ disabled, onUploadSingle, onUploadMultiple }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [mode, setMode] = useState<UploadMode>("single");
  const [queue, setQueue] = useState<QueuedFile[]>([]);
  const [dragOver, setDragOver] = useState(false);

  function addFiles(fileList: FileList | null) {
    if (!fileList?.length) return;
    const next = Array.from(fileList).map((file) => ({
      id: `${file.name}-${file.size}-${file.lastModified}`,
      file,
    }));
    setQueue((prev) => {
      const seen = new Set(prev.map((q) => q.id));
      return [...prev, ...next.filter((q) => !seen.has(q.id))];
    });
  }

  function removeFile(id: string) {
    setQueue((prev) => prev.filter((q) => q.id !== id));
  }

  async function startUpload() {
    if (!queue.length) return;
    if (mode === "single") {
      await onUploadSingle(queue[0].file);
    } else {
      await onUploadMultiple(queue.map((q) => q.file));
    }
  }

  return (
    <div className="upload-panel">
      <div className="mode-toggle" role="tablist" aria-label="Upload mode">
        <button
          type="button"
          role="tab"
          aria-selected={mode === "single"}
          className={mode === "single" ? "active" : ""}
          onClick={() => {
            setMode("single");
            setQueue((q) => q.slice(0, 1));
          }}
        >
          Single bill
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={mode === "multiple"}
          className={mode === "multiple" ? "active" : ""}
          onClick={() => setMode("multiple")}
        >
          Multiple bills
        </button>
      </div>

      <div
        className={`dropzone ${dragOver ? "drag-over" : ""}`}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          addFiles(e.dataTransfer.files);
        }}
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") inputRef.current?.click();
        }}
        role="button"
        tabIndex={0}
        aria-label="Upload electricity bill"
      >
        <div className="dropzone-icon" aria-hidden>
          ↑
        </div>
        <p className="dropzone-title">Drop your bill here or click to upload</p>
        <p className="dropzone-hint">PDF, JPG, JPEG, PNG · Karnataka BESCOM domestic</p>
        <input
          ref={inputRef}
          type="file"
          accept="image/jpeg,image/jpg,image/png,application/pdf,.pdf"
          multiple={mode === "multiple"}
          hidden
          onChange={(e) => addFiles(e.target.files)}
        />
      </div>

      {queue.length > 0 && (
        <ul className="file-queue">
          {queue.map((item) => (
            <li key={item.id}>
              <div>
                <strong>{item.file.name}</strong>
                <span>{Math.round(item.file.size / 1024)} KB</span>
              </div>
              <button
                type="button"
                className="ghost"
                onClick={() => removeFile(item.id)}
                aria-label={`Remove ${item.file.name}`}
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}

      <button
        type="button"
        className="cta"
        disabled={disabled || queue.length === 0}
        onClick={() => void startUpload()}
      >
        {disabled ? "Processing…" : "Analyze bill"}
      </button>
    </div>
  );
}
