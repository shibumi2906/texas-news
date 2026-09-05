import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { CategoryView } from "@/components/public-site";
import { getCategory, PublicApiError } from "@/lib/public-api";

export const dynamic = "force-dynamic";

type Props = {
  params: Promise<{ category: string }>;
  searchParams: Promise<{ offset?: string }>;
};

async function loadCategory(props: Props) {
  const { category } = await props.params;
  const rawOffset = (await props.searchParams).offset;
  const offset = Math.max(0, Number.parseInt(rawOffset ?? "0", 10) || 0);
  try {
    return await getCategory(category, offset);
  } catch (error) {
    if (error instanceof PublicApiError && error.status === 404) notFound();
    throw error;
  }
}

export async function generateMetadata(props: Props): Promise<Metadata> {
  const data = await loadCategory(props);
  const description = `The latest ${data.category.name.toLowerCase()} stories from across Texas.`;
  return {
    title: data.category.name,
    description,
    alternates: { canonical: data.canonical_url },
    openGraph: {
      title: data.category.name,
      description,
      url: data.canonical_url,
    },
  };
}

export default async function CategoryPage(props: Props) {
  return <CategoryView data={await loadCategory(props)} />;
}
