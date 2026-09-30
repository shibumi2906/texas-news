import type { Metadata } from "next";

import { PersonalizedFeed } from "@/components/personalized-feed";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { robots: { index: false, follow: false } };

export default async function ForYouPage({
  searchParams,
}: {
  searchParams: Promise<{ cursor?: string }>;
}) {
  return (
    <PersonalizedFeed kind="for-you" cursor={(await searchParams).cursor} />
  );
}
