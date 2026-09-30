# AI and search discovery operations

The public site exposes the same editorially eligible content to search engines and
answer engines that it exposes to readers. Discovery never creates a second content
identity: every story URL is generated from the canonical `ContentItem` returned by
the public API.

## Public endpoints

- `/robots.txt` allows Googlebot, OAI-SearchBot and PerplexityBot on public pages.
- `/sitemap.xml` contains canonical EN/ES pages, available language alternates,
  author pages and public media URLs.
- `/news-sitemap.xml` contains no more than 1,000 eligible representations published
  during the preceding two days.
- `/rss.xml` and `/es/rss.xml` expose the newest 50 eligible stories.
- `/llms.txt` is a human-readable directory. It is not treated as a ranking control.

Admin, API, personalized and search-result pages are excluded from crawler access.
GPTBot is disallowed independently of OAI-SearchBot; changing the training policy
must not accidentally disable ChatGPT Search discovery.

## Production launch checklist

1. Configure the portal's `seo_settings.canonical_base_url` with the final HTTPS
   origin. It must not contain localhost, a preview hostname or credentials.
2. Configure `Portal.logo` with an absolute HTTPS image and set
   `NEXT_PUBLIC_NEWSROOM_EMAIL` to a monitored publisher address.
3. Replace placeholder ownership wording with the legal publisher, beneficial owner
   and material funding disclosures before launch.
4. Verify that the CDN/WAF permits the published IP ranges for Googlebot,
   OAI-SearchBot and PerplexityBot. User-agent strings alone are not proof of crawler
   identity.
5. Fetch a public story with each verified crawler identity. It must return `200`,
   canonical HTML and the complete article body without a challenge page.
6. Confirm that `/robots.txt`, both sitemaps and both feeds return `200` on the
   production hostname. Every sitemap URL must return `200`, self-canonicalize and
   remain inside its portal and language representation.
7. Register the production origin in Google Search Console and Bing Webmaster Tools,
   submit both sitemaps and inspect representative story URLs.
8. Validate homepage and story JSON-LD with Google's Rich Results Test. Structured
   fields must match visible title, author, dates, section, language and images.

Official crawler references:

- OpenAI: <https://developers.openai.com/api/docs/bots>
- Perplexity: <https://docs.perplexity.ai/docs/resources/perplexity-crawlers>
- Google AI features: <https://developers.google.com/search/docs/appearance/ai-features>
- Google News sitemaps:
  <https://developers.google.com/search/docs/crawling-indexing/sitemaps/news-sitemap>

## Monitoring

Log the normalized crawler family, request path, response status, latency and cache
status. Do not log authorization headers, cookies, subscription endpoints, provider
credentials or raw query strings. Validate claimed bots by reverse/forward DNS or the
provider's published IP ranges at the edge.

Track:

- crawl `2xx`, `4xx`, `5xx` and challenge rates by verified crawler;
- indexed canonical URLs and sitemap processing errors;
- referrals from Google, ChatGPT and Perplexity;
- a fixed monthly set of local discovery questions in EN and ES;
- citations to individual stories separately from recommendations of the publisher.

Technical eligibility does not guarantee recommendation. Publisher-level
recommendations require original reporting and independent references from venues,
artists, public bodies, universities and other established local sources. Sponsored
syndication must preserve clear attribution and a canonical link to the source story.
