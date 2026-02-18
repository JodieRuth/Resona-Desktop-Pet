import os
import glob
from pathlib import Path
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("FilesystemTools")


@mcp.tool()
def list_directory(path: str) -> list[str]:
    """List all files and subdirectories in the specified path."""
    try:
        target = Path(path)
        if not target.exists():
            return [f"Error: Path not found: {path}"]
        if not target.is_dir():
            return [f"Error: Path is not a directory: {path}"]
        return [p.name for p in target.iterdir()]
    except Exception as e:
        return [f"Error: {e}"]


@mcp.tool()
def read_file(path: str, start_line: int = 1, end_line: int = -1) -> str:
    """Read the content of a file. Supports reading specific line ranges (1-based)."""
    try:
        target = Path(path)
        if not target.exists():
            return f"Error: File not found: {path}"
        if not target.is_file():
            return f"Error: Path is not a file: {path}"
        with target.open("r", encoding="utf-8") as f:
            lines = f.readlines()
        total = len(lines)
        if start_line < 1:
            start_line = 1
        if end_line == -1 or end_line > total:
            end_line = total
        if start_line > total:
            return ""
        return "".join(lines[start_line - 1:end_line])
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def count_lines(path: str) -> int:
    """Get the total number of lines in a file."""
    try:
        target = Path(path)
        if not target.exists() or not target.is_file():
            return -1
        with target.open("r", encoding="utf-8") as f:
            return sum(1 for _ in f)
    except Exception:
        return -1


@mcp.tool()
def search_files(directory: str, pattern: str) -> list[str]:
    """Search for files in a directory using a glob pattern (e.g., '*.txt')."""
    try:
        base = Path(directory)
        if not base.exists() or not base.is_dir():
            return [f"Error: Directory not found: {directory}"]
        search_path = str(base / pattern)
        return glob.glob(search_path, recursive=True)
    except Exception as e:
        return [f"Error: {e}"]


@mcp.tool()
def edit_lines(path: str, start_line: int, end_line: int, new_content: str) -> str:
    """Replace a range of lines in a file with new content. 1-based indexing."""
    try:
        target = Path(path)
        if not target.exists():
            return f"Error: File not found: {path}"
        if not target.is_file():
            return f"Error: Path is not a file: {path}"
        with target.open("r", encoding="utf-8") as f:
            lines = f.readlines()
        total = len(lines)
        if start_line < 1 or end_line < start_line:
            return "Error: Invalid line range."
        if start_line > total:
            return f"Error: Start line out of range: {start_line}"
        if end_line > total:
            end_line = total
        replacement = new_content.splitlines(keepends=True)
        if new_content and not new_content.endswith("\n"):
            replacement.append("\n")
        lines[start_line - 1:end_line] = replacement
        with target.open("w", encoding="utf-8") as f:
            f.writelines(lines)
        return f"OK: Edited lines {start_line}-{end_line} in {path}"
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def write_file(path: str, content: str) -> str:
    """Write content to a file. Overwrites if exists, creates if not."""
    try:
        target = Path(path)
        if target.parent and not target.parent.exists():
            return f"Error: Parent directory does not exist: {target.parent}"
        with target.open("w", encoding="utf-8") as f:
            f.write(content)
        return f"OK: Wrote file {path}"
    except Exception as e:
        return f"Error: {e}"


if __name__ == "__main__":
    mcp.run()
