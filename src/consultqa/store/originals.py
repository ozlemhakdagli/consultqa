"""Keeps the uploaded original of each document so the web page can show it later.

Each file is named after its document id, so the id is checked before any path is built.
A document id is 32 lowercase hex characters, which rules out path separators and dots.
"""

import re
import shutil
from collections.abc import Iterable
from pathlib import Path

_DOC_ID = re.compile(r"^[0-9a-f]{32}$")

_MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".txt": "text/plain; charset=utf-8",
    ".md": "text/markdown; charset=utf-8",
}


def _is_doc_id(doc_id: str) -> bool:
    return _DOC_ID.fullmatch(doc_id) is not None


class OriginalFiles:
    """A folder holding one original file per document id."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def save(self, doc_id: str, source: Path) -> Path:
        """Copy the source file into the folder under the document id, keeping its suffix."""
        if not _is_doc_id(doc_id):
            raise ValueError(f"not a document id: {doc_id!r}")
        self._root.mkdir(parents=True, exist_ok=True)
        target = self._root / f"{doc_id}{source.suffix.lower()}"
        shutil.copyfile(source, target)
        return target

    def path(self, doc_id: str) -> Path | None:
        """Return the stored file for this id, or None if there is none or the id is malformed."""
        if not _is_doc_id(doc_id):
            return None
        matches = sorted(self._root.glob(f"{doc_id}.*"))
        return matches[0] if matches else None

    def delete(self, doc_id: str) -> None:
        """Remove the stored file for this id. Deleting a missing file is not an error."""
        found = self.path(doc_id)
        if found is not None:
            found.unlink(missing_ok=True)

    def delete_many(self, doc_ids: Iterable[str]) -> None:
        """Remove the stored files for several ids."""
        for doc_id in doc_ids:
            self.delete(doc_id)

    def media_type(self, path: Path) -> str:
        """Return the content type to send with this file, based on its suffix."""
        return _MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream")
