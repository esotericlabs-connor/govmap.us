import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "GovMap.us",
  description: "A plain-English view of the entire US federal government.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="scroll-smooth">
      <body className="min-h-screen bg-white text-slate-900 antialiased">
        {children}
      </body>
    </html>
  );
}
