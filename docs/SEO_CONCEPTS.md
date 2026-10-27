# SEO Concepts for the AI SEO Lab — beginner notes

## 1. What SEO means

SEO stands for search engine optimization. In this project, that means helping the right people discover useful pages and helping search engines access and understand those pages. It is not a trick that forces Google to rank a page. The system can improve site hygiene and prepare better content, but it cannot guarantee rankings.

## 2. The three stages: crawl, index, rank

- **Crawl:** a bot requests a URL and reads the response. Our Python crawler follows internal links on the same host and records basic information. It is a miniature learning crawler, not Googlebot.
- **Index:** a search engine decides whether to store a page and consider it for results. A page appearing in our crawl does not mean Google has indexed it.
- **Rank:** the search engine orders eligible results for a query. Position depends on many factors and varies by query and context.

## 3. URL, response status and redirect

A URL is a page address. `200` usually indicates success; `404` means not found; `5xx` often signals a server error. A `301` or `308` commonly indicates a permanent redirect, while `302` or `307` commonly indicates a temporary redirect. An auditor should record what happened, not assume every redirect is wrong.

## 4. HTML and page elements

- **Title tag:** `<title>Useful title</title>` appears in the HTML head. Google can use it when forming a search-result title link, but may choose different text. Write a unique, descriptive title. No fixed character count guarantees how Google will display it.
- **Meta description:** `<meta name="description" content="...">` is a possible summary for a search result. Google can instead take text from the page. Make it accurate and useful rather than stuffing keywords.
- **H1:** the main visible heading. A clear heading helps a visitor understand the page. Multiple H1s are not automatically a penalty; prioritize a sensible document structure.
- **Body content:** the actual information visitors came for. AI should help clarify or fill genuine gaps, not add repetitive paragraphs merely to create more text.
- **HTML links:** `<a href="/related-page">Related page</a>` connect pages. Useful internal links help people discover related information and help crawlers follow the site.

## 5. Keywords and search intent

A keyword is often a phrase a person types into a search engine; Google calls it a query. Search intent is the person's goal:

- Informational: learn or understand something.
- Commercial investigation: compare options before choosing.
- Transactional: take an action such as purchasing or signing up.
- Navigational: find a particular site, brand, or page.

The page should fulfill the intent. For instance, a page targeting “how to choose project management software” should explain decision criteria; merely repeating the phrase on a sales page won't answer the query. The LLM can suggest a fit, but a human should check it.

## 6. Canonical URLs and duplicate pages

The canonical link points search engines toward the preferred URL among duplicates or near-duplicates. It is a signal, not an unconditional command. Do not mechanically add a canonical to every page or overwrite a correct canonical with the URL currently being crawled. Inspect URL variants and page relationships first.

## 7. robots.txt vs noindex

- **robots.txt** gives crawler access instructions. It is mainly for crawl management, not privacy.
- **noindex** is a directive supported by search engines such as Google to keep a crawled page out of search results. The crawler must be able to access the page and read the directive. Do not remove it without checking why it exists.

These two are not interchangeable. A blocked page can stop Google from seeing a noindex tag.

## 8. XML sitemap

An XML sitemap lists URLs that a site wants search engines to discover. Use absolute canonical URLs and keep it updated. A sitemap can help discovery; it does not force indexing or improve rankings by itself.

## 9. Content quality and AI use

Use AI to draft, organize, improve clarity, generate title options, and find internal pages that are relevant. Supply source material and verified business facts. Check names, prices, claims, dates, regulations, and technical statements. Do not mass-produce pages with little original value. A human should review the content for usefulness and accuracy.

## 10. What embeddings do (optional next step)

A sentence-embedding model turns a sentence into a list of numbers that roughly represents its meaning. It can find similar queries and pages even when they use different words. That is useful for topic clustering and internal-link suggestions, but similarity is not the same as keyword search volume, search intent, or proof that a link belongs on a page.

## 11. Local language model

Ollama runs a language model on your computer. The prompt combines instructions with a page excerpt and target query; the model generates draft text. It can hallucinate, overlook context, or rewrite a sentence so its meaning changes. Structured JSON makes the output easier for code to parse; it does not make the content true.

## 12. Human approval and versioning

Keep the original page values and AI suggestions separately. Let a reviewer edit, approve, or reject the proposed changes. Publish only after approval. The demo site has a version field; publishing checks that the current page version still matches the version used to create the draft. This prevents an old proposal from accidentally overwriting a newer edit.

For a real business site, add authentication, role-based permissions, immutable logs, content backups, a rollback feature, and an audit trail. Do not let the language model decide who can publish.

## 13. Search Console metrics for a later version

- **Impressions:** how many times a result from your site appeared.
- **Clicks:** clicks from Google Search results to your site.
- **CTR:** clicks divided by impressions.
- **Average position:** a summary of the positions of your site's results, not a single permanent ranking.

Segment by page, query, date, country, and device where relevant. Compare similar periods and remember that changes may have multiple causes. The API can return a limited set of rows, so do not assume one response is the complete history.

## Official Google documentation

- SEO Starter Guide: https://developers.google.com/search/docs/fundamentals/seo-starter-guide
- Crawling and indexing: https://developers.google.com/search/docs/crawling-indexing
- robots.txt introduction: https://developers.google.com/search/docs/crawling-indexing/robots/intro
- noindex: https://developers.google.com/search/docs/crawling-indexing/block-indexing
- sitemap creation: https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap
- Search Analytics API: https://developers.google.com/webmaster-tools/v1/searchanalytics/query
