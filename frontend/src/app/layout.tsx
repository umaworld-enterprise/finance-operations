import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { Providers } from "@/components/layout/Providers";
import { PWARegister } from "@/components/layout/PWARegister";
import { FontSizeSync } from "@/components/layout/FontSizeSync";

// Runs before paint so the stored font size applies with no flash.
const FONT_SIZE_INIT = `(function(){try{var s=localStorage.getItem("adt-font-size");var m={default:"100%",large:"112.5%",xlarge:"125%"};if(s&&m[s]&&s!=="default"){document.documentElement.style.fontSize=m[s];}}catch(e){}})();`;

const inter = Inter({ subsets: ["latin"] });

export const viewport: Viewport = {
  themeColor: "#171717",
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export const metadata: Metadata = {
  title: "Finance Operations",
  description: "Supplier advance deposit management — track payments, shipments, and supplier risk.",
  applicationName: "Finance Operations",
  manifest: "/manifest.webmanifest",
  appleWebApp: {
    capable: true,
    title: "Finance Ops",
    statusBarStyle: "black-translucent",
  },
  formatDetection: {
    telephone: false,
  },
  icons: {
    icon: [
      { url: "/icon-192.png", sizes: "192x192", type: "image/png" },
      { url: "/icon-512.png", sizes: "512x512", type: "image/png" },
    ],
    apple: "/icon-192.png",
    shortcut: "/icon-192.png",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={inter.className} suppressHydrationWarning>
        <script dangerouslySetInnerHTML={{ __html: FONT_SIZE_INIT }} />
        <Providers>
          {children}
          <FontSizeSync />
        </Providers>
        <PWARegister />
      </body>
    </html>
  );
}
