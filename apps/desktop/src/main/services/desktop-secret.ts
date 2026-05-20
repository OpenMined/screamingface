import {
  existsSync,
  mkdirSync,
  openSync,
  readFileSync,
  writeFileSync,
  closeSync,
  chmodSync,
} from 'fs';
import { dirname, join } from 'path';
import { randomBytes } from 'crypto';
import { app } from 'electron';

const SECRET_BYTES = 32;

export function getDesktopSecretPath(): string {
  return join(app.getPath('userData'), '.sf', 'runtime', 'desktop.secret');
}

export function getDesktopSecretValue(): string {
  const path = getDesktopSecretPath();
  if (existsSync(path)) {
    return readFileSync(path, 'utf-8').trim();
  }

  mkdirSync(dirname(path), { recursive: true });
  const secret = randomBytes(SECRET_BYTES).toString('base64url');
  const fd = openSync(path, 'w', 0o600);
  try {
    writeFileSync(fd, secret + '\n', 'utf-8');
  } finally {
    closeSync(fd);
  }
  chmodSync(path, 0o600);
  return secret;
}

export function desktopSecretHeader(): Record<string, string> {
  return { 'X-SF-Desktop-Secret': getDesktopSecretValue() };
}
