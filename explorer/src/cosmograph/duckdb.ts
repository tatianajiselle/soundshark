import type { CosmographProps } from "@cosmograph/react";
import { AsyncDuckDB, VoidLogger, selectBundle } from "@duckdb/duckdb-wasm";
import ehModule from "@duckdb/duckdb-wasm/dist/duckdb-eh.wasm?url";
import ehWorker from "@duckdb/duckdb-wasm/dist/duckdb-browser-eh.worker.js?url";
import mvpModule from "@duckdb/duckdb-wasm/dist/duckdb-mvp.wasm?url";
import mvpWorker from "@duckdb/duckdb-wasm/dist/duckdb-browser-mvp.worker.js?url";

export type DuckDBConnection = Exclude<CosmographProps["duckDBConnection"], string | undefined>;

const absolute = (url: string) => new URL(url, document.baseURI).href;

export async function openDuckDB(): Promise<DuckDBConnection> {
  const bundle = await selectBundle({
    mvp: { mainModule: absolute(mvpModule), mainWorker: absolute(mvpWorker) },
    eh: { mainModule: absolute(ehModule), mainWorker: absolute(ehWorker) },
  });
  if (!bundle.mainWorker) throw new Error("no DuckDB worker for this browser");
  const worker = new Worker(bundle.mainWorker);
  const duckdb = new AsyncDuckDB(new VoidLogger(), worker);
  await duckdb.instantiate(bundle.mainModule, bundle.pthreadWorker);
  const connection = await duckdb.connect();
  return { duckdb, connection };
}
