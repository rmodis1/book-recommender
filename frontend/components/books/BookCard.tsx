"use client";

import Image from "next/image";
import type { Book } from "@/types";

interface BookCardProps {
  book: Book;
}

export function BookCard({ book }: BookCardProps) {
  const cardContent = (
    <article className="flex-shrink-0 w-40 h-80 rounded-xl overflow-hidden border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 shadow-sm flex flex-col">
      {/* Cover area — fixed height so all cards are uniform */}
      <div className="relative h-56 flex-shrink-0 bg-zinc-100 dark:bg-zinc-700">
        {book.cover_url && (
          <Image
            src={book.cover_url}
            alt={`Cover of ${book.title}`}
            fill
            className="object-cover"
            sizes="160px"
            unoptimized
          />
        )}
      </div>

      {/* Info — fixed remaining height, text clipped not expanding */}
      <div className="p-2 flex flex-col gap-1 overflow-hidden">
        <p className="text-xs font-semibold text-zinc-900 dark:text-zinc-100 line-clamp-2 leading-snug">
          {book.title}
        </p>
        <p className="text-xs text-zinc-500 dark:text-zinc-400 line-clamp-1">
          {book.author}
        </p>
        {book.nyt_bestseller && (
          <span className="mt-auto inline-block text-[10px] font-medium bg-amber-100 dark:bg-amber-900/40 text-amber-800 dark:text-amber-300 rounded px-1.5 py-0.5 w-fit">
            NYT Bestseller
          </span>
        )}
      </div>
    </article>
  );

  if (book.book_url) {
    return (
      <a href={book.book_url} target="_blank" rel="noopener noreferrer" className="no-underline">
        {cardContent}
      </a>
    );
  }

  return cardContent;
}
