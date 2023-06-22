import threading

# A single process-wide lock that serializes every mutation of shared on-disk
# state touched by worker threads:
#   - cookies.txt   (write_cookie)
#   - etag.csv      (get_etag's read-modify-append; delete_etag / modify_etag)
#   - PUT/POST/DELETE target files (write_file / os.remove)
#
# Why one global lock is sufficient (C1 strategy):
#   * It is the *only* lock, so a thread can never hold one lock while waiting on
#     another -> no lock-ordering deadlock is possible.
#   * It is acquired only at the leaf functions that perform the I/O, and those
#     functions never call each other, so it is never acquired re-entrantly ->
#     a plain (non-reentrant) Lock is safe.
#   * Holding it across the whole read-modify-write of etag.csv makes that
#     sequence atomic, so no thread can read a half-written CSV.
#
# It is intentionally coarse-grained: C1 prioritizes correctness (no interleaved
# or corrupt writes, no lost updates) over throughput. A finer-grained,
# per-resource scheme or a single-writer queue is the C1q refinement.
write_lock = threading.Lock()
