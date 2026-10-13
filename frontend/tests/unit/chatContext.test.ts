import { describe, expect, it } from 'vitest';
import { buildChatContext } from '../../src/utils/chatPages';

describe('buildChatContext', () => {
  it('extracts the ticker from a research page', () => {
    expect(buildChatContext('/research/ARG.TO')).toEqual({ path: '/research/ARG.TO', ticker: 'ARG.TO' });
  });

  it('decodes an encoded ticker', () => {
    expect(buildChatContext('/research/BRK%2EB')).toEqual({ path: '/research/BRK%2EB', ticker: 'BRK.B' });
  });

  it('has no ticker on other pages or on a malformed escape', () => {
    expect(buildChatContext('/transactions')).toEqual({ path: '/transactions' });
    expect(buildChatContext('/research/%E0%A4%A')).toEqual({ path: '/research/%E0%A4%A' });
  });

  it('adds the owner in view so "this portfolio" resolves (#10813)', () => {
    expect(buildChatContext('/portfolio/steve', { owner: 'steve', group: 'family' })).toEqual({
      path: '/portfolio/steve',
      owner: 'steve',
    });
  });

  it('falls back to the group when no owner is selected', () => {
    expect(buildChatContext('/', { owner: '', group: 'family' })).toEqual({ path: '/', group: 'family' });
    expect(buildChatContext('/', { owner: null, group: null })).toEqual({ path: '/' });
  });

  it('keeps the ticker alongside the owner on a research page', () => {
    expect(buildChatContext('/research/ARG.TO', { owner: 'steve' })).toEqual({
      path: '/research/ARG.TO',
      ticker: 'ARG.TO',
      owner: 'steve',
    });
  });

  it('drops a slug the backend would reject instead of failing the turn', () => {
    expect(buildChatContext('/', { owner: 'not a slug' })).toEqual({ path: '/' });
  });

  it('falls back to the group when the owner is not a usable slug', () => {
    expect(buildChatContext('/', { owner: 'not a slug', group: 'family' })).toEqual({
      path: '/',
      group: 'family',
    });
  });
});
