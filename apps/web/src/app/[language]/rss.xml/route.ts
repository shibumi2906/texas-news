import { notFound } from "next/navigation";

import { rssResponse } from "@/lib/feeds";

export const dynamic = "force-dynamic";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ language: string }> },
) {
  const { language } = await params;
  if (language !== "es") notFound();
  return rssResponse(language);
}
