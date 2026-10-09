# Prototype SQLite backup V1

`tools/prototype_backup.py` provides a local-only backup and restore tool for
`PrototypeStore` databases. It accepts trusted filesystem paths on the command
line and is not exposed through HTTP or the client API.

The `.cpbackup` file contains a fixed magic header, a four-byte big-endian
manifest length, canonical JSON, and the SQLite database bytes. The manifest
binds the database byte count, SHA-256, and row counts for `projects`,
`sessions`, and `feedback`. Keeping the bundle as one file allows publication
through a no-replace atomic rename on Windows or a hard link on other platforms.
An existing destination cannot be replaced. The temporary file is created
beside the destination.

Backup opens the source read-only and uses SQLite's online backup API, which
captures a transactionally consistent snapshot while the store uses WAL. The
source is never intentionally modified. Before publication, the snapshot must
pass SQLite integrity and foreign-key checks and match the prototype store's
three-table schema. Database and manifest limits are 128 MiB and 16 KiB.
Source file/page limits are checked before copying and rechecked in the online
backup callback and completed snapshot. Copy progress is limited to 16,384
callbacks and 30 seconds of monotonic elapsed time. This operational timeout
is not a mathematical infeasibility result. Bundle reads are bounded even if
the file grows between metadata inspection and reading.

Restore checks the bundle framing, manifest, database hash, exact schema,
integrity, foreign keys, and row counts before publication. A destination may
be a new database filename or a new directory (which receives
`prototype.sqlite3`). Existing paths, symlinks, and source/bundle conflicts are
rejected. Restore never replaces a database in place.
Windows restricted execution may deny final-path resolution or atomic publication;
the tool reports failure instead of substituting an overwrite/copy fallback.

The SHA-256 detects accidental or untrusted bundle changes only when compared
with a trusted manifest; a bundle does not authenticate who created it.
Successful backup/restore establishes data integrity for the stored SQLite
snapshot, not CrochetIR verification, physical correctness, or physical proof.

```powershell
python tools/prototype_backup.py backup .\data\prototype.sqlite3 .\backup.cpbackup
python tools/prototype_backup.py restore .\backup.cpbackup .\recovered\
```
