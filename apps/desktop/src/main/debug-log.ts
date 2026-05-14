import { appendFileSync, mkdirSync, writeFileSync } from 'fs';
import { join } from 'path';
import { getUserDataPath } from './user-data-path';

const debugLogDir = getUserDataPath();
const debugLogPath = join(debugLogDir, 'debug.log');

// Truncate on each app launch
try {
  mkdirSync(debugLogDir, { recursive: true });
  writeFileSync(debugLogPath, `=== ScreamingFace launch ${new Date().toISOString()} ===\n`);
} catch {}

export function log(msg: string): void {
  const line = `[${Date.now()}] ${msg}\n`;
  try {
    appendFileSync(debugLogPath, line);
  } catch {}
}
