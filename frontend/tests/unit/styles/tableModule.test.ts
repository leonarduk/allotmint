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
    expect(thead).toMatch(/z-index:\s*[1-9]/)
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
