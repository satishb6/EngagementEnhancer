import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "WIRE — your take on the news, at the speed of a swipe",
  description:
    "The machine finds the signal and does the labour. You supply the one thing it can't: an opinion worth reading.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link
          rel="preconnect"
          href="https://fonts.gstatic.com"
          crossOrigin="anonymous"
        />
        {/* eslint-disable-next-line @next/next/no-page-custom-font */}
        <link
          href="https://fonts.googleapis.com/css2?family=Instrument+Sans:ital,wght@0,400..700;1,400..700&family=Instrument+Serif:ital@0;1&family=Martian+Mono:wght@300;400;600&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="grain font-sans text-body antialiased">{children}</body>
    </html>
  );
}
