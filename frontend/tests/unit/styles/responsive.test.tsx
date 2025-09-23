import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

describe('responsive styles', () => {
  const cssPath = path.resolve(process.cwd(), 'src/styles/responsive.css')
  const css = fs.readFileSync(cssPath, 'utf-8')

  it('includes max-width breakpoint for small screens', () => {
    expect(css).toMatch(/@media\s*\(max-width:\s*768px\)/)
  })

  it('includes mobile breakpoint', () => {
    expect(css).toMatch(/@media\s*\(min-width:\s*480px\)/)
  })

  it('includes tablet breakpoint', () => {
    expect(css).toMatch(/@media\s*\(min-width:\s*768px\)/)
  })

  it('includes desktop breakpoint', () => {
    expect(css).toMatch(/@media\s*\(min-width:\s*1024px\)/)
  })

  it('uses single column grid by default for phones', () => {
    expect(css).toMatch(/\.responsive-grid\s*{[^}]*grid-template-columns:\s*1fr/)
  })

  it('switches to two columns above 480px', () => {
    expect(css).toMatch(/@media\s*\(min-width:\s*480px\)[\s\S]*grid-template-columns:\s*repeat\(2,\s*1fr\)/)
  })

  it('switches to three columns above 768px', () => {
    expect(css).toMatch(/@media\s*\(min-width:\s*768px\)[\s\S]*grid-template-columns:\s*repeat\(3,\s*1fr\)/)
  })

  it('switches to four columns at desktop widths', () => {
    expect(css).toMatch(/@media\s*\(min-width:\s*1024px\)[\s\S]*grid-template-columns:\s*repeat\(4,\s*1fr\)/)
  })
})
