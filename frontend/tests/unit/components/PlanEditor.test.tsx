import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import PlanEditor from '@/components/PlanEditor';

const mockSaveInvestmentPlan = vi.hoisted(() => vi.fn());

vi.mock('@/api', () => ({ saveInvestmentPlan: mockSaveInvestmentPlan }));

function renderEditor() {
  const onSaved = vi.fn();
  render(
    <PlanEditor
      owner="alex"
      initial={{}}
      onSaved={onSaved}
      onCancel={vi.fn()}
    />
  );
  return { onSaved };
}

const change = (label: string, value: string) =>
  fireEvent.change(screen.getByLabelText(label), { target: { value } });

describe('PlanEditor', () => {
  beforeEach(() => mockSaveInvestmentPlan.mockReset());

  it('builds a plan from the form and saves it', async () => {
    mockSaveInvestmentPlan.mockResolvedValue({ plan: {} });
    const { onSaved } = renderEditor();

    change('Target weight % 1', '60');
    expect(screen.getByText(/Total: 60% \(must equal 100%\)/)).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: 'Add target' }));
    change('Target class 2', 'gold');
    change('Target weight % 2', '40');
    expect(screen.getByText('Total: 100%')).toBeVisible();

    fireEvent.click(screen.getByRole('button', { name: 'Add vehicle' }));
    change('Ticker 1', 'SGLN.L');
    fireEvent.click(screen.getByRole('button', { name: 'Add assumption' }));
    change('Assumption 1', 'retirement_age');
    change('Value 1', '58');
    fireEvent.click(screen.getByRole('button', { name: 'Add open question' }));
    change('Open questions 1', 'Lump sum?');

    fireEvent.click(screen.getByRole('button', { name: 'Save plan' }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    const [owner, sent] = mockSaveInvestmentPlan.mock.calls[0];
    expect(owner).toBe('alex');
    expect(sent).toMatchObject({
      owner: 'alex',
      target: [
        { class: 'equity', weight_pct: 60 },
        { class: 'gold', weight_pct: 40 },
      ],
      vehicles: { equity: [{ ticker: 'SGLN.L' }] },
      assumptions: [{ key: 'retirement_age', value: 58 }],
      open_questions: ['Lump sum?'],
    });
  });

  it('blocks the save on form errors without calling the API', () => {
    renderEditor();
    change('Version', '0');
    fireEvent.click(screen.getByRole('button', { name: 'Save plan' }));
    expect(screen.getByText(/Version must be a whole number/)).toBeVisible();
    expect(mockSaveInvestmentPlan).not.toHaveBeenCalled();
  });

  it('removes a row', () => {
    renderEditor();
    fireEvent.click(screen.getByRole('button', { name: 'Remove target 1' }));
    expect(screen.queryByLabelText('Target class 1')).not.toBeInTheDocument();
  });

  it('round-trips edits between the form and the raw JSON view', () => {
    renderEditor();
    change('Target weight % 1', '70');
    fireEvent.click(screen.getByRole('button', { name: 'Edit as JSON' }));
    const json = screen.getByLabelText('Plan JSON') as HTMLTextAreaElement;
    expect(json.value).toContain('"weight_pct": 70');

    fireEvent.change(json, {
      target: {
        value: json.value.replace('"weight_pct": 70', '"weight_pct": 100'),
      },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Back to form' }));
    expect(screen.getByLabelText('Target weight % 1')).toHaveValue(100);
  });

  it('stays in the JSON view when the JSON is invalid', () => {
    renderEditor();
    fireEvent.click(screen.getByRole('button', { name: 'Edit as JSON' }));
    change('Plan JSON', '[1, 2]');
    fireEvent.click(screen.getByRole('button', { name: 'Back to form' }));
    expect(screen.getByText(/must be a JSON object/)).toBeVisible();
    change('Plan JSON', '{oops');
    fireEvent.click(screen.getByRole('button', { name: 'Back to form' }));
    expect(screen.getByText(/Invalid JSON/)).toBeVisible();
    expect(screen.getByLabelText('Plan JSON')).toBeInTheDocument();
  });
});
