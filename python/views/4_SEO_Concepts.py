import streamlit as st

st.title("7. SEO concepts in plain English")
st.write("You do not need to memorize every SEO term. Understand the basics below so you can judge what the automation is doing.")

with st.expander("1. Crawling vs. indexing vs. ranking", expanded=True):
    st.markdown("""
**Crawling** means a bot requests a page and reads what it can access. Our Python crawler does a small version of this by following links.

**Indexing** means a search engine decides whether to store and consider a page for search results. Finding a page with our crawler does not prove Google has indexed it.

**Ranking** is the ordering of results for a particular search. Our tool cannot guarantee ranking. A good technical check is only one part of a much larger picture.
""")
with st.expander("2. URL, HTTP status and redirects"):
    st.markdown("""
A **URL** is the page's address. **HTTP 200** usually means the request succeeded. **404** means not found. **301/308** typically indicate a permanent redirect; **302/307** usually indicate a temporary one. A crawler records these so you can spot dead or redirected links.
""")
with st.expander("3. Title tag, meta description and H1"):
    st.markdown("""
- **Title tag:** text in the HTML `<title>` element. It is a strong page-identification signal and can influence the title link shown in search. Google may choose a different title.
- **Meta description:** a short summary in HTML metadata. Google may use it for the search snippet, but may instead select text from the page.
- **H1:** the main visible heading. It helps visitors understand the page topic. Do not force a keyword into every heading or assume that exactly one H1 is a ranking requirement.

The code flags missing values and some review candidates; its character counts are prompts for human review, not official Google limits.
""")
with st.expander("4. Keywords and search intent"):
    st.markdown("""
A **keyword** (more naturally called a search query) is what someone types into a search engine. **Search intent** is what they are trying to do: learn something, compare options, find a specific business, or buy.

Choose a phrase that genuinely matches what the page helps the visitor do. Do not repeat it unnaturally. A page targeting “how to choose a CRM” should answer that question rather than becoming an unrelated sales pitch.
""")
with st.expander("5. Internal links and site structure"):
    st.markdown("""
An **internal link** connects one page on your site to another page on the same site. Useful links help people explore related topics and help crawlers discover URLs. Link because the destination is useful, not simply to hit a target number.
""")
with st.expander("6. Canonical URL, robots.txt, noindex and sitemap"):
    st.markdown("""
- **Canonical URL:** a hint about the preferred URL when multiple URLs contain duplicate or very similar content. Do not add or change canonicals blindly.
- **robots.txt:** crawl instructions. It is not a reliable privacy mechanism and is not the same as a noindex directive.
- **noindex:** asks supporting search engines not to include a page in search results if the crawler can access and read the directive. Do not remove this automatically.
- **XML sitemap:** a list of important URLs that can help search engines discover pages. Listing a URL does not guarantee indexing.
""")
with st.expander("7. Local LLM, prompt and hallucination"):
    st.markdown("""
A **local LLM** is a text-generation model that runs on your computer through Ollama. The **prompt** is the instruction plus the page context you send to it. The model returns a draft, not verified truth. A **hallucination** is information the model states confidently without support. Provide verified business facts and check every claim before publishing.
""")
with st.expander("8. Suggest-only workflow and human review"):
    st.markdown("""
This lab never edits the live website. A suggestion stores the **original** and **suggested** content side by side; a human accepts or rejects each change and applies the accepted ones in their own codebase, with backups and the ability to roll back.
""")
with st.expander("9. Search Console metrics"):
    st.markdown("""
**Impressions** are how often your site appeared in a Google result; **clicks** are clicks from those results; **CTR** is clicks divided by impressions; **average position** summarizes ranking position in the report's defined way. These are observations, not proof that a specific edit caused a change. Compare similar date windows and account for seasonality, query mix, and other changes.
""")
with st.expander("10. What this prototype does not do"):
    st.markdown("""
It does not yet connect Google Search Console, PageSpeed Insights, keyword-volume providers, link-index services, or a production CMS. It does not perform a full JavaScript-rendering audit, prove indexing, judge backlinks comprehensively, or promise rankings. Add those integrations one at a time after you understand the basic workflow.
""")

st.subheader("Official references")
st.markdown("""
- [Google SEO Starter Guide](https://developers.google.com/search/docs/fundamentals/seo-starter-guide)
- [Google crawling and indexing documentation](https://developers.google.com/search/docs/crawling-indexing)
- [Google robots.txt introduction](https://developers.google.com/search/docs/crawling-indexing/robots/intro)
- [Google noindex guidance](https://developers.google.com/search/docs/crawling-indexing/block-indexing)
- [Build and submit a sitemap](https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap)
- [Search Console Search Analytics API](https://developers.google.com/webmaster-tools/v1/searchanalytics/query)
""")
