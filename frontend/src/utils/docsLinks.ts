// Links from the app into the repo's docs, published on GitHub `main`.
// tests/unit/utils/docsLinks.test.ts checks each anchor against the doc itself.

export const DOCS_BASE_URL = "https://github.com/leonarduk/allotmint/blob/main";

// How to give an MCP tool its credentials, locally and in the deployed stack;
// linked from a "Not configured" tool on the admin MCP tools list (#9314).
export const MCP_TOOL_SETUP_DOCS_URL = `${DOCS_BASE_URL}/docs/CONTRIBUTOR_RUNBOOK.md#running-the-chat-mcp-agent-locally`;
