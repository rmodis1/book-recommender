import { ChatWindow } from "@/components/chat/ChatWindow";

export default function Home() {
  return (
    <main className="flex flex-col flex-1 h-full max-w-3xl w-full mx-auto">
      <ChatWindow />
    </main>
  );
}
