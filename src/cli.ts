#!/usr/bin/env node
import { basename } from 'node:path';
import { Command } from 'commander';
import { runLogin, runLogout, runUpdate, runWhoami } from './auth/commands.js';
import { withLicense } from './auth/heartbeat.js';
import { runAudit } from './commands/audit.js';
import { runDoctor } from './commands/doctor.js';
import { runInit } from './commands/init.js';
import { runUi } from './commands/ui.js';
import { runWatch } from './commands/watch.js';
import { CLI_VERSION } from './version.js';

const program = new Command();
const binaryName = basename(process.argv[1] ?? 'mrtoken');

program
  .name(binaryName)
  .description('Local-first Claude Code hook collector and terminal token audit CLI.')
  .version(CLI_VERSION);

program
  .command('login')
  .argument('<key>', 'Mr Token license key')
  .description('Verify and store a Mr Token license key.')
  .action(runLogin);

program
  .command('logout')
  .description('Remove the stored Mr Token license key.')
  .action(runLogout);

program
  .command('whoami')
  .description('Show the current Mr Token license status.')
  .action(runWhoami);

program
  .command('init')
  .description('Create the local database and install Claude Code hooks.')
  .option('--settings <path>', 'Claude settings file to update')
  .option('--db <path>', 'SQLite database path')
  .action(withLicense(runInit));

program
  .command('audit')
  .description('Print a local terminal audit report.')
  .option('--db <path>', 'SQLite database path')
  .action(withLicense(runAudit));

program
  .command('watch', { hidden: true })
  .description('Collect a Claude Code hook event.')
  .option('--db <path>', 'SQLite database path')
  .option('--events <path>', 'JSONL event log path')
  .option('--hook-event <name>', 'Claude Code hook event name')
  .option('--stdin', 'Read one event JSON object from stdin')
  .option('--event <json>', 'Read one event JSON object from an argument')
  .action(runWatch);

program
  .command('doctor')
  .description('Check local setup, hook config, and database status.')
  .option('--settings <path>', 'Claude settings file to inspect')
  .option('--db <path>', 'SQLite database path')
  .action(withLicense(runDoctor));

program
  .command('ui')
  .description('Start the local Mr Token web UI.')
  .option('--port <number>', 'Localhost port', '4317')
  .option('--no-open', 'Do not open a browser')
  .option('--db <path>', 'SQLite database path')
  .action(withLicense(runUi));

program
  .command('update')
  .description('Download the latest Mr Token installer package.')
  .action(withLicense(runUpdate));

await program.parseAsync();
