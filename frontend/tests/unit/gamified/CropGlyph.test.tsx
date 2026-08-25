import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import CropGlyph from '@/gamified/components/CropGlyph';
import { GLYPH_SHAPES, STAGE_FILL } from '@/gamified/glyphShapes';
import { cropSpecies } from '@/gamified/cropGlyph';

function svgOf(container: HTMLElement): SVGSVGElement {
  const svg = container.querySelector('svg');
  if (!svg) throw new Error('no glyph rendered');
  return svg;
}

describe('CropGlyph', () => {
  it('draws the species the ticker and sector resolve to', () => {
    const { container } = render(
      <CropGlyph ticker="HSBA.L" sector="Financials" stage="budding" />
    );
    const expected = GLYPH_SHAPES[cropSpecies('HSBA.L', 'Financials')].body;
    expect(container.querySelector('clipPath path')).toHaveAttribute(
      'd',
      expected
    );
  });

  it('prefers an explicit species over the ticker', () => {
    const { container } = render(<CropGlyph species="pear" stage="bumper" />);
    expect(container.querySelector('clipPath path')).toHaveAttribute(
      'd',
      GLYPH_SHAPES.pear.body
    );
  });

  it('anchors the fill to the base and sizes it by growth stage', () => {
    const { container } = render(<CropGlyph species="pear" stage="sprout" />);
    const rect = container.querySelector('rect');
    const height = 48 * STAGE_FILL.sprout;
    expect(rect).toHaveAttribute('height', String(height));
    // Anchored at the bottom of the 48-unit box, so the crop fills upward.
    expect(rect).toHaveAttribute('y', String(48 - height));
  });

  it('fills the whole silhouette for a bumper crop', () => {
    const { container } = render(<CropGlyph species="pear" stage="bumper" />);
    const rect = container.querySelector('rect');
    expect(rect).toHaveAttribute('height', '48');
    expect(rect).toHaveAttribute('y', '0');
  });

  it('gives every instance its own clip path', () => {
    // A shared id would point every fill at whichever shape rendered first,
    // so two different crops on one screen would clip to the same silhouette.
    const { container } = render(
      <>
        <CropGlyph species="pear" stage="bumper" />
        <CropGlyph species="carrot" stage="wilting" />
      </>
    );
    const ids = Array.from(container.querySelectorAll('clipPath')).map(
      (node) => node.id
    );
    expect(ids).toHaveLength(2);
    expect(new Set(ids).size).toBe(2);
    expect(ids.every(Boolean)).toBe(true);

    const rects = Array.from(container.querySelectorAll('rect'));
    rects.forEach((rect, index) => {
      expect(rect.getAttribute('clip-path')).toBe(`url(#${ids[index]})`);
    });
  });

  it('takes its colour and box from the wrapper rather than hard-coding them', () => {
    const { container } = render(
      <CropGlyph species="tomato" stage="leafing" />
    );
    const svg = svgOf(container);
    expect(svg).toHaveAttribute('width', '1em');
    expect(svg).toHaveAttribute('height', '1em');
    expect(svg.querySelector('path[stroke]')).toHaveAttribute(
      'stroke',
      'currentColor'
    );
    expect(container.querySelector('rect')).toHaveAttribute(
      'fill',
      'currentColor'
    );
  });

  it('stays out of the accessibility tree', () => {
    // The card already names the ticker and the stage in text.
    const { container } = render(<CropGlyph species="leek" stage="seed" />);
    expect(svgOf(container)).toHaveAttribute('aria-hidden', 'true');
  });
});
