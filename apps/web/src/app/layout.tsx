import type { Metadata } from "next";
import type { ReactNode } from "react";

import "./styles.css";

export const metadata: Metadata = {
  title: {
    default: "Texas Entertainment Daily",
    template: "%s | Texas Entertainment Daily",
  },
  description: "Entertainment and culture from across Texas.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en-US">
      <body>{children}</body>
    </html>
  );
}
