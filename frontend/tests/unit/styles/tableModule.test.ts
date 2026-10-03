import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

// Guards the sticky-header and count-badge fixes from #8532. jsdom does not
// lay out or paint, so these assert the stylesheet contract directly.
describe('table.module.css sticky header and group count', () => {
  const cssPath = path.resolve(process.cwd(), 'src/styles/table.module.css')
  const css = fs.readFileSync(cssPath, 'utf-8')

  const rule = (selector: string) => {
    const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    const match = css.match(new RegExp(`(?:^|\\n)${escaped}\\s*{([^}]*)}`))
    return match?.[1] ?? ''
  }

  it('makes the whole thead sticky with an opaque theme background', () => {
    const thead = rule('.table thead')
    expect(thead).toMatch(/position:\s*sticky/)
    expect(thead).toMatch(/top:\s*0/)
    expect(thead).toMatch(/z-index:\s*[1-9]\d*\s*;/)
    expect(thead).toMatch(/background-color:\s*var\(--surface-card-bg\)/)
  })

  it('does not pin each header cell to top: 0, so the two header rows cannot overlap', () => {
    const th = rule('.table thead th')
    expect(th).not.toMatch(/position:\s*sticky/)
    expect(th).not.toMatch(/background:\s*inherit/)
  })

  it('colours the group count with the theme-aware muted text token', () => {
    const groupCount = rule('.groupCount')
    expect(groupCount).toMatch(/color:\s*var\(--surface-muted-color\)/)
    expect(groupCount).not.toMatch(/rgba\(0,\s*0,\s*0/)
  })
})

// The table rules above only reference theme tokens; this checks the tokens
// are actually defined, with AA contrast, in every theme block of index.css:
// default (dark), explicit light/dark, and the system-theme light override
// (#6530).
describe('theme tokens used by the holdings table header and group count', () => {
  const indexCss = fs.readFileSync(path.resolve(process.cwd(), 'src/index.css'), 'utf-8')

  const block = (selector: string, after = 0) => {
    const start = indexCss.indexOf(`${selector} {`, after)
    expect(start, `missing theme block ${selector}`).toBeGreaterThanOrEqual(0)
    return indexCss.slice(start, indexCss.indexOf('}', start))
  }

  const declaration = (body: string, property: string) => {
    const match = body.match(new RegExp(`(?:^|[\\s;{])${property}:\\s*(#[0-9a-fA-F]{3,6})\\s*;`))
    return match?.[1]
  }

  const luminance = (hex: string) => {
    const full = hex.length === 4 ? `#${[...hex.slice(1)].map((c) => c + c).join('')}` : hex
    const [r, g, b] = [1, 3, 5].map((i) => {
      const channel = parseInt(full.slice(i, i + 2), 16) / 255
      return channel <= 0.03928 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4
    })
    return 0.2126 * r + 0.7152 * g + 0.0722 * b
  }

  const contrast = (a: string, b: string) => {
    const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
    return (hi + 0.05) / (lo + 0.05)
  }

  const systemLightMedia = indexCss.indexOf('@media (prefers-color-scheme: light)')

  const themes: [string, () => string][] = [
    ['default (dark)', () => block(':root')],
    ['explicit light', () => block(":root[data-theme='light']")],
    ['explicit dark', () => block(":root[data-theme='dark']")],
    ['system light', () => block(':root:not([data-theme])', systemLightMedia)],
  ]

  it.each(themes)('%s theme defines the tokens with AA contrast for the group count', (_name, getBody) => {
    const body = getBody()
    const page = declaration(body, 'background-color')
    const card = declaration(body, '--surface-card-bg')
    const muted = declaration(body, '--surface-muted-color')
    const border = declaration(body, '--surface-card-border')

    expect(page).toBeDefined()
    expect(card).toBeDefined()
    expect(muted).toBeDefined()
    expect(border).toBeDefined()
    expect(contrast(muted!, page!)).toBeGreaterThanOrEqual(4.5)
    expect(contrast(muted!, card!)).toBeGreaterThanOrEqual(4.5)
  })

  it('places the system light override inside the prefers-color-scheme: light query', () => {
    expect(systemLightMedia).toBeGreaterThanOrEqual(0)
    expect(indexCss.indexOf(':root:not([data-theme]) {', systemLightMedia)).toBeGreaterThan(systemLightMedia)
  })
})
