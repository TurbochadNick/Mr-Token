#!/usr/bin/env node
import { Command } from 'commander';
import { runAudit } from './commands/audit.js';
import { runDoctor } from './commands/doctor.js';
import { runInit } from './commands/init.js';
import { runWatch } from './commands/watch.js';

const program = new Command();

program
  .name('token-tithe')
  .description('Local-first Claude Code hook collector and terminal token audit CLI.')
  .version('0.1.0');

program
  .command('init')
  .description('Create the local database and install Claude Code hooks.')
  .option('--settings <path>', 'Claude settings file to update')
  .option('--db <path>', 'SQLite database path')
  .action(runInit);

program
  .command('audit')
  .description('Print a local terminal audit report.')
  .option('--db <path>', 'SQLite database path')
  .action(runAudit);

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
  .action(runDoctor);

await program.parseAsync();
