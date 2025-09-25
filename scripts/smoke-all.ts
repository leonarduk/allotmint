import { spawn } from 'child_process';
import { createRequire } from 'module';

type Command = {
  command: string;
  args: string[];
  label: string;
};

const forwardedEnvironmentVariables = [
  'SMOKE_URL',
  'TEST_ID_TOKEN',
  'SMOKE_AUTH_TOKEN',
] as const;

const env: NodeJS.ProcessEnv = { ...process.env };

for (const variable of forwardedEnvironmentVariables) {
  const value = process.env[variable];
  if (value !== undefined) {
    env[variable] = value;
  }
}

const scriptArgs = process.argv.slice(2).filter((arg) => arg !== '--');
const cliBase = scriptArgs[0];

if (cliBase) {
  env.SMOKE_URL = cliBase;
}

const targetBase = env.SMOKE_URL;

const require = createRequire(import.meta.url);

const tsxCliPath = require.resolve('tsx/cli');

const backendArgs = targetBase
  ? [tsxCliPath, 'scripts/frontend-backend-smoke.ts', targetBase]
  : [tsxCliPath, 'scripts/frontend-backend-smoke.ts'];

const commands: Command[] = [
  {
    command: process.execPath,
    args: backendArgs,
    label: 'backend smoke suite',
  },
  {
    command: 'npm',
    args: ['--prefix', 'frontend', 'run', 'smoke:frontend'],
    label: 'frontend smoke suite',
  },
];

async function runSequentially() {
  const failures: { label: string; exitCode: number | null }[] = [];

  for (const { command, args, label } of commands) {
    console.log(`\n▶ Running ${label}...`);
    const exitCode = await runCommand(command, args);

    if (exitCode !== 0) {
      console.error(`✖ ${label} failed with exit code ${exitCode ?? 'null'}.`);
      failures.push({ label, exitCode });
    } else {
      console.log(`✔ ${label} completed successfully.`);
    }
  }

  if (failures.length > 0) {
    console.error('\nSmoke suites completed with failures:');
    for (const { label, exitCode } of failures) {
      console.error(`  • ${label} (exit code: ${exitCode ?? 'null'})`);
    }

    process.exit(1);
  }

  console.log('\nAll smoke suites completed successfully.');
}

function runCommand(command: string, args: string[]): Promise<number | null> {
  return new Promise((resolve) => {
    const child = spawn(command, args, {
      stdio: 'inherit',
      env,
    });

    child.on('close', (code) => {
      resolve(code);
    });

    child.on('error', (error) => {
      console.error(`Failed to start command \"${command}\":`, error);
      resolve(1);
    });
  });
}

runSequentially().catch((error) => {
  console.error('Unexpected error while orchestrating smoke suites:', error);
  process.exit(1);
});
