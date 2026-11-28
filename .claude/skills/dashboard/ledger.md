# Dashboard version ledger

Every `ArtifactData` write to an existing document needs the document's current version as its pin. `tools/agent/dash_rows.py` keeps those versions in a ledger, `OUT_DIR/versions.json`, so the coordinator does not have to type them.

- Each write the helper emits records the version it will leave: the pin plus one.
- `--if-version DOC=N` overrides the ledger for one write.
- A `new-row` with no pin records nothing, because the row may already exist at a higher version. The next `row` for it asks for `ledger-sync`.
- `sync-prs` takes each row's version from the row file a fresh `list` saved, and writes it into the ledger. A ledger that ran ahead after a refused or unapplied batch is corrected at the next sync.
- The ledger is saved when the writes are emitted, not when `ArtifactData` applies them. After a version mismatch, `list` the collection with `out_dir`, save `{doc_id: version}` to a file and run `dash_rows.py OUT_DIR --wave W ledger-sync <file>`.
- One coordinator writes to one `OUT_DIR`. The ledger has no lock.
