# Benchmark data attribution

All final inputs were downloaded from the UCI Machine Learning Repository on 20 September 2026. UCI identifies the three datasets as CC BY 4.0. This folder preserves the original CSV members; SHA256 checksums and archive URLs are in [manifest.json](manifest.json).

| File | Original dataset / attribution | DOI |
|---|---|---|
| bank.csv | Moro, S., Rita, P., and Cortez, P. (2014), Bank Marketing | https://doi.org/10.24432/C5K306 |
| student-mat.csv | Cortez, P. (2008), Student Performance | https://doi.org/10.24432/C5TG7T |
| winequality-red.csv | Cortez, P., Cerdeira, A., Almeida, F., Matos, T., and Reis, J. (2009), Wine Quality | https://doi.org/10.24432/C56S3T |

Primary landing pages: [banking](https://archive.ics.uci.edu/dataset/222/bank+marketing), [education](https://archive.ics.uci.edu/dataset/320/student+performance), [wine quality](https://archive.ics.uci.edu/dataset/186/wine+quality).

Benchmark transformations are documented in the report: selecting columns, mapping the banking target, dropping exact duplicate projected rows, splitting, and fitting transforms only on training partitions. The raw files here are unmodified. Generated output is research/PoC output, not a statement about current populations.

The separate mirror_manifest.json records an intermediate acquisition attempt. Those hashes do not identify the final raw files. The primary manifest is authoritative for this experiment. A rejected 11,162-row banking mirror was not used. Data distribution comparisons to published experiments must account for our selected features and deduplication.
