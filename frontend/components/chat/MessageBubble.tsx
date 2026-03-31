"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { BookCard } from "@/components/books/BookCard";
import type { ChatMessage } from "@/types";

interface MessageBubbleProps {
  message: ChatMessage;
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user";

  return (
    <div className={`flex w-full ${isUser ? "justify-end" : "justify-start"}`}>
      <div className={`flex flex-col gap-3 max-w-[85%] ${isUser ? "items-end" : "items-start"}`}>
        {/* Text bubble */}
        <div
          className={`rounded-2xl px-4 py-3 text-sm leading-relaxed ${
            isUser
              ? "bg-indigo-600 text-white rounded-br-sm"
              : "bg-zinc-100 dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 rounded-bl-sm"
          }`}
        >
          {isUser ? (
            <p>{message.content}</p>
          ) : (
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                // Prevent markdown from rendering links that open in new tabs unsafely
                a: ({ href, children }) => (
                  <a
                    href={href}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="underline underline-offset-2"
                  >
                    {children}
                  </a>
                ),
                // Suppress any inline images the LLM may emit (e.g. ![Cover](url))
                img: () => null,
                p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
                ul: ({ children }) => <ul className="list-disc list-inside mb-2">{children}</ul>,
                ol: ({ children }) => <ol className="list-decimal list-inside mb-2">{children}</ol>,
                strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
              }}
            >
              {message.content || " "}
            </ReactMarkdown>
          )}
          {/* Typing cursor while streaming */}
          {message.streaming && (
            <span className="inline-block w-1.5 h-4 ml-0.5 bg-current animate-pulse align-text-bottom rounded-sm" />
          )}
        </div>

        {/* Book cards */}
        {message.books && message.books.length > 0 && (
          <div className="w-full max-w-full">
            <div className="flex items-center gap-2 mb-2">
              <div className="flex-1 h-px bg-zinc-200 dark:bg-zinc-700" />
              <p className="text-xs font-semibold text-zinc-400 dark:text-zinc-500 uppercase tracking-wide whitespace-nowrap">
                Browse These Books
              </p>
              <div className="flex-1 h-px bg-zinc-200 dark:bg-zinc-700" />
            </div>
            <div className="flex gap-3 overflow-x-auto pb-2 scrollbar-thin scrollbar-thumb-zinc-300">
              {message.books.map((book, i) => (
                <BookCard key={`${book.title}-${i}`} book={book} />
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
