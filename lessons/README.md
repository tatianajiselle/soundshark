# Lessons

Practice files for learning async Python while building wavelength. Each lesson's concept ends up in the real crawler in `src/wavelength/`.

| # | Concept | Lands in the crawler as |
|---|---------|-------------------------|
| 0 | One thread taking turns; `await` vs `time.sleep` | ✅ done |
| 1 | Coroutines vs tasks, `gather`, `TaskGroup` | fetching many pages at once |
| 2 | `asyncio.Queue` + workers, `Semaphore` | the crawl engine + rate limits |
| 3 | Timeouts, retries, cancellation, shutdown | a crawler that survives the real internet |
| 4 | Async generators, async DB | pagination + saving the graph |
| 5 | CPU work off the loop, backpressure | v2 audio analysis |
| 6 | FastAPI | the explorer |
