import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { FeedView } from "@/components/public-site";
import { getLocal, PublicApiError } from "@/lib/public-api";

export const dynamic = "force-dynamic";

type Props = {
  params: Promise<{ geography: string }>;
  searchParams: Promise<{ cursor?: string }>;
};

async function loadLocal(props: Props) {
  const { geography } = await props.params;
  try {
    return await getLocal(geography, (await props.searchParams).cursor);
  } catch (error) {
    if (error instanceof PublicApiError && error.status === 404) notFound();
    throw error;
  }
}

export async function generateMetadata(props: Props): Promise<Metadata> {
  const data = await loadLocal(props);
  return {
    title: `Local — ${data.label}`,
    description: `The latest published entertainment stories from ${data.label}.`,
    alternates: { canonical: data.canonical_url },
  };
}

export default async function LocalPage(props: Props) {
  const data = await loadLocal(props);
  return (
    <FeedView
      data={data}
      title={`${data.label} Local`}
      deck={`Published entertainment stories connected to ${data.label}.`}
      path={`/local/${data.scope ?? ""}`}
    />
  );
}
