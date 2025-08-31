import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

describe('responsive styles', () => {
  const cssPath = path.resolve(__dirname, 'responsive.css')
  const css = fs.readFileSync(cssPath, 'utf-8')

  it('includes mobile breakpoint', () => {
    expect(css).toMatch(/@media\s*\(min-width:\s*480px\)/)
  })

  it('includes tablet breakpoint', () => {
    expect(css).toMatch(/@media\s*\(min-width:\s*768px\)/)
  })

  it('includes desktop breakpoint', () => {
    expect(css).toMatch(/@media\s*\(min-width:\s*1024px\)/)
  })

  it('includes mobile max-width breakpoint', () => {
    expect(css).toMatch(/@media\s*\(max-width:\s*768px\)/)
  })
})
