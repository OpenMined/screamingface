import { mkdirSync } from 'fs';
import { resolve } from 'path';
import { app } from 'electron';

const USER_DATA_OVERRIDE_ENV = 'SCREAMINGFACE_USER_DATA_DIR';

export function getUserDataPath(): string {
  const override = process.env[USER_DATA_OVERRIDE_ENV];
  if (override) {
    const dir = resolve(override);
    mkdirSync(dir, { recursive: true });
    return dir;
  }
  return app.getPath('userData');
}
