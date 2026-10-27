using System.Net;
using System.Text;
using System.Text.Json;
using System.Xml.Linq;
using Microsoft.AspNetCore.StaticFiles;

var builder = WebApplication.CreateBuilder(args);
var app = builder.Build();

var dataFile = Path.Combine(app.Environment.ContentRootPath, "site-data.json");
var seedFile = Path.Combine(app.Environment.ContentRootPath, "seed-data.json");
var distDir = Path.Combine(app.Environment.ContentRootPath, "ClientApp", "dist");
var siteLock = new object();
var apiKey = Environment.GetEnvironmentVariable("SEO_DEMO_API_KEY") ?? "local-dev-change-me";
var jsonOptions = new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true };
var pages = LoadPages(dataFile, seedFile, jsonOptions);

// React build output (hashed JS/CSS). The HTML shell itself is served through RenderPage below.
// An explicit endpoint is used because the catch-all page route below would otherwise win over UseStaticFiles.
var assetsDir = Path.GetFullPath(Path.Combine(distDir, "assets"));
var contentTypes = new FileExtensionContentTypeProvider();
app.MapGet("/assets/{**file}", IResult (string file) =>
{
    var full = Path.GetFullPath(Path.Combine(assetsDir, file));
    if (!full.StartsWith(assetsDir + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase) || !File.Exists(full))
        return Results.NotFound();
    contentTypes.TryGetContentType(full, out var contentType);
    return Results.File(full, contentType ?? "application/octet-stream");
});

app.MapGet("/robots.txt", (HttpContext ctx) => Results.Text(
    $"User-agent: *\nAllow: /\nSitemap: {ctx.Request.Scheme}://{ctx.Request.Host}/sitemap.xml\n",
    "text/plain; charset=utf-8"));

app.MapGet("/sitemap.xml", (HttpContext ctx) =>
{
    var baseUrl = $"{ctx.Request.Scheme}://{ctx.Request.Host}";
    XNamespace ns = "http://www.sitemaps.org/schemas/sitemap/0.9";
    var xml = new XDocument(
        new XElement(ns + "urlset",
            pages.Select(p => new XElement(ns + "url", new XElement(ns + "loc", baseUrl + p.Path)))));
    return Results.Content(xml.ToString(), "application/xml; charset=utf-8");
});

app.MapGet("/api/pages", () => Results.Ok(pages.Select(ToApiPage)));
app.MapGet("/api/pages/{slug}", IResult (string slug) =>
{
    var page = pages.FirstOrDefault(p => p.Slug.Equals(slug, StringComparison.OrdinalIgnoreCase));
    return page is null ? Results.NotFound(new { error = "Page slug not found." }) : Results.Ok(ToApiPage(page));
});

app.MapPatch("/api/pages/{slug}/seo", IResult (HttpContext context, string slug, SeoUpdate input) =>
{
    // This API is for a local learning demo. Bind Kestrel to loopback; do not expose this endpoint publicly.
    var suppliedKey = context.Request.Headers["X-SEO-API-Key"].ToString();
    if (string.IsNullOrWhiteSpace(apiKey) || !CryptographicEquals(suppliedKey, apiKey))
        return Results.Unauthorized();

    if (input.ApprovalId <= 0)
        return Results.BadRequest(new { error = "A positive approvalId is required." });
    if (string.IsNullOrWhiteSpace(input.Title) || input.Title.Length > 300)
        return Results.BadRequest(new { error = "Title must contain 1 to 300 characters." });
    if (string.IsNullOrWhiteSpace(input.MetaDescription) || input.MetaDescription.Length > 1000)
        return Results.BadRequest(new { error = "Meta description must contain 1 to 1000 characters." });
    if (string.IsNullOrWhiteSpace(input.H1) || input.H1.Length > 300)
        return Results.BadRequest(new { error = "H1 must contain 1 to 300 characters." });
    if (input.Paragraphs is null || input.Paragraphs.Count < 1 || input.Paragraphs.Count > 8 || input.Paragraphs.Any(p => string.IsNullOrWhiteSpace(p) || p.Length > 2500))
        return Results.BadRequest(new { error = "Provide 1 to 8 non-empty paragraphs, each no longer than 2500 characters." });

    lock (siteLock)
    {
        var page = pages.FirstOrDefault(p => p.Slug.Equals(slug, StringComparison.OrdinalIgnoreCase));
        if (page is null) return Results.NotFound(new { error = "Page slug not found." });
        if (input.ExpectedVersion != page.Version)
            return Results.Conflict(new { error = "This page changed after the draft was made. Audit it again and create a new proposal." });

        page.Title = input.Title.Trim();
        page.MetaDescription = input.MetaDescription.Trim();
        page.H1 = input.H1.Trim();
        page.Paragraphs = input.Paragraphs.Select(p => p.Trim()).ToList();
        page.Version++;
        page.LastApprovalId = input.ApprovalId;
        File.WriteAllText(dataFile, JsonSerializer.Serialize(pages, jsonOptions));
        return Results.Ok(new { status = "published", approvalId = input.ApprovalId, page = ToApiPage(page) });
    }
});

