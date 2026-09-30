import { rssResponse } from "@/lib/feeds";

export const dynamic = "force-dynamic";

export function GET() {
  return rssResponse("en");
}
