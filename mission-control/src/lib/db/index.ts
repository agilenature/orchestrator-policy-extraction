/**
 * Database connection singleton for Mission Control.
 *
 * Provides a lazily-initialized better-sqlite3 connection with WAL mode
 * and the episode schema already created. API routes import getDb() to
 * get the shared connection.
 *
 * The database file defaults to `data/mission-control.db` relative to
 * the project root, configurable via MC_DB_PATH environment variable.
 *
 * @module db
 */

import Database from "better-sqlite3";
import path from "path";
import { initEpisodeSchema } from "./schema-episodes";

let _db: Database.Database | null = null;

/**
 * Get the shared database connection.
 *
 * Lazily creates the connection on first call and initializes the
 * episode schema. Subsequent calls return the same instance.
 *
 * @returns A better-sqlite3 Database instance.
 */
export function getDb(): Database.Database {
  if (!_db) {
    const dbPath =
      process.env.MC_DB_PATH ??
      path.resolve(process.cwd(), "data", "mission-control.db");

    _db = new Database(dbPath);
    initEpisodeSchema(_db);
  }
  return _db;
}

export default getDb;
