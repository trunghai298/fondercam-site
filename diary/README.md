# Development diary

`/diary/` is generated. Edit the entries, not `diary/index.html`.

## Add an entry

1. **Images.** Put each image in `diary/img/` as a JPEG: about 1600 px on the long edge,
   quality around 80, and no metadata:

   ```sh
   exiftool -overwrite_original -all= -tagsfromfile @ -icc_profile diary/img/your-image.jpg
   ```

   Only publish your own photos, and no identifiable faces.

2. **Entry.** Add `diary/entries/YYYY-MM-DD-short-slug.json`. The file name (without `.json`)
   becomes the entry's anchor, e.g. `/diary/#2026-09-27-film-roll`.

   ```json
   {
     "date": "2026-09-27",
     "chapter": "film-roll",
     "title": "Film Roll, in progress",
     "body": [
       "A paragraph. **bold**, *italic*, `code` and [links](https://example.com) work.",
       {"list": ["a bullet", "another"]},
       {"steps": ["a numbered step", "the next one"]},
       {"table": {"head": ["Column", "Column"], "rows": [["a", "b"]]}},
       {"note": "A small grey line, e.g. under a table."}
     ],
     "images": [
       {"file": "img/your-image.jpg", "alt": "What is in the picture.", "caption": "What it shows and where it came from."}
     ]
   }
   ```

   `images` is optional. Every image needs `alt` and `caption`; width and height are read
   from the file.

3. **Chapter.** `chapter` must be an `id` from `diary/chapters.json`. To start a new chapter,
   add `{"id": "...", "title": "...", "intro": "optional one line"}` to that list; chapters
   appear in the order they are listed there.

4. **Build** from the repository root, then commit `diary/index.html` with the rest:

   ```sh
   python3 tools/build_diary.py
   ```

   It needs only Python 3. It stops with a message if an entry names an unknown chapter,
   has no date, or points at a missing image.

## Look

The page's styles are in `diary/diary.css` (fonts from `/fonts`, tokens and header/footer
as on the homepage). The page is English only.

## Order

Chapters appear in the order of `chapters.json`; inside a chapter, entries run oldest
first. The header links to the newest entry.
