// apps/desktop/src/main/services/publish-log.ts
//
// A small diagnostic bus for the "Publish to Leaderboard" flow. publish-score.ts
// records each scoreboard attempt here; the lines are (a) persisted to debug.log,
// (b) kept in a bounded in-memory backlog, and (c) streamed live to the renderer
// so the Eval Studio "Publish logs" panel can show them without tailing a file.

import { EventEmitter } from 'events';
import { log as fileLog } from '../debug-log';

const MAX_BACKLOG = 200;
const buffer: string[] = [];
const emitter = new EventEmitter();
emitter.setMaxListeners(0); // any number of windows may subscribe

/** Record a publish/scoreboard diagnostic line. */
export function publishLog(message: string): void {
  fileLog(message);
  const line = `[${new Date().toISOString()}] ${message}`;
  buffer.push(line);
  if (buffer.length > MAX_BACKLOG) buffer.splice(0, buffer.length - MAX_BACKLOG);
  emitter.emit('line', line);
}

/** Snapshot of recent lines, for a renderer that just mounted. */
export function getPublishLog(): string[] {
  return [...buffer];
}

/** Subscribe to live lines; returns an unsubscribe fn. */
export function onPublishLog(listener: (line: string) => void): () => void {
  emitter.on('line', listener);
  return () => emitter.off('line', listener);
}
