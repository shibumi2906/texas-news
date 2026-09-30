import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { HomeView } from "@/components/public-site";
import { PublisherStructuredData } from "@/components/structured-data";
import { getHomepage, getSetupStatus } from "@/lib/public-api";

export const dynamic = "force-dynamic";

export async function generateMetadata(): Promise<Metadata> {
  const data = await getHomepage();
  return {
    title: "Texas Entertainment Daily",
    description:
      "Entertainment, culture, sports, food and local stories from across Texas.",
    alternates: { canonical: data.canonical_url, languages: data.alternates },
    openGraph: {
      title: "Texas Entertainment Daily",
      description: "The entertainment beat across the Lone Star State.",
      url: data.canonical_url,
      type: "website",
    },
  };
}

export default async function Home() {
  const setup = await getSetupStatus();
  if (setup.required) redirect("/setup");
  const data = await getHomepage();
  return (
    <>
      <PublisherStructuredData portal={data.portal} />
      <HomeView data={data} />
    </>
  );
}
