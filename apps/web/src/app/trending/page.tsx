import type { Metadata } from "next";

import { FeedView } from "@/components/public-site";
import { getTrending } from "@/lib/public-api";

export const dynamic = "force-dynamic";

type Props = { searchParams: Promise<{ cursor?: string }> };

export async function generateMetadata({
  searchParams,
}: Props): Promise<Metadata> {
  const data = await getTrending((await searchParams).cursor);
  return {
    title: "Trending",
    description: "Entertainment stories trending across Texas right now.",
    alternates: { canonical: data.canonical_url },
  };
}

export default async function TrendingPage({ searchParams }: Props) {
  const data = await getTrending((await searchParams).cursor);
  return (
    <FeedView
      data={data}
      title="Trending in Texas"
      deck="Stories gaining attention across the Lone Star State."
      path="/trending"
    />
  );
}
