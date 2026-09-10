import { PersonalizedFeed } from "@/components/personalized-feed";

export const dynamic = "force-dynamic";

export default async function FollowingPage({
  searchParams,
}: {
  searchParams: Promise<{ cursor?: string }>;
}) {
  return (
    <PersonalizedFeed kind="following" cursor={(await searchParams).cursor} />
  );
}
