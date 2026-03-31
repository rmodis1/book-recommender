export interface Book {
  title: string;
  author: string;
  description?: string | null;
  cover_url?: string | null;
  book_url?: string | null;
  source?: string;
  nyt_bestseller?: boolean;
  nyt_list?: string;
  nyt_rank?: number;
  weeks_on_list?: number;
  genres?: string[];
  published_year?: number;
}

export type MessageRole = "user" | "assistant";

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  books?: Book[];
  streaming?: boolean;
}
