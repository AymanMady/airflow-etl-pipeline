# Medallion architecture

## Bronze

Raw data as received, append-only, with ingestion metadata (source file,
ingestion time). Never modified, so everything can be rebuilt from it.

## Silver

Cleaned and conformed: types cast, duplicates removed, invalid rows sent to
quarantine, keys standardised. One table per business entity or event.

## Gold

Business-level aggregates and dimensional models ready for BI and ML.

## Rules

- Data flows one way: bronze → silver → gold.
- Each layer is reproducible from the previous one.
- Quality checks run at each boundary; gold is only published when they pass.
