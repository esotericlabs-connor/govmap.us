import type { Metadata } from "next";
import { Inter, Space_Grotesk } from "next/font/google";
import "./globals.css";

import { MemberBlade } from "@/components/MemberBlade";
import { SiteHeader } from "@/components/SiteHeader";
import { MapWorkspaceProvider } from "@/lib/map-workspace";
import { MemberBladeProvider } from "@/lib/member-blade";
import { ZipProvider } from "@/lib/zip-context";

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
  "A nonpartisan view of your government, from city council to Congress — starting with who represents you in Congress, how they vote, the bills they write and where their campaign money comes from. Real public records, always sourced.";

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
      // Next 16 stopped disabling smooth scrolling during route changes by
      // default; this restores the instant scroll-to-top on navigation.
      data-scroll-behavior="smooth"
    >
      {/* Base background/text colors are now in globals.css */}
      <body>
        <MapWorkspaceProvider>
          <MemberBladeProvider>
            <ZipProvider>
              {/* Mounted once here so the header, its search and menu survive
                  navigation instead of remounting with every page. */}
              <SiteHeader />
              {children}
            </ZipProvider>
            <MemberBlade />
          </MemberBladeProvider>
        </MapWorkspaceProvider>
      </body>
    </html>
  );
}
