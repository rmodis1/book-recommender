"use client";

import { useEffect, useRef, startTransition, useState } from "react";
import { useChat } from "@/hooks/useChat";
import { ChatInput } from "@/components/chat/ChatInput";
import { MessageBubble } from "@/components/chat/MessageBubble";
import { TypingIndicator } from "@/components/chat/TypingIndicator";

const ALL_PROMPTS = [
  // Science fiction
  "I loved Project Hail Mary — what should I read next?",
  "I finished The Martian and want more books like it.",
  "Recommend some hard sci-fi with realistic science.",
  "What are the best space opera series to start with?",
  "I loved Dune — what epic sci-fi should I read after?",
  "I want sci-fi that explores artificial intelligence and consciousness.",
  // Fantasy
  "What are the best fantasy series for a new reader?",
  "I loved The Hobbit — what classic fantasy should I try next?",
  "Recommend some epic fantasy with incredible world-building.",
  "I want dark fantasy with morally complex characters.",
  "What are some great urban fantasy novels set in modern cities?",
  "I finished A Court of Thorns and Roses — what should I read next?",
  "Any fantasy books with strong female protagonists?",
  // Horror
  "I want a genuinely scary horror novel for a dark night in.",
  "Recommend some psychological horror that messes with your mind.",
  "What are the best Stephen King books to start with?",
  "I want subtle, atmospheric horror rather than gore.",
  // Mystery & thriller
  "Recommend some cozy mystery novels for a rainy day.",
  "I loved Gone Girl — what psychological thrillers should I read next?",
  "What are the best classic detective novels I should read?",
  "I want a twisty thriller that keeps me up all night.",
  "Recommend a murder mystery set in a historical period.",
  "What are some great true crime books from the last few years?",
  // Romance
  "What are the best contemporary romance novels with great banter?",
  "I want a funny, lighthearted romantic comedy to cheer me up.",
  "Recommend some historical romance set in the Regency era.",
  "I loved Outlander — what other historical romance should I try?",
  "What are some great paranormal romance series?",
  // Literary fiction
  "I want a beautiful, literary novel I'll think about for weeks.",
  "Recommend some short story collections that are impossible to put down.",
  "What are the best Booker Prize winners worth reading?",
  "I want literary fiction that deals with identity and belonging.",
  // Historical fiction
  "Recommend some immersive historical fiction set in World War II.",
  "I want a historical novel set in ancient Rome or Greece.",
  "What are the best historical fiction books about strong women?",
  // Young adult
  "I loved The Hunger Games — what YA should I read next?",
  "What are the best YA fantasy series for a teenager?",
  "Recommend some YA novels that adults love just as much.",
  // Nonfiction
  "I want a nonfiction book about human psychology.",
  "Recommend some popular science books that are actually exciting to read.",
  "I loved Sapiens — what other big-ideas history books should I try?",
  "I want a memoir that reads like a novel — gripping and personal.",
  "What are the best self-help books that are actually backed by science?",
  "Recommend a biography of someone who changed the world.",
  "I finished Atomic Habits — what other productivity books should I read?",
  "I want a travel memoir that makes me want to book a flight.",
  "What are some great books about the history of science?",
  "Recommend nonfiction about the history of the internet or technology.",
];

function shuffled<T>(arr: T[]): T[] {
  const a = [...arr];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

export function ChatWindow() {
  const { messages, isStreaming, sendMessage, clearMessages } = useChat();
  const bottomRef = useRef<HTMLDivElement>(null);
  const isEmpty = messages.length === 0;
  const [examplePrompts, setExamplePrompts] = useState<string[]>([]);

  // Shuffle prompts client-side only to avoid SSR/client hydration mismatch.
  // startTransition defers the update so the React Compiler doesn't flag it
  // as a synchronous setState-in-effect (cascading render) violation.
  useEffect(() => {
    startTransition(() => {
      setExamplePrompts(shuffled(ALL_PROMPTS).slice(0, 4));
    });
  }, []);

  // Scroll to bottom whenever messages or streaming state changes
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isStreaming]);

  // Show the typing indicator while streaming and the assistant message is still empty
  const showTypingDots =
    isStreaming &&
    messages.length > 0 &&
    messages[messages.length - 1].role === "assistant" &&
    messages[messages.length - 1].content === "";

  return (
    <div className="flex flex-col h-full">
      {/* Message list */}
      <div className="flex-1 overflow-y-auto">
        {isEmpty ? (
          /* Welcome screen */
          <div className="flex flex-col items-center justify-center h-full gap-8 px-4 text-center">
            <div className="flex flex-col items-center gap-4">
              {/* Shelf icon — open book in indigo to match the color scheme */}
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" className="w-20 h-20" fill="none" aria-hidden="true">
                <rect x="4" y="48" width="56" height="8" rx="3" fill="#6366f1"/>
                <rect x="10" y="14" width="10" height="34" rx="2" fill="#818cf8"/>
                <rect x="23" y="10" width="10" height="38" rx="2" fill="#6366f1"/>
                <rect x="36" y="16" width="10" height="32" rx="2" fill="#818cf8"/>
                <rect x="49" y="12" width="10" height="36" rx="2" fill="#6366f1"/>
              </svg>
              <h1 className="text-5xl font-black tracking-tight text-zinc-900 dark:text-zinc-100">
                Welcome to Shelf
              </h1>
              <p className="text-base text-zinc-500 dark:text-zinc-400 max-w-sm">
                Your AI librarian. Tell me what you like, and I&apos;ll find your next great read.
              </p>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 w-full max-w-lg">
              {examplePrompts.map((prompt) => (
                <button
                  key={prompt}
                  onClick={() => sendMessage(prompt)}
                  className="text-left text-sm px-4 py-3 rounded-xl border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-600 dark:text-zinc-300 hover:border-indigo-400 hover:text-indigo-600 dark:hover:text-indigo-400 transition-colors"
                >
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="flex flex-col gap-4 px-4 py-6">
            {messages.map((msg) => (
              <MessageBubble
                key={msg.id}
                message={msg}
              />
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
              onClick={() => {
                clearMessages();
                setExamplePrompts(shuffled(ALL_PROMPTS).slice(0, 4));
              }}
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
