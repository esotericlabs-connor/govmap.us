import type { Metadata } from "next";
import { Inter, Space_Grotesk } from "next/font/google";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
});

const spaceGrotesk = Space_Grotesk({
  subsets: ["latin"],
  weight: ["500", "600", "700"],
  variable: "--font-display",
  display: "swap",
});

const DESCRIPTION =
  "A nonpartisan, plain-English view of the entire US federal government — who represents you, how they vote, who runs the agencies that govern you, where the money goes, and how a bill becomes law.";

export const metadata: Metadata = {
  metadataBase: new URL("https://govmap.us"),
  title: {
    default: "GovMap.us — See your government. Clearly.",
    template: "%s · GovMap.us",
  },
  description: DESCRIPTION,
  openGraph: {
    title: "GovMap.us — See your government. Clearly.",
    description: DESCRIPTION,
    url: "https://govmap.us",
    siteName: "GovMap.us",
    type: "website",
    images: [{ url: "/capitol-hero.jpg", alt: "The US Capitol at sunset — GovMap.us" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "GovMap.us — See your government. Clearly.",
    description: DESCRIPTION,
    images: ["/capitol-hero.jpg"],
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="en"
      className={`${inter.variable} ${spaceGrotesk.variable} scroll-smooth`}
    >
      <body className="min-h-screen bg-govnavy font-sans text-slate-100 antialiased">
        {children}
      </body>
    </html>
  );
}
