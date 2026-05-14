import { getMainWindow } from '../window-registry';

export function broadcastToRenderers(channel: string, ...args: unknown[]): void {
  const win = getMainWindow();
  if (!win || win.isDestroyed() || win.webContents.isDestroyed()) return;

  try {
    win.webContents.send(channel, ...args);
  } catch {
    // Renderer frames can be disposed during reload/quit while backend processes
    // are still emitting logs. Dropping that event is safer than wedging startup.
  }
}
