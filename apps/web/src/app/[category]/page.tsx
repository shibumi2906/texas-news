import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { CategoryView } from "@/components/public-site";
import { getCategory, PublicApiError } from "@/lib/public-api";

export const dynamic = "force-dynamic";

type Props = {
  params: Promise<{ category: string }>;
  searchParams: Promise<{ cursor?: string }>;
};

async function loadCategory(props: Props) {
  const { category } = await props.params;
  const cursor = (await props.searchParams).cursor;
  try {
    return await getCategory(category, cursor);
  } catch (error) {
    if (error instanceof PublicApiError && error.status === 404) notFound();
    throw error;
  }
}

export async function generateMetadata(props: Props): Promise<Metadata> {
  const data = await loadCategory(props);
  const description = `The latest ${data.label.toLowerCase()} stories from across Texas.`;
  return {
    title: data.label,
    description,
    alternates: { canonical: data.canonical_url },
    openGraph: {
      title: data.label,
      description,
      url: data.canonical_url,
    },
  };
}

export default async function CategoryPage(props: Props) {
  return <CategoryView data={await loadCategory(props)} />;
}
