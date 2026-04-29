"""
OpenClaw Skill — File Management
==================================
File operations using pathlib/shutil with watchdog directory monitoring.
"""

import os
import shutil
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional, Callable
from collections import defaultdict


class FileManager:
    """
    Manages file operations: move, copy, rename, delete, organize.
    Integrates with watchdog for directory monitoring.
    """

    # File type categories for organization
    FILE_CATEGORIES = {
        "documents": {".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt", ".xls", ".xlsx", ".ppt", ".pptx", ".csv"},
        "images": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp", ".ico", ".tiff"},
        "videos": {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm", ".m4v"},
        "audio": {".mp3", ".wav", ".flac", ".aac", ".ogg", ".wma", ".m4a"},
        "archives": {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"},
        "code": {".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".cpp", ".c", ".h", ".go", ".rs", ".rb", ".php", ".html", ".css", ".json", ".yaml", ".yml", ".xml", ".md"},
        "executables": {".exe", ".msi", ".dmg", ".app", ".deb", ".rpm", ".sh", ".bat"},
    }

    def __init__(self, broadcast: Optional[Callable] = None):
        self.broadcast = broadcast
        self.confirm_deletions = os.getenv("CONFIRM_DELETIONS", "true").lower() == "true"
        self._watcher = None

    @staticmethod
    def _resolve(path: str) -> str:
        """
        Resolve a path to an absolute string, expanding:
          - $env:USERPROFILE  (PowerShell env var)
          - %USERPROFILE%     (cmd env var)
          - ~                 (Unix home shorthand)
        """
        home = Path.home()
        p = path.strip()
        # PowerShell style
        p = p.replace("$env:USERPROFILE", str(home))
        p = p.replace("$env:USERNAME",    os.environ.get("USERNAME", ""))
        # cmd style
        p = p.replace("%USERPROFILE%",    str(home))
        p = p.replace("%USERNAME%",       os.environ.get("USERNAME", ""))
        # Unix home
        p = p.replace("~", str(home))
        # Normalise slashes
        return str(Path(p))

    async def execute(self, action: str, params: dict) -> str:
        """Dispatch a file action."""
        # Resolve env vars / ~ in all path-like string params
        resolved = {}
        for k, v in params.items():
            resolved[k] = self._resolve(v) if isinstance(v, str) else v

        actions = {
            "move":            self.move,
            "copy":            self.copy,
            "rename":          self.rename,
            "delete":          self.delete,
            "organize_by_type": self.organize_by_type,
            "organize_by_date": self.organize_by_date,
            "find_duplicates": self.find_duplicates,
            "list_dir":        self.list_directory,
            "watch":           self.start_watch,
        }
        handler = actions.get(action)
        if not handler:
            raise ValueError(f"Unknown file action: {action}")
        return await handler(**resolved)

    async def move(self, source: str, destination: str, **kwargs) -> str:
        """Move a file or directory."""
        src = Path(source)
        dst = Path(destination)
        if not src.exists():
            raise FileNotFoundError(f"Source not found: {source}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        return f"Moved {source} → {destination}"

    async def copy(self, source: str, destination: str, **kwargs) -> str:
        """Copy a file or directory."""
        src = Path(source)
        dst = Path(destination)
        if not src.exists():
            raise FileNotFoundError(f"Source not found: {source}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(str(src), str(dst))
        else:
            shutil.copy2(str(src), str(dst))
        return f"Copied {source} → {destination}"

    async def rename(self, source: str, new_name: str, **kwargs) -> str:
        """Rename a file or directory."""
        src = Path(source)
        if not src.exists():
            raise FileNotFoundError(f"Source not found: {source}")
        dst = src.parent / new_name
        src.rename(dst)
        return f"Renamed {src.name} → {new_name}"

    async def delete(self, path: str, force: bool = False, **kwargs) -> str:
        """Delete a file or directory (with confirmation by default)."""
        target = Path(path)
        if not target.exists():
            raise FileNotFoundError(f"Not found: {path}")

        if self.confirm_deletions and not force:
            return f"CONFIRM_REQUIRED: Delete {path}? (set force=true to confirm)"

        if target.is_dir():
            shutil.rmtree(str(target))
        else:
            target.unlink()
        return f"Deleted {path}"

    async def organize_by_type(self, directory: str, **kwargs) -> str:
        """Organize files in a directory by file type into subdirectories."""
        dir_path = Path(directory)
        if not dir_path.is_dir():
            raise NotADirectoryError(f"Not a directory: {directory}")

        moved_count = defaultdict(int)

        for file_path in dir_path.iterdir():
            if file_path.is_file():
                ext = file_path.suffix.lower()
                category = self._get_category(ext)
                target_dir = dir_path / category
                target_dir.mkdir(exist_ok=True)
                target = target_dir / file_path.name

                # Handle name conflicts
                if target.exists():
                    stem = file_path.stem
                    suffix = file_path.suffix
                    counter = 1
                    while target.exists():
                        target = target_dir / f"{stem}_{counter}{suffix}"
                        counter += 1

                shutil.move(str(file_path), str(target))
                moved_count[category] += 1

        summary = ", ".join(f"{cat}: {count}" for cat, count in sorted(moved_count.items()))
        return f"Organized {sum(moved_count.values())} files — {summary}"

    async def organize_by_date(self, directory: str, **kwargs) -> str:
        """Organize files by modification date into YYYY-MM subdirectories."""
        dir_path = Path(directory)
        if not dir_path.is_dir():
            raise NotADirectoryError(f"Not a directory: {directory}")

        moved_count = 0

        for file_path in dir_path.iterdir():
            if file_path.is_file():
                mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                date_dir = dir_path / mtime.strftime("%Y-%m")
                date_dir.mkdir(exist_ok=True)

                new_name = f"{mtime.strftime('%Y%m%d')}_{file_path.name}"
                target = date_dir / new_name

                if not target.exists():
                    shutil.move(str(file_path), str(target))
                    moved_count += 1

        return f"Organized {moved_count} files by date"

    async def find_duplicates(self, directory: str, delete: bool = False, **kwargs) -> str:
        """Find duplicate files by content hash."""
        dir_path = Path(directory)
        if not dir_path.is_dir():
            raise NotADirectoryError(f"Not a directory: {directory}")

        hashes = defaultdict(list)

        for file_path in dir_path.rglob("*"):
            if file_path.is_file():
                file_hash = self._hash_file(file_path)
                hashes[file_hash].append(str(file_path))

        duplicates = {h: paths for h, paths in hashes.items() if len(paths) > 1}

        if not duplicates:
            return "No duplicate files found"

        total_dupes = sum(len(paths) - 1 for paths in duplicates.values())
        result = f"Found {total_dupes} duplicate files in {len(duplicates)} groups"

        if delete and not self.confirm_deletions:
            deleted = 0
            for paths in duplicates.values():
                for path in paths[1:]:  # Keep the first, delete the rest
                    Path(path).unlink()
                    deleted += 1
            result += f" — deleted {deleted} duplicates"

        return result

    async def list_directory(self, path: str, recursive: bool = False, **kwargs) -> str:
        """List contents of a directory."""
        dir_path = Path(path)
        if not dir_path.exists():
            raise NotADirectoryError(f"Path not found: {path}")
        if not dir_path.is_dir():
            raise NotADirectoryError(f"Not a directory: {path}")

        items = []
        iterator = dir_path.rglob("*") if recursive else dir_path.iterdir()

        for item in iterator:
            stat = item.stat()
            items.append({
                "name": item.name,
                "path": str(item),
                "type": "dir" if item.is_dir() else "file",
                "size": stat.st_size if item.is_file() else None,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            })

        return str(items[:100])  # Cap at 100 items

    async def start_watch(self, directory: str, **kwargs) -> str:
        """Start watching a directory for changes."""
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler

            class OpenClawHandler(FileSystemEventHandler):
                def __init__(self, broadcast):
                    self.broadcast = broadcast

                def on_created(self, event):
                    if not event.is_directory:
                        print(f"[FileWatcher] New file: {event.src_path}")

                def on_modified(self, event):
                    if not event.is_directory:
                        print(f"[FileWatcher] Modified: {event.src_path}")

                def on_deleted(self, event):
                    print(f"[FileWatcher] Deleted: {event.src_path}")

            observer = Observer()
            handler = OpenClawHandler(self.broadcast)
            observer.schedule(handler, directory, recursive=False)
            observer.start()
            self._watcher = observer
            return f"Watching directory: {directory}"

        except ImportError:
            return "watchdog not installed — cannot watch directories"

    def _get_category(self, extension: str) -> str:
        """Map a file extension to a category."""
        for category, extensions in self.FILE_CATEGORIES.items():
            if extension in extensions:
                return category
        return "other"

    def _hash_file(self, path: Path, block_size: int = 65536) -> str:
        """Calculate MD5 hash of a file."""
        hasher = hashlib.md5()
        with open(path, "rb") as f:
            while True:
                buf = f.read(block_size)
                if not buf:
                    break
                hasher.update(buf)
        return hasher.hexdigest()
