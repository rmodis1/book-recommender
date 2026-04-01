"use client";

import Image from "next/image";
import type { Book } from "@/types";

interface BookCardProps {
  book: Book;
}

export function BookCard({ book }: BookCardProps) {
  const powellsQ = encodeURIComponent(`${book.title} ${book.author ?? ""}`.trim());
  const powellsUrl = `https://www.powells.com/searchresults?keyword=${powellsQ}`;

  return (
    <article className="flex-shrink-0 w-40 rounded-xl overflow-hidden border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 shadow-sm flex flex-col">
      {/* Cover */}
      <div className="relative h-52 flex-shrink-0 bg-zinc-100 dark:bg-zinc-700">
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

      {/* Info */}
      <div className="p-2 flex flex-col gap-1 overflow-hidden flex-1">
        <p className="text-xs font-semibold text-zinc-900 dark:text-zinc-100 line-clamp-2 leading-snug">
          {book.title}
        </p>
        <p className="text-xs text-zinc-500 dark:text-zinc-400 line-clamp-1">
          {book.author}
        </p>
        {book.nyt_bestseller && (
          <span className="inline-block text-[10px] font-medium bg-amber-100 dark:bg-amber-900/40 text-amber-800 dark:text-amber-300 rounded px-1.5 py-0.5 w-fit">
            NYT Bestseller
          </span>
        )}
      </div>

      {/* Action links — siblings, never nested */}
      <div className="flex gap-1 mx-2 mb-2">
        {book.book_url && (
          <a
            href={book.book_url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex-1 text-center text-[10px] font-medium border border-zinc-300 dark:border-zinc-600 text-zinc-600 dark:text-zinc-300 rounded-md py-1 hover:bg-zinc-100 dark:hover:bg-zinc-700 transition-colors"
          >
            Goodreads
          </a>
        )}
        <a
          href={powellsUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="flex-1 text-center text-[10px] font-semibold bg-indigo-600 hover:bg-indigo-700 text-white rounded-md py-1 transition-colors"
        >
          Buy
        </a>
      </div>
    </article>
  );
}
