import type { Metadata } from "next";

import { HomeView } from "@/components/public-site";
import { getHomepage } from "@/lib/public-api";

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
  return <HomeView data={await getHomepage()} />;
}
