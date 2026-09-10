import { PersonalizedFeed } from "@/components/personalized-feed";

export const dynamic = "force-dynamic";

export default async function ForYouPage({
  searchParams,
}: {
  searchParams: Promise<{ cursor?: string }>;
}) {
  return (
    <PersonalizedFeed kind="for-you" cursor={(await searchParams).cursor} />
  );
}
