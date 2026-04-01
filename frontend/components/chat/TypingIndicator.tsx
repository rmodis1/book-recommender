"use client";

import { useEffect, useRef, useState } from "react";

interface TypingIndicatorProps {
  visible: boolean;
}

const MESSAGES = [
  "Browsing the shelves for books you might like",
  "Checking with the librarian",
  "Scanning the stacks",
  "Pulling some titles for you",
];

export function TypingIndicator({ visible }: TypingIndicatorProps) {
  const [index, setIndex] = useState(0);
  const counterRef = useRef(0);

  useEffect(() => {
    if (!visible) return;
    counterRef.current = 0;
    const id = setInterval(() => {
      counterRef.current += 1;
      setIndex(counterRef.current % MESSAGES.length);
    }, 3000);
    return () => clearInterval(id);
  }, [visible]);

  if (!visible) return null;

  return (
    <div className="flex justify-start">
      <div className="bg-zinc-100 dark:bg-zinc-800 rounded-2xl rounded-bl-sm px-4 py-3">
        <span className="text-sm animate-pulse bg-gradient-to-r from-indigo-500 via-purple-500 to-indigo-400 bg-clip-text text-transparent font-medium">
          {MESSAGES[index]}&hellip;
        </span>
      </div>
    </div>
  );
}


