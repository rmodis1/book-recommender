"use client";

import { useEffect, useRef } from "react";
import { useChat } from "@/hooks/useChat";
import { ChatInput } from "@/components/chat/ChatInput";
import { MessageBubble } from "@/components/chat/MessageBubble";
import { TypingIndicator } from "@/components/chat/TypingIndicator";

const EXAMPLE_PROMPTS = [
  "I loved Project Hail Mary — what should I read next?",
  "Recommend some cozy mystery novels for a rainy day",
  "I want a nonfiction book about human psychology",
  "What are the best fantasy series for a new reader?",
];

export function ChatWindow() {
  const { messages, isStreaming, sendMessage, clearMessages } = useChat();
  const bottomRef = useRef<HTMLDivElement>(null);
  const isEmpty = messages.length === 0;

  // Scroll to bottom whenever messages or streaming state changes
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isStreaming]);

  // Show the typing indicator only before the assistant message has started
  const showTypingDots =
    isStreaming &&
    messages.length > 0 &&
    messages[messages.length - 1].role === "user";

  return (
    <div className="flex flex-col h-full">
      {/* Message list */}
      <div className="flex-1 overflow-y-auto">
        {isEmpty ? (
          /* Welcome screen */
          <div className="flex flex-col items-center justify-center h-full gap-8 px-4 text-center">
            <div className="flex flex-col items-center gap-2">
              <span className="text-5xl">📚</span>
              <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">
                Welcome to Shelf
              </h1>
              <p className="text-sm text-zinc-500 dark:text-zinc-400 max-w-xs">
                Your AI librarian. Tell me what you like and I'll find your next great read.
              </p>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 w-full max-w-lg">
              {EXAMPLE_PROMPTS.map((prompt) => (
                <button
                  key={prompt}
                  onClick={() => sendMessage(prompt)}
                  className="text-left text-xs px-4 py-3 rounded-xl border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-600 dark:text-zinc-300 hover:border-indigo-400 hover:text-indigo-600 dark:hover:text-indigo-400 transition-colors"
                >
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="flex flex-col gap-4 px-4 py-6">
            {messages.map((msg) => (
              <MessageBubble key={msg.id} message={msg} />
            ))}
            <TypingIndicator visible={showTypingDots} />
            <div ref={bottomRef} />
          </div>
        )}
      </div>

      {/* Input bar */}
      <div className="shrink-0 px-4 pb-6 pt-3 border-t border-zinc-100 dark:border-zinc-800">
        {!isEmpty && (
          <div className="flex justify-end mb-2">
            <button
              onClick={clearMessages}
              className="text-xs text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300 transition-colors"
            >
              Clear conversation
            </button>
          </div>
        )}
        <ChatInput onSend={sendMessage} disabled={isStreaming} />
        <p className="mt-2 text-center text-[10px] text-zinc-400">
          Shift + Enter for a new line · recommendations may include hallucinated titles
        </p>
      </div>
    </div>
  );
}
