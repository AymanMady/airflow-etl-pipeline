# Logging in pipelines

## What every run should log

- Start and end of each step, with duration.
- Input and output row counts, and rows rejected with the reason.
- The parameters: logical date, source, target, configuration version.

## Format

- One event per line, with a stable prefix or structured fields
  (`step=load table=orders rows=1520 duration_s=3.2`). Easy to grep and to
  parse into a log tool.
- Use levels consistently: `INFO` for progress, `WARNING` for handled data
  issues, `ERROR` for failures.

## What never to log

Passwords, tokens, full connection strings, personal data. Log identifiers and
counts instead of row contents.

## Python

Configure logging once at the entry point (`logging.basicConfig` or a small
setup module) and use `logging.getLogger(__name__)` in modules. Never call
`print` in library code.
