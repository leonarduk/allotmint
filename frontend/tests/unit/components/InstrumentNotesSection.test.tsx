import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import '@/i18n';
import InstrumentNotesSection from '@/components/InstrumentNotesSection';
import type { InstrumentNote } from '@/api';

const mockList = vi.hoisted(() => vi.fn());
const mockCreate = vi.hoisted(() => vi.fn());
const mockDelete = vi.hoisted(() => vi.fn());
const identity = vi.hoisted(() => ({ value: 'demo' }));

vi.mock('@/api', () => ({
  getInstrumentNotes: mockList,
  createInstrumentNote: mockCreate,
  deleteInstrumentNote: mockDelete,
}));
vi.mock('@/hooks/useAlertIdentity', () => ({
  useAlertIdentity: () => ({ identity: identity.value, resolving: false }),
}));
vi.mock('@/hooks/useDemoReadOnly', () => ({
  useDemoReadOnly: () => ({ demoReadOnly: false, reason: () => undefined }),
}));

const note: InstrumentNote = {
  id: 'n1',
  ticker: 'REC.L',
  stance: 'bullish',
  text: 'Cheap vs peers',
  price: null,
  created_at: '2026-01-01T00:00:00Z',
};

beforeEach(() => {
  identity.value = 'demo';
  mockList.mockReset().mockResolvedValue([note]);
  mockCreate.mockReset().mockResolvedValue(note);
  mockDelete.mockReset().mockResolvedValue({ status: 'deleted', note });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('InstrumentNotesSection', () => {
  it('lists notes with their stance and no price comparison when none was saved', async () => {
    render(<InstrumentNotesSection ticker="REC.L" latestPrice={1.2} />);
    expect(await screen.findByText('Cheap vs peers')).toBeInTheDocument();
    expect(
      within(screen.getByRole('listitem')).getByText('Bullish')
    ).toBeInTheDocument();
    expect(screen.queryByText(/since/)).not.toBeInTheDocument();
  });

  it('deletes only after confirmation', async () => {
    const confirm = vi
      .spyOn(window, 'confirm')
      .mockReturnValueOnce(false)
      .mockReturnValueOnce(true);
    render(<InstrumentNotesSection ticker="REC.L" />);
    const del = await screen.findByRole('button', { name: 'Delete' });
    await userEvent.click(del);
    expect(mockDelete).not.toHaveBeenCalled();
    await userEvent.click(del);
    await waitFor(() => expect(mockDelete).toHaveBeenCalledWith('demo', 'n1'));
    expect(confirm).toHaveBeenCalledTimes(2);
  });

  it('keeps the draft and shows the error when saving fails', async () => {
    mockCreate.mockRejectedValue(new Error('boom'));
    render(<InstrumentNotesSection ticker="REC.L" />);
    await screen.findByText('Cheap vs peers');
    await userEvent.type(screen.getByLabelText('Note'), 'Draft');
    await userEvent.click(screen.getByRole('button', { name: 'Add note' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('boom');
    expect(screen.getByLabelText('Note')).toHaveValue('Draft');
  });

  it('asks the user to sign in when there is no identity', () => {
    identity.value = '';
    render(<InstrumentNotesSection ticker="REC.L" />);
    expect(
      screen.getByText('Sign in to keep research notes.')
    ).toBeInTheDocument();
    expect(mockList).not.toHaveBeenCalled();
  });
});
