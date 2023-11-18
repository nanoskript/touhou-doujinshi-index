# touhou-doujinshi-index

[Website](https://scarlet.nsk.sh/)

A searchable database of Touhou doujinshi translations.

## Project structure

- `scripts` - Python scripts for scraping entries and building the database.
    - `source_*.py` - Scripts for scraping entries from sites.
    - `data_*.py` - Scripts for sourcing metadata through various methods.
    - `build_image_hashes.py` - Transforms images into perceptual image hashes.
    - `build_index.py` - Processes entries to build the final database.
    - `entry.py` - Defines a common interface for working with data across all sites.
- `app.py` - Entry point for the public Flask web server.
- `templates` - Templates for constructing HTML pages.

## Lifecycle

1. On a daily basis, the update process is initiated.
2. New entries are sourced from each site and added to their respective databases.
3. Image hashes are generated for all images from each site.
4. Images and entries are linked together into one central database file.
5. The database file used by the web server is atomically updated in-place.
