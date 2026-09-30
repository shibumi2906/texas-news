import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { StoryView } from "@/components/public-site";
import { StoryStructuredData } from "@/components/structured-data";
import { getStory, PublicApiError } from "@/lib/public-api";

export const dynamic = "force-dynamic";

type Props = { params: Promise<{ slug: string }> };

async function loadStory(slug: string) {
  try {
    return await getStory(slug);
  } catch (error) {
    if (error instanceof PublicApiError && error.status === 404) notFound();
    throw error;
  }
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const story = await loadStory((await params).slug);
  const description =
    (typeof story.seo.description === "string"
      ? story.seo.description
      : null) ??
    story.description ??
    story.subtitle ??
    story.title;
  const image = story.media[0]?.thumbnail_url ?? story.media[0]?.url;
  return {
    title: typeof story.seo.title === "string" ? story.seo.title : story.title,
    description,
    alternates: { canonical: story.canonical_url, languages: story.alternates },
    openGraph: {
      title: story.title,
      description,
      type: "article",
      url: story.canonical_url,
      publishedTime: story.published_at,
      modifiedTime: story.updated_at,
      images: image ? [{ url: image }] : undefined,
    },
  };
}

export default async function StoryPage({ params }: Props) {
  const story = await loadStory((await params).slug);
  return (
    <>
      <StoryStructuredData story={story} />
      <StoryView story={story} portal={story.portal} />
    </>
  );
}