// Any other GET is a site page: serve the React shell with the SEO head and content pre-rendered for crawlers.
app.MapGet("/{**path}", IResult (HttpContext ctx, string? path) =>
{
    var wantedPath = "/" + (path ?? "").Trim('/');
    var page = pages.FirstOrDefault(p => p.Path.Equals(wantedPath, StringComparison.OrdinalIgnoreCase));
    if (page is null)
        return Results.Content("<!doctype html><html><head><title>404 - Not found</title></head><body><h1>404 - Page not found</h1><p><a href='/'>Home</a></p></body></html>", "text/html; charset=utf-8", statusCode: 404);

    var indexFile = Path.Combine(distDir, "index.html");
    if (!File.Exists(indexFile))
        return Results.Content("<!doctype html><html><body><h1>Frontend not built</h1><p>Run <code>npm install</code> and <code>npm run build</code> in <code>ClientApp</code>.</p></body></html>", "text/html; charset=utf-8", statusCode: 503);

    var baseUrl = $"{ctx.Request.Scheme}://{ctx.Request.Host}";
    var html = File.ReadAllText(indexFile)
        .Replace("<!--SEO_HEAD-->", RenderHead(page, baseUrl))
        .Replace("<!--APP_HTML-->", RenderBody(page));
    return Results.Content(html, "text/html; charset=utf-8");
});

app.Run("http://127.0.0.1:5055");

static object ToApiPage(DemoPage p) => new
{
    slug = p.Slug, path = p.Path, title = p.Title, metaDescription = p.MetaDescription,
    h1 = p.H1, tagline = p.Tagline, heroImage = p.HeroImage, paragraphs = p.Paragraphs,
    sections = p.Sections, version = p.Version, lastApprovalId = p.LastApprovalId
};

static string E(string? value) => WebUtility.HtmlEncode(value ?? "");

static string RenderHead(DemoPage page, string baseUrl) =>
    $"<title>{E(page.Title)}</title>\n" +
    $"  <meta name=\"description\" content=\"{E(page.MetaDescription)}\">\n" +
    "  <meta name=\"robots\" content=\"index,follow\">\n" +
    $"  <link rel=\"canonical\" href=\"{E(baseUrl + page.Path)}\">\n" +
    $"  <meta property=\"og:title\" content=\"{E(page.Title)}\">\n" +
    $"  <meta property=\"og:description\" content=\"{E(page.MetaDescription)}\">";

