import os
from typing import Optional
from pathlib import Path


def read_local_file(file_path: str, max_chars: int = 10000) -> str:
    """Read content from a local file.

    Args:
        file_path: Path to the file to read (can be absolute or relative)
        max_chars: Maximum number of characters to return (default: 10000)

    Returns:
        The content of the file or an error message
    """
    try:
        # Convert to Path object for better path handling
        path = Path(file_path).resolve()

        # Check if file exists
        if not path.exists():
            return f"Error: File not found: {file_path}"

        # Check if it's actually a file (not a directory)
        if not path.is_file():
            return f"Error: Path is not a file: {file_path}"

        # Get file size
        file_size = path.stat().st_size

        # Try to read as text
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read(max_chars)

            # Add truncation notice if file is larger
            if file_size > max_chars:
                content += f"\n\n[Content truncated. File size: {file_size} bytes, showing first {max_chars} characters]"

            return content

        except UnicodeDecodeError:
            # If it's a binary file, provide info instead
            return f"Error: File appears to be binary. File size: {file_size} bytes. Cannot display binary content as text."

    except PermissionError:
        return f"Error: Permission denied to read file: {file_path}"
    except Exception as e:
        return f"Error reading file: {str(e)}"


if __name__ == "__main__":
    # Test the function
    test_file = "test.txt"
    content = read_local_file(test_file)
    print(content)