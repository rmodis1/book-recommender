"use client";

import { useEffect, useState } from "react";
import { API_URL } from "@/lib/env";

interface BookDetailModalProps {
  subject: string;
  onClose: () => void;
}

export function BookDetailModal({ subject, onClose }: BookDetailModalProps) {
  const [detail, setDetail] = useState<string | null>(null);
  const [error, setError] = useState(false);

  // Fetch detail on mount; abort if modal is closed early
  useEffect(() => {
    const controller = new AbortController();

    fetch(`${API_URL}/api/book-detail`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ subject }),
      signal: controller.signal,
    })
      .then((res) => {
        if (!res.ok) throw new Error("Network error");
        return res.json();
      })
      .then((data: { detail: string }) => setDetail(data.detail))
      .catch((err: Error) => {
        if (err.name !== "AbortError") setError(true);
      });

    return () => controller.abort();
  }, [subject]);

  // Close on Escape key
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
    >
      <div
        className="relative bg-white dark:bg-zinc-900 rounded-2xl shadow-2xl max-w-lg w-full p-6 max-h-[80vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200 transition-colors text-lg leading-none"
          aria-label="Close"
        >
          ✕
        </button>

        {(() => {
          const byIdx = subject.indexOf(" by ");
          const title = byIdx !== -1 ? subject.slice(0, byIdx) : subject;
          const author = byIdx !== -1 ? subject.slice(byIdx + 4) : null;
          return (
            <div className="mb-4 pr-8">
              <h2 className="text-base font-bold text-zinc-900 dark:text-zinc-100 leading-snug">
                {title}
              </h2>
              {author && (
                <p className="text-sm text-zinc-500 dark:text-zinc-400 mt-0.5">by {author}</p>
              )}
            </div>
          );
        })()}

        {error ? (
          <p className="text-sm text-red-500">Could not load details. Please try again.</p>
        ) : detail === null ? (
          <p className="text-sm animate-pulse bg-linear-to-r from-indigo-500 via-purple-500 to-indigo-400 bg-clip-text text-transparent font-medium">
            Loading details…
          </p>
        ) : (
          <p className="text-sm text-zinc-700 dark:text-zinc-300 leading-relaxed whitespace-pre-line">
            {detail}
          </p>
        )}
      </div>
    </div>
  );
}
