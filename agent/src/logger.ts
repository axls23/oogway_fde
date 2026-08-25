// Minimal structured JSON logger. One line per call, always includes
// trace_id so a single grep spans this service and `api` (architecture.md
// §11). Deliberately not a dependency — this is the entire surface we need
// and pulling in pino/winston for it would be a drive-by addition the
// CLAUDE.md forbidden-patterns list warns against.

export type LogLevel = "debug" | "info" | "warn" | "error";

interface LogFields {
  trace_id?: string;
  session_id?: string;
  [key: string]: unknown;
}

function emit(level: LogLevel, msg: string, fields: LogFields = {}): void {
  const line = {
    ts: new Date().toISOString(),
    level,
    service: "agent",
    msg,
    ...fields,
  };
  // stderr for warn/error so container log drivers can split streams by
  // severity if configured to; stdout otherwise.
  const stream = level === "error" || level === "warn" ? process.stderr : process.stdout;
  stream.write(`${JSON.stringify(line)}\n`);
}

export const log = {
  debug: (msg: string, fields?: LogFields) => emit("debug", msg, fields),
  info: (msg: string, fields?: LogFields) => emit("info", msg, fields),
  warn: (msg: string, fields?: LogFields) => emit("warn", msg, fields),
  error: (msg: string, fields?: LogFields) => emit("error", msg, fields),
};
