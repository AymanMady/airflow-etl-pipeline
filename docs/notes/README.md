# Engineering notes

Short reference notes on the data-engineering practices applied (or worth
applying) in this project. Each note is self-contained.

- [Idempotent loads](idempotent-loads.md) — running a load twice must not change the result
- [Slowly changing dimensions (type 2)](scd-type-2.md) — keeping history of dimension attributes
- [Testing data pipelines](testing-data-pipelines.md) — unit, integration and data tests
- [Late-arriving data](late-arriving-data.md) — event time, watermarks and corrections
- [Table grain](table-grain.md) — declare what one row means before writing any SQL
- [Partitioning](partitioning.md) — choosing partition keys for lakes and warehouses
