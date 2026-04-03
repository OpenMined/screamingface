import { registerServerHandlers } from './server-process.ipc';
import { registerVenvHandlers } from './venv-manager.ipc';
import { registerPluginHandlers } from './plugin-manager.ipc';
import { registerConfigHandlers } from './config.ipc';
import { registerSessionHandlers } from './session.ipc';

export function registerAllHandlers(): void {
  registerConfigHandlers();
  registerVenvHandlers();
  registerServerHandlers();
  registerPluginHandlers();
  registerSessionHandlers();
}
