import type { Metadata } from "next";
import { headers } from "next/headers";
import type { ReactNode } from "react";

import "./styles.css";

export const metadata: Metadata = {
  title: {
    default: "Texas Entertainment Daily",
    template: "%s | Texas Entertainment Daily",
  },
  description: "Entertainment and culture from across Texas.",
};

export default async function RootLayout({
  children,
}: Readonly<{ children: ReactNode }>) {
  const language =
    (await headers()).get("x-site-language") === "es" ? "es" : "en";
  return (
    <html lang={language === "es" ? "es-US" : "en-US"}>
      <body>{children}</body>
    </html>
  );
}
