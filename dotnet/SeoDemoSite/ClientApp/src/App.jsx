import { useEffect, useState } from 'react'
import { Link, NavLink, useLocation } from 'react-router-dom'

const NAV = [
  ['/', 'Home'],
  ['/destinations', 'Destinations'],
  ['/itineraries', 'Itineraries'],
  ['/travel-tips', 'Travel Tips'],
  ['/resources', 'Resources'],
  ['/about', 'About'],
]

const isExternal = (href) => /^https?:\/\//.test(href)

function SmartLink({ href, children, ...rest }) {
  return isExternal(href)
    ? <a href={href} target="_blank" rel="noopener noreferrer" {...rest}>{children}</a>
    : <Link to={href} {...rest}>{children}</Link>
}

function Section({ section }) {
  const { heading, image, paragraphs = [], items = [], links = [], cards = [] } = section
  return (
    <section className="section">
      {heading && <h2>{heading}</h2>}
      <div className={image ? 'with-image' : undefined}>
        {image && <img className="section-image" src={image.url} alt={image.alt} loading="lazy" />}
        <div>
          {paragraphs.map((p, i) => <p key={i}>{p}</p>)}
          {items.length > 0 && <ul>{items.map((t, i) => <li key={i}>{t}</li>)}</ul>}
          {links.length > 0 && (
            <ul className="links">
              {links.map((l) => <li key={l.href}><SmartLink href={l.href}>{l.label}</SmartLink></li>)}
            </ul>
          )}
        </div>
      </div>
      {cards.length > 0 && (
        <div className="cards">
          {cards.map((c) => (
            <article className="card" key={c.href}>
              <Link to={c.href}><img src={c.imageUrl} alt={c.imageAlt} loading="lazy" /></Link>
              <div className="card-body">
                <h3><Link to={c.href}>{c.title}</Link></h3>
                <p>{c.text}</p>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  )
}

function ContactForm() {
  const [sent, setSent] = useState(false)
  return (
    <form className="contact" onSubmit={(e) => { e.preventDefault(); setSent(true) }}>
      <label>Name<input name="name" required /></label>
      <label>Email<input name="email" type="email" required /></label>
      <label>Message<textarea name="message" rows="5" required /></label>
      <button type="submit">Send message</button>
      {sent && <p role="status" className="notice">Thanks. This is a local demo form, so nothing was sent.</p>}
      <p className="note">Website administrators should add a working contact form and a monitored contact method before publishing this page.</p>
    </form>
  )
}

function PageView({ page }) {
  return (
    <>
      {page.heroImage && (
        <div className="hero" style={{ backgroundImage: `linear-gradient(rgba(10,30,50,.45), rgba(10,30,50,.65)), url(${page.heroImage.url})` }} role="img" aria-label={page.heroImage.alt} />
      )}
      <div className="container">
        <h1>{page.h1}</h1>
        {page.tagline && <h2 className="tagline">{page.tagline}</h2>}
        <div className="lead">{page.paragraphs.map((p, i) => <p key={i}>{p}</p>)}</div>
        {page.slug === 'contact' && <ContactForm />}
        {page.sections.map((s, i) => <Section key={i} section={s} />)}
      </div>
    </>
  )
}

export default function App() {
  const { pathname } = useLocation()
  const [pages, setPages] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetch('/api/pages').then((r) => r.json()).then(setPages).catch(setError)
  }, [])

  const wanted = pathname.length > 1 ? pathname.replace(/\/+$/, '') : '/'
  const page = pages?.find((p) => p.path.toLowerCase() === wanted.toLowerCase())

  // Keep title/description in sync on client-side navigation (the server sets them on first load).
  useEffect(() => {
    if (!page) return
    document.title = page.title
    let meta = document.querySelector('meta[name="description"]')
    if (!meta) { meta = document.createElement('meta'); meta.name = 'description'; document.head.appendChild(meta) }
    meta.content = page.metaDescription
    window.scrollTo(0, 0)
  }, [page])

  return (
    <>
      <header className="site-header">
        <div className="bar">
          <Link to="/" className="brand">🌍 Explore the World</Link>
          <nav>
            {NAV.map(([to, label]) => <NavLink key={to} to={to} end={to === '/'}>{label}</NavLink>)}
          </nav>
        </div>
      </header>
      <main>
        {error && <div className="container"><p>Could not load page content. Is the .NET API running?</p></div>}
        {!error && !pages && <div className="container"><p>Loading…</p></div>}
        {pages && !page && <div className="container"><h1>Page not found</h1><p><Link to="/">Back to the home page</Link></p></div>}
        {page && <PageView page={page} />}
      </main>
      <footer className="site-footer">
        <div className="container">
          <p>Explore the World is a local ASP.NET Core + React SEO test site. Not a production website. Page version: {page?.version ?? '–'}.</p>
          <p>
            <Link to="/about">About</Link> · <Link to="/contact">Contact</Link> · <Link to="/editorial-policy">Editorial policy</Link> ·{' '}
            <a href="/sitemap.xml">XML sitemap</a> · <a href="/robots.txt">robots.txt</a> · <a href="/api/pages">Demo API</a>
          </p>
        </div>
      </footer>
    </>
  )
}
