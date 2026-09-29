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
});
