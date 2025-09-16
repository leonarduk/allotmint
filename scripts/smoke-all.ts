import { spawn } from 'child_process';

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

const commands: Command[] = [
  {
    command: 'tsx',
    args: ['scripts/frontend-backend-smoke.ts'],
    label: 'backend smoke suite',
  },
  {
    command: 'npm',
    args: ['--prefix', 'frontend', 'run', 'smoke:frontend'],
    label: 'frontend smoke suite',
  },
];

async function runSequentially() {
  for (const { command, args, label } of commands) {
    console.log(`\n▶ Running ${label}...`);
    const exitCode = await runCommand(command, args);

    if (exitCode !== 0) {
      console.error(`✖ ${label} failed with exit code ${exitCode ?? 'null'}.`);
      process.exit(exitCode ?? 1);
    }

    console.log(`✔ ${label} completed successfully.`);
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
