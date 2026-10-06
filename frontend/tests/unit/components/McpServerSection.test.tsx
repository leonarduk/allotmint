import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mockGetMcpServerStatus = vi.hoisted(() => vi.fn());
const mockRestartMcpServer = vi.hoisted(() => vi.fn());

vi.mock('@/api', async () => {
  const actual = await vi.importActual<typeof import('@/api')>('@/api');
  return {
    ...actual,
    getMcpServerStatus: mockGetMcpServerStatus,
    restartMcpServer: mockRestartMcpServer,
  };
});

import McpServerSection from '@/components/McpServerSection';

const runningStatus = {
  can_restart: true,
  reason: null,
  url: 'http://localhost:8001/mcp',
  port: 8001,
  running: true,
  pid: 200,
  parent_pid: 100,
  started_at: '2026-10-06T09:00:00Z',
  pro_dir: '/work/allotmint-pro',
  pro_commit: 'abcdef1234567',
  code_changed: true,
  code_changes: [
    'allotmint-pro: commit abcdef1 is newer than the running server.',
  ],
  tool_count: 34,
  tools_error: null,
  log_path: '/work/allotmint/logs/mcp-server.log',
};

async function renderLoaded(onRestarted?: () => void) {
  render(<McpServerSection onRestarted={onRestarted} />);
  await screen.findByRole('heading', { name: 'MCP server' });
}

async function click(name: string) {
  await act(async () => {
    await userEvent.click(screen.getByRole('button', { name }));
  });
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('McpServerSection', () => {
  it('renders nothing when the backend has no MCP server route (AWS)', async () => {
    mockGetMcpServerStatus.mockRejectedValue(
      Object.assign(new Error('Not Found'), { status: 404 })
    );
    const { container } = render(<McpServerSection />);
    await act(async () => {});
    expect(container).toBeEmptyDOMElement();
  });

  it('shows status, tool count and the stale-code warning', async () => {
    mockGetMcpServerStatus.mockResolvedValue(runningStatus);
    await renderLoaded();
    expect(
      screen.getByText(/Running on port 8001 \(pid 200/)
    ).toBeInTheDocument();
    expect(screen.getByText('abcdef1')).toBeInTheDocument();
    expect(screen.getByText('34 tool(s) listed.')).toBeInTheDocument();
    expect(
      screen.getByText(/Code changed since the server started/)
    ).toBeInTheDocument();
    expect(screen.getByText(/commit abcdef1 is newer/)).toBeInTheDocument();
  });

  it('disables restart and shows the reason when the port holder is foreign', async () => {
    mockGetMcpServerStatus.mockResolvedValue({
      ...runningStatus,
      can_restart: false,
      running: false,
      pid: null,
      code_changed: false,
      code_changes: [],
      tool_count: null,
      reason: 'Port 8001 is held by another program (pid 77: node server.js)',
    });
    await renderLoaded();
    expect(screen.getByText(/held by another program/)).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Restart MCP server' })
    ).toBeDisabled();
  });

  it('asks for confirmation, warning about foreground terminals, before restarting', async () => {
    mockGetMcpServerStatus.mockResolvedValue(runningStatus);
    mockRestartMcpServer.mockResolvedValue({
      restarted: true,
      reason: null,
      stopped_pids: [100, 200],
      pid: 301,
      tool_count: 35,
      log_lines: [],
      log_path: runningStatus.log_path,
    });
    const onRestarted = vi.fn();
    await renderLoaded(onRestarted);

    await click('Restart MCP server');
    const dialog = screen.getByRole('dialog', {
      name: 'Restart the MCP server?',
    });
    expect(dialog).toHaveTextContent(
      'stops the MCP server on port 8001 (pid 200)'
    );
    expect(dialog).toHaveTextContent(
      'runs in the background, logging to /work/allotmint/logs/mcp-server.log'
    );
    expect(dialog).toHaveTextContent(
      'started with run-mcp-server in a terminal'
    );
    expect(mockRestartMcpServer).not.toHaveBeenCalled();

    await click('Cancel');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();

    await click('Restart MCP server');
    await click('Confirm restart');
    expect(mockRestartMcpServer).toHaveBeenCalledTimes(1);
    expect(
      screen.getByText('Restarted: pid 301, 35 tool(s).')
    ).toBeInTheDocument();
    expect(onRestarted).toHaveBeenCalledTimes(1);
    expect(mockGetMcpServerStatus).toHaveBeenCalledTimes(2);
  });

  it('shows the failure reason and log lines when the new server fails to start', async () => {
    mockGetMcpServerStatus.mockResolvedValue(runningStatus);
    mockRestartMcpServer.mockResolvedValue({
      restarted: false,
      reason: 'The MCP server launcher exited with code 1.',
      stopped_pids: [100, 200],
      pid: null,
      tool_count: null,
      log_lines: [
        'Traceback (most recent call last):',
        "ImportError: cannot import name 'x'",
      ],
      log_path: runningStatus.log_path,
    });
    const onRestarted = vi.fn();
    await renderLoaded(onRestarted);

    await click('Restart MCP server');
    await click('Confirm restart');

    expect(screen.getByRole('alert')).toHaveTextContent(
      'The MCP server launcher exited with code 1.'
    );
    expect(screen.getByLabelText('MCP server log')).toHaveTextContent(
      "ImportError: cannot import name 'x'"
    );
    expect(onRestarted).not.toHaveBeenCalled();
  });

  it('reports a request error', async () => {
    mockGetMcpServerStatus.mockResolvedValue(runningStatus);
    mockRestartMcpServer.mockRejectedValue(
      Object.assign(new Error('A restart is already in progress.'), {
        status: 409,
      })
    );
    await renderLoaded();
    await click('Restart MCP server');
    await click('Confirm restart');
    expect(screen.getByRole('alert')).toHaveTextContent(
      'A restart is already in progress.'
    );
  });
});
