import { appendFileSync, writeFileSync } from 'fs';
import { join } from 'path';
import { app } from 'electron';

const debugLogPath = join(app.getPath('userData'), 'debug.log');

// Truncate on each app launch
try {
  writeFileSync(debugLogPath, `=== ScreamingFace launch ${new Date().toISOString()} ===\n`);
} catch {}

export function log(msg: string): void {
  const line = `[${Date.now()}] ${msg}\n`;
  try {
    appendFileSync(debugLogPath, line);
  } catch {}
}
