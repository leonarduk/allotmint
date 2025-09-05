import { Helmet } from 'react-helmet'

interface MetaProps {
  title: string
  description: string
  canonical?: string
  jsonLd?: Record<string, unknown>
}

function isSafe(value: unknown): boolean {
  if (value === null) return true
  const t = typeof value
  if (t === 'string' || t === 'number' || t === 'boolean') return true
  if (Array.isArray(value)) return value.every(isSafe)
  if (t === 'object') return Object.values(value as Record<string, unknown>).every(isSafe)
  return false
}

function serializeJsonLd(data: Record<string, unknown>): string | null {
  if (!isSafe(data)) return null
  try {
    return JSON.stringify(data).replace(/</g, '\\u003c')
  } catch {
    return null
  }
}

export default function Meta({ title, description, canonical, jsonLd }: MetaProps) {
  const serialized = jsonLd ? serializeJsonLd(jsonLd) : null
  return (
    <Helmet>
      <title>{title}</title>
      <meta name="description" content={description} />
      {canonical && <link rel="canonical" href={canonical} />}
      <meta property="og:title" content={title} />
      <meta property="og:description" content={description} />
      <meta name="twitter:title" content={title} />
      <meta name="twitter:description" content={description} />
      {serialized && (
        <script type="application/ld+json">{serialized}</script>
      )}
    </Helmet>
  )
}