// Plain-HTML copy of the page content. React replaces it on load; crawlers that do not run JavaScript read it as-is.
static string RenderBody(DemoPage page)
{
    var sb = new StringBuilder();
    sb.Append("<nav>");
    foreach (var (label, href) in new[] { ("Home", "/"), ("Destinations", "/destinations"), ("Itineraries", "/itineraries"), ("Travel Tips", "/travel-tips"), ("Resources", "/resources"), ("About", "/about") })
        sb.Append($"<a href=\"{href}\">{label}</a> ");
    sb.Append("</nav><main>");
    if (page.HeroImage is not null) sb.Append($"<img src=\"{E(page.HeroImage.Url)}\" alt=\"{E(page.HeroImage.Alt)}\">");
    sb.Append($"<h1>{E(page.H1)}</h1>");
    if (!string.IsNullOrWhiteSpace(page.Tagline)) sb.Append($"<h2>{E(page.Tagline)}</h2>");
    foreach (var p in page.Paragraphs) sb.Append($"<p>{E(p)}</p>");
    foreach (var s in page.Sections)
    {
        sb.Append("<section>");
        if (!string.IsNullOrWhiteSpace(s.Heading)) sb.Append($"<h2>{E(s.Heading)}</h2>");
        if (s.Image is not null) sb.Append($"<img src=\"{E(s.Image.Url)}\" alt=\"{E(s.Image.Alt)}\">");
        foreach (var p in s.Paragraphs) sb.Append($"<p>{E(p)}</p>");
        if (s.Items.Count > 0) sb.Append("<ul>" + string.Concat(s.Items.Select(i => $"<li>{E(i)}</li>")) + "</ul>");
        foreach (var c in s.Cards)
            sb.Append($"<article><img src=\"{E(c.ImageUrl)}\" alt=\"{E(c.ImageAlt)}\"><h3><a href=\"{E(c.Href)}\">{E(c.Title)}</a></h3><p>{E(c.Text)}</p></article>");
        if (s.Links.Count > 0) sb.Append("<ul>" + string.Concat(s.Links.Select(l => $"<li><a href=\"{E(l.Href)}\">{E(l.Label)}</a></li>")) + "</ul>");
        sb.Append("</section>");
    }
    sb.Append("</main><footer><a href=\"/contact\">Contact</a> <a href=\"/editorial-policy\">Editorial policy</a> <a href=\"/sitemap.xml\">XML sitemap</a></footer>");
    return sb.ToString();
}

static List<DemoPage> LoadPages(string filePath, string seedPath, JsonSerializerOptions options)
{
    if (File.Exists(filePath))
    {
        try
        {
            var loaded = JsonSerializer.Deserialize<List<DemoPage>>(File.ReadAllText(filePath), options);
            if (loaded is { Count: > 0 }) return loaded;
        }
        catch (JsonException) { /* Re-create from the seed file below if the file is malformed. */ }
    }
    var seeded = JsonSerializer.Deserialize<List<DemoPage>>(File.ReadAllText(seedPath), options)
                 ?? throw new InvalidOperationException("seed-data.json is empty.");
    File.WriteAllText(filePath, JsonSerializer.Serialize(seeded, options));
    return seeded;
}

static bool CryptographicEquals(string a, string b)
{
    var ba = Encoding.UTF8.GetBytes(a);
    var bb = Encoding.UTF8.GetBytes(b);
    return ba.Length == bb.Length && System.Security.Cryptography.CryptographicOperations.FixedTimeEquals(ba, bb);
}

public sealed class DemoPage
{
    public string Slug { get; set; } = "";
    public string Path { get; set; } = "";
    public string Title { get; set; } = "";
    public string MetaDescription { get; set; } = "";
    public string H1 { get; set; } = "";
    public string? Tagline { get; set; }
    public ImageRef? HeroImage { get; set; }
    // Intro paragraphs: the part of the page the SEO lab proposes and publishes changes to.
    public List<string> Paragraphs { get; set; } = new();
    public List<Section> Sections { get; set; } = new();
    public int Version { get; set; } = 1;
    public int? LastApprovalId { get; set; }
}

public sealed class ImageRef
{
    public string Url { get; set; } = "";
    public string Alt { get; set; } = "";
}

public sealed class Section
{
    public string Heading { get; set; } = "";
    public ImageRef? Image { get; set; }
    public List<string> Paragraphs { get; set; } = new();
    public List<string> Items { get; set; } = new();
    public List<LinkRef> Links { get; set; } = new();
    public List<Card> Cards { get; set; } = new();
}

public sealed class LinkRef
{
    public string Label { get; set; } = "";
    public string Href { get; set; } = "";
}

public sealed class Card
{
    public string Title { get; set; } = "";
    public string Text { get; set; } = "";
    public string Href { get; set; } = "";
    public string ImageUrl { get; set; } = "";
    public string ImageAlt { get; set; } = "";
}

public sealed class SeoUpdate
{
    public string Title { get; set; } = "";
    public string MetaDescription { get; set; } = "";
    public string H1 { get; set; } = "";
    public List<string>? Paragraphs { get; set; }
    public int ExpectedVersion { get; set; }
    public int ApprovalId { get; set; }
}
