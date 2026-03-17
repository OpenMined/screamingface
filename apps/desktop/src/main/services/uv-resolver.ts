import { execFileSync } from 'child_process';
import { existsSync } from 'fs';
import { join } from 'path';
import { homedir } from 'os';
import { is } from '@electron-toolkit/utils';

const KNOWN_PATHS = [
  join(homedir(), '.cargo', 'bin', 'uv'),
  join(homedir(), '.local', 'bin', 'uv'),
  '/usr/local/bin/uv',
  '/opt/homebrew/bin/uv',
];

export function resolveUv(): string | null {
  // Production: check bundled uv first
  if (!is.dev) {
    const bundled = join(process.resourcesPath, 'server', 'bin', 'uv');
    if (existsSync(bundled)) return bundled;
  }

  // Try PATH first
  try {
    const result = execFileSync('which', ['uv'], { encoding: 'utf-8' }).trim();
    if (result) return result;
  } catch {
    // not on PATH
  }

  // Check known locations
  for (const p of KNOWN_PATHS) {
    if (existsSync(p)) return p;
  }

  return null;
}
