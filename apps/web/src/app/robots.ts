import type { MetadataRoute } from "next";

import { getHomepage } from "@/lib/public-api";

export const dynamic = "force-dynamic";

export default async function robots(): Promise<MetadataRoute.Robots> {
  const { portal } = await getHomepage();
  const privatePaths = [
    "/admin/",
    "/api/",
    "/for-you",
    "/following",
    "/*/for-you",
    "/*/following",
    "/search",
    "/*/search",
  ];
  return {
    rules: [
      { userAgent: "*", allow: "/", disallow: privatePaths },
      { userAgent: "Googlebot", allow: "/", disallow: privatePaths },
      { userAgent: "OAI-SearchBot", allow: "/", disallow: privatePaths },
      { userAgent: "PerplexityBot", allow: "/", disallow: privatePaths },
      // Training access is deliberately independent from search visibility.
      { userAgent: "GPTBot", disallow: "/" },
    ],
    sitemap: [
      `${portal.canonical_url}/sitemap.xml`,
      `${portal.canonical_url}/news-sitemap.xml`,
    ],
    host: portal.canonical_url,
  };
}
