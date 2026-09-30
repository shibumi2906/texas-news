import { getHomepage } from "@/lib/public-api";

export const dynamic = "force-dynamic";

export async function GET() {
  const { portal } = await getHomepage();
  const base = portal.canonical_url;
  return new Response(
    `# ${portal.name}

> Local entertainment and culture reporting for Texas, published in ${portal.supported_languages.join(" and ")}.

## Primary sections
- [Latest](${base}/latest)
- [Trending](${base}/trending)
- [About](${base}/about)
- [Editorial policy](${base}/editorial-policy)
- [Corrections](${base}/corrections)
- [Ownership and funding](${base}/ownership)
- [RSS](${base}/rss.xml)

Only canonical public story URLs represent published reporting. Personalized, search, API and admin routes are not editorial source pages.
`,
    { headers: { "Content-Type": "text/plain; charset=utf-8" } },
  );
}
