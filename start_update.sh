run() {
  echo "[stage] $1 $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  pdm run python3 -u -m "scripts.$1"
}

# Detached: Coolify kills the task's ssh session after 1h and retries it,
# spawning concurrent runs (coollabsio/coolify#8435).
{
  run source_eh;
  run source_db;
  run source_ds;
  run source_md;
  run source_mb;
  run source_tora;
  # run source_px;
  run build_image_hashes &&
  run build_index &&
  run collate_statistics;
  echo "[stage] end $(date -u +%Y-%m-%dT%H:%M:%SZ)"
} &> data/update.log < /dev/null &

echo "[detached] update running, follow data/update.log"
