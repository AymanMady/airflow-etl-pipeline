# Orchestration best practices

- **Small, idempotent tasks**: a failed task can be retried alone.
- **Logical dates**: tasks process `data_interval_start`/`end`, not "now".
- **No heavy work in the DAG file**: top-level code runs at every parse.
- **Pass references, not data**: exchange paths or table names between tasks,
  not datasets through XCom.
- **Explicit dependencies**: use sensors or dataset-based scheduling rather
  than guessing upstream completion times.
- **Bounded concurrency**: `max_active_runs` and pools protect sources.
- **Timeouts and SLAs** on every task so a hang becomes an alert.
- **Same image everywhere**: dev, CI and prod run the same container.
