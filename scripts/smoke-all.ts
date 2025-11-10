import fs from "node:fs";
import path from "node:path";
import { spawn, type SpawnOptions } from "child_process";
import { createRequire } from "module";

type Command = {
  command: string;
  args: string[];
  label: string;
  options?: SpawnOptions;
};

const forwardedEnvironmentVariables = [
  "SMOKE_URL",
  "TEST_ID_TOKEN",
  "SMOKE_AUTH_TOKEN",
  "SMOKE_IDENTITY",
] as const;

const env: NodeJS.ProcessEnv = { ...process.env };

for (const variable of forwardedEnvironmentVariables) {
  const value = process.env[variable];
  if (value !== undefined) {
    env[variable] = value;
  }
}

const scriptArgs = process.argv.slice(2).filter((arg) => arg !== "--");
const cliBase = scriptArgs[0];

if (cliBase) {
  env.SMOKE_URL = cliBase;
}

const targetBase = env.SMOKE_URL;

const require = createRequire(import.meta.url);

const tsxCliPath = require.resolve("tsx/cli");

const backendArgs = targetBase
  ? [tsxCliPath, "scripts/frontend-backend-smoke.ts", targetBase]
  : [tsxCliPath, "scripts/frontend-backend-smoke.ts"];

const npmArgs = ["--prefix", "frontend", "run", "smoke:frontend"] as const;

function sanitizePath(value: string | undefined): string | undefined {
  if (!value) {
    return undefined;
  }
  const trimmed = value.trim();
  if (!trimmed) {
    return undefined;
  }
  if (trimmed.startsWith('"') && trimmed.endsWith('"')) {
    return trimmed.slice(1, -1);
  }
  return trimmed;
}

function createFrontendCommand(): Command {
  const label = "frontend smoke suite";
  const rawExecPath = sanitizePath(env.npm_execpath);

  const runWithNode = (scriptPath: string): Command => ({
    command: process.execPath,
    args: [scriptPath, ...npmArgs],
    label,
  });

  if (rawExecPath) {
    const ext = path.extname(rawExecPath).toLowerCase();
    if (ext === ".js" || ext === ".cjs" || ext === ".mjs") {
      return runWithNode(rawExecPath);
    }
    if (ext === ".cmd" || ext === ".bat") {
      return {
        command: rawExecPath,
        args: [...npmArgs],
        label,
        options: { shell: true },
      };
    }
    return {
      command: rawExecPath,
      args: [...npmArgs],
      label,
    };
  }

  const bundledCli = path.join(
    path.dirname(process.execPath),
    "node_modules",
    "npm",
    "bin",
    "npm-cli.js",
  );

  if (fs.existsSync(bundledCli)) {
    return runWithNode(bundledCli);
  }

  if (process.platform === "win32") {
    return {
      command: "cmd",
      args: ["/c", "npm", ...npmArgs],
      label,
    };
  }

  return {
    command: "npm",
    args: [...npmArgs],
    label,
  };
}

const commands: Command[] = [
  {
    command: process.execPath,
    args: backendArgs,
    label: "backend smoke suite",
  },
  createFrontendCommand(),
];

async function runSequentially() {
  const failures: { label: string; exitCode: number | null }[] = [];

  for (const { command, args, label, options } of commands) {
    console.log(`\n▶ Running ${label}...`);
    const exitCode = await runCommand(command, args, options);

    if (exitCode !== 0) {
      console.error(`✖ ${label} failed with exit code ${exitCode ?? "null"}.`);
      failures.push({ label, exitCode });
    } else {
      console.log(`✔ ${label} completed successfully.`);
    }
  }

  if (failures.length > 0) {
    console.error("\nSmoke suites completed with failures:");
    for (const { label, exitCode } of failures) {
      console.error(`  • ${label} (exit code: ${exitCode ?? "null"})`);
    }

    process.exit(1);
  }

  console.log("\nAll smoke suites completed successfully.");
}

function runCommand(
  command: string,
  args: string[],
  options: Command["options"] = undefined,
): Promise<number | null> {
  return new Promise((resolve) => {
    let child: ReturnType<typeof spawn>;

    try {
      child = spawn(command, args, {
        stdio: "inherit",
        env,
        ...options,
      });
    } catch (error) {
      console.error(`Failed to start command "${command}":`, error);
      resolve(1);
      return;
    }

    child.on("close", (code) => {
      resolve(code);
    });

    child.on("error", (error) => {
      console.error(`Failed to start command \"${command}\":`, error);
      resolve(1);
    });
  });
}

runSequentially().catch((error) => {
  console.error("Unexpected error while orchestrating smoke suites:", error);
  process.exit(1);
});
