import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

import { DOCS_BASE_URL, MCP_TOOL_SETUP_DOCS_URL } from "@/utils/docsLinks";

// The repo root is the frontend's parent; vitest runs from frontend/.
const REPO_ROOT = path.resolve(process.cwd(), "..");

// GitHub's anchor for a plain-text heading: lower-cased, punctuation dropped,
// spaces to hyphens. Not a full slugger: it does not strip inline markup or add
// GitHub's -1/-2 suffix for repeated headings, so link only to unique,
// plain-text headings (the test below fails if a link's heading is missing).
function githubSlug(heading: string): string {
  return heading
    .trim()
    .toLowerCase()
    .replace(/[^\w\- ]/g, "")
    .replace(/ /g, "-");
}

// Heading level and text per line (undefined for non-headings), ignoring lines
// inside fenced code blocks, where `# ` starts a shell comment.
function headings(lines: string[]): ({ level: number; text: string } | undefined)[] {
  let inFence = false;
  return lines.map((line) => {
    if (/^\s*(```|~~~)/.test(line)) {
      inFence = !inFence;
      return undefined;
    }
    const match = inFence ? null : /^(#{1,6}) (.*)$/.exec(line);
    return match ? { level: match[1].length, text: match[2] } : undefined;
  });
}

// The markdown section under the heading whose anchor is `anchor`, up to the
// next heading of the same or a higher level; undefined if no heading matches.
function sectionFor(markdown: string, anchor: string): string | undefined {
  const lines = markdown.split(/\r?\n/);
  const found = headings(lines);
  const start = found.findIndex((h) => h !== undefined && githubSlug(h.text) === anchor);
  if (start < 0) return undefined;
  const level = found[start]!.level;
  const end = found.findIndex((h, i) => i > start && h !== undefined && h.level <= level);
  return lines.slice(start, end < 0 ? undefined : end).join("\n");
}

function docAndAnchor(url: string): { file: string; anchor: string } {
  expect(url.startsWith(`${DOCS_BASE_URL}/`)).toBe(true);
  const [file, anchor] = url.slice(DOCS_BASE_URL.length + 1).split("#");
  return { file, anchor };
}

describe("docs links", () => {
  it("MCP tool setup link lands on the section that covers MCP credentials", () => {
    const { file, anchor } = docAndAnchor(MCP_TOOL_SETUP_DOCS_URL);
    const section = sectionFor(fs.readFileSync(path.join(REPO_ROOT, file), "utf-8"), anchor);

    expect(section, `no heading in ${file} has anchor #${anchor}`).toBeDefined();
    // Local credentials and the deployed stack's SSM parameters.
    for (const needle of [
      "ALLOTMINT_MCP_BRAVE_API_KEY",
      "ALLOTMINT_MCP_GITHUB_TOKEN",
      "/allotmint/mcp/brave-api-key",
      "/allotmint/mcp/github-token",
    ]) {
      expect(section).toContain(needle);
    }
  });

  it("slugs plain-text headings the way GitHub does", () => {
    expect(githubSlug("Running the chat (MCP) agent locally")).toBe("running-the-chat-mcp-agent-locally");
  });

  it("does not end a section at a shell comment inside a code block", () => {
    const markdown = ["## A", "```bash", "# not a heading", "```", "kept", "## B", "dropped"].join("\n");

    expect(sectionFor(markdown, "a")).toContain("kept");
    expect(sectionFor(markdown, "a")).not.toContain("dropped");
  });
});
