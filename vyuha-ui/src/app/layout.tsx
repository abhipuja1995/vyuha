import type { Metadata } from "next";
import "./globals.css";
import { Sidebar } from "@/components/Sidebar";
import { QueryProvider } from "@/components/QueryProvider";

export const metadata: Metadata = {
  title: "Vyuha — Voice AI Evaluation",
  description: "Bot-to-bot testing, multilingual simulation, automated RCA",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-gray-50 text-gray-900 antialiased">
        <QueryProvider>
          <div className="flex h-screen overflow-hidden">
            <Sidebar />
            <main className="flex-1 overflow-y-auto p-6">{children}</main>
          </div>
        </QueryProvider>
      </body>
    </html>
  );
}
