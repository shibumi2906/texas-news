import type { Metadata } from "next";

import { FeedView } from "@/components/public-site";
import { getLatest } from "@/lib/public-api";

export const dynamic = "force-dynamic";

type Props = { searchParams: Promise<{ cursor?: string }> };

export async function generateMetadata({
  searchParams,
}: Props): Promise<Metadata> {
  const data = await getLatest((await searchParams).cursor);
  return {
    title: "Latest",
    description: "The latest entertainment stories published across Texas.",
    alternates: { canonical: data.canonical_url, languages: data.alternates },
  };
}

export default async function LatestPage({ searchParams }: Props) {
  const data = await getLatest((await searchParams).cursor);
  return (
    <FeedView
      data={data}
      title="Latest"
      deck="The newest published entertainment stories from across Texas."
      path="/latest"
    />
  );
}
