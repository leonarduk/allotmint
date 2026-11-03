import { useTranslation } from 'react-i18next';
import type { McpToolSwitch, McpToolsetSwitch } from '../api';
import { MCP_TOOL_SETUP_DOCS_URL } from '../utils/docsLinks';

// DOM ids derived from a name (stable across reorders), with characters not
// safe in an id replaced.
function safeId(prefix: string, name: string): string {
  return `${prefix}-${name.replace(/[^A-Za-z0-9_-]/g, '-')}`;
}

// The id of an MCP tool's "not configured" note.
function mcpToolStatusId(toolName: string): string {
  return safeId('mcp-tool-status', toolName);
}

type SwitchHandler = (name: string, enabled: boolean) => void;

interface ToolRowProps {
  tool: McpToolSwitch;
  // Set while the tool's toolset is off: the tool cannot be used whatever its own switch says.
  toolsetOffId: string | null;
  onToolChange: SwitchHandler;
}

function ToolRow({ tool, toolsetOffId, onToolChange }: ToolRowProps) {
  const { t } = useTranslation();
  const describedBy =
    [tool.not_configured ? mcpToolStatusId(tool.name) : null, toolsetOffId]
      .filter(Boolean)
      .join(' ') || undefined;
  return (
    <div className="mb-1">
      <label className="block font-medium" title={tool.description}>
        <input
          type="checkbox"
          checked={tool.enabled}
          disabled={toolsetOffId !== null}
          onChange={(e) => onToolChange(tool.name, e.target.checked)}
          aria-describedby={describedBy}
          className="mr-1"
        />
        {tool.name}
      </label>
      {tool.not_configured && (
        <p
          id={mcpToolStatusId(tool.name)}
          className="ml-5 text-xs text-amber-600"
        >
          {t('support.config.mcpToolNotConfigured')}: {tool.not_configured}{' '}
          <a
            href={MCP_TOOL_SETUP_DOCS_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="underline"
          >
            {t('support.config.mcpToolSetupLink')}
          </a>
        </p>
      )}
    </div>
  );
}

interface ToolGridProps {
  tools: McpToolSwitch[];
  toolsetOffId: string | null;
  onToolChange: SwitchHandler;
}

function ToolGrid({ tools, toolsetOffId, onToolChange }: ToolGridProps) {
  return (
    <div className="grid grid-cols-1 gap-x-4 md:grid-cols-2">
      {tools.map((tool) => (
        <ToolRow
          key={tool.name}
          tool={tool}
          toolsetOffId={toolsetOffId}
          onToolChange={onToolChange}
        />
      ))}
    </div>
  );
}

interface ToolsetGroupProps {
  toolset: McpToolsetSwitch;
  tools: McpToolSwitch[];
  onToolsetChange: SwitchHandler;
  onToolChange: SwitchHandler;
}

function ToolsetGroup({
  toolset,
  tools,
  onToolsetChange,
  onToolChange,
}: ToolsetGroupProps) {
  const { t } = useTranslation();
  const offId = safeId('mcp-toolset-off', toolset.name);
  return (
    <fieldset className="mb-2 rounded border border-[var(--surface-card-border)] p-2">
      <legend className="px-1">
        <label className="font-semibold">
          <input
            type="checkbox"
            checked={toolset.enabled}
            onChange={(e) => onToolsetChange(toolset.name, e.target.checked)}
            className="mr-1"
          />
          {t('support.config.mcpToolset', { name: toolset.name })}
        </label>
      </legend>
      {!toolset.enabled && (
        <p id={offId} className="mb-1 text-xs text-amber-600">
          {t('support.config.mcpToolsetOff')}
        </p>
      )}
      <ToolGrid
        tools={tools}
        toolsetOffId={toolset.enabled ? null : offId}
        onToolChange={onToolChange}
      />
    </fieldset>
  );
}

interface McpToolSwitchesProps {
  tools: McpToolSwitch[];
  toolsets: McpToolsetSwitch[];
  onToolsetChange: SwitchHandler;
  onToolChange: SwitchHandler;
}

/**
 * The admin page's MCP tool switches, grouped by toolset with a toggle per
 * toolset (#8587). A tool is usable only while its toolset is on (a per-tool
 * "on" does not override an off toolset), so its own switch is greyed out
 * while the toolset is off. Tools without a known toolset (local chat tools,
 * tools allotmint does not know) are listed last.
 */
export default function McpToolSwitches({
  tools,
  toolsets,
  onToolsetChange,
  onToolChange,
}: McpToolSwitchesProps) {
  const { t } = useTranslation();
  const known = new Set(toolsets.map((toolset) => toolset.name));
  const ungrouped = tools.filter(
    (tool) => !tool.toolset || !known.has(tool.toolset)
  );
  if (toolsets.length === 0) {
    return (
      <ToolGrid
        tools={ungrouped}
        toolsetOffId={null}
        onToolChange={onToolChange}
      />
    );
  }
  return (
    <div>
      {toolsets.map((toolset) => (
        <ToolsetGroup
          key={toolset.name}
          toolset={toolset}
          tools={tools.filter((tool) => tool.toolset === toolset.name)}
          onToolsetChange={onToolsetChange}
          onToolChange={onToolChange}
        />
      ))}
      {ungrouped.length > 0 && (
        <fieldset className="mb-2 rounded border border-[var(--surface-card-border)] p-2">
          <legend className="px-1 font-semibold">
            {t('support.config.mcpOtherTools')}
          </legend>
          <ToolGrid
            tools={ungrouped}
            toolsetOffId={null}
            onToolChange={onToolChange}
          />
        </fieldset>
      )}
    </div>
  );
}
