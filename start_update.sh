{
  pdm run python3 -u -m scripts.source_eh;
  pdm run python3 -u -m scripts.source_db;
  pdm run python3 -u -m scripts.source_ds;
  pdm run python3 -u -m scripts.source_md;
  pdm run python3 -u -m scripts.build_image_hashes;
  pdm run python3 -u -m scripts.build_index;
  pdm run python3 -u -m scripts.collate_statistics;
} &> data/update.log
