{
  pdm run python3 -m scripts.source_eh;
  pdm run python3 -m scripts.source_db;
  pdm run python3 -m scripts.source_ds;
  pdm run python3 -m scripts.source_md;
  pdm run python3 -m scripts.build_image_hashes;
  pdm run python3 -m scripts.build_index;
} &> data/update.log