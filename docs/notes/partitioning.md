# Partitioning

Partitioning splits a table into independent chunks so queries and loads only
touch the data they need.

## Choosing a key

- Use the column most queries filter on, usually a date.
- Aim for partitions of roughly 100 MB to 1 GB of compressed data.
- Avoid high-cardinality keys (user id): they produce millions of tiny files.

## Spark / Delta

```python
df.write.partitionBy("order_date").format("delta").save(path)
```

Daily partitions on small data are often too fine; monthly may be enough.

## PostgreSQL

Declarative partitioning (`PARTITION BY RANGE (order_date)`) helps retention
(drop a partition instead of a `DELETE`) more than query speed on small tables.

## Check partition pruning

Look at the query plan (`EXPLAIN`, Spark UI) and confirm only the expected
partitions are scanned.
