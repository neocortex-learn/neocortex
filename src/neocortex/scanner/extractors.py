"""Key file content extractors for project scanning."""

from __future__ import annotations

import re
from pathlib import Path

KEY_FILE_PATTERNS: dict[str, list[str]] = {
    "model": [
        "**/models.py",
        "**/model.py",
        "**/schema.prisma",
        "**/entities/**/*.py",
        "**/entities/**/*.java",
        "**/entities/**/*.kt",
        "**/entities/**/*.go",
        "**/entities/**/*.ts",
    ],
    "route": [
        "**/routes.*",
        "**/urls.py",
        "**/handlers/**/*.py",
        "**/handlers/**/*.go",
        "**/handlers/**/*.ts",
        "**/handlers/**/*.java",
        "**/controllers/**/*.py",
        "**/controllers/**/*.java",
        "**/controllers/**/*.ts",
        "**/controllers/**/*.go",
    ],
    "config": [
        "docker-compose*",
        "nginx.conf",
        ".github/workflows/*",
        ".gitlab-ci.yml",
        "Dockerfile",
    ],
    "test": [
        "**/test_*.py",
        "**/*_test.py",
        "**/*_test.go",
        "**/*.test.ts",
        "**/*.test.js",
        "**/*.test.tsx",
        "**/*.test.jsx",
        "**/spec/**/*.rb",
        "**/spec/**/*.ts",
        "**/spec/**/*.js",
    ],
}

SIGNATURE_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "Python": [
        re.compile(r"^\s*(class\s+\w+.*)"),
        re.compile(r"^\s*(def\s+\w+.*)"),
        re.compile(r"^\s*(async\s+def\s+\w+.*)"),
    ],
    "JavaScript": [
        re.compile(r"^\s*(class\s+\w+.*)"),
        re.compile(r"^\s*(function\s+\w+.*)"),
        re.compile(r"^\s*(export\s+.*)"),
        re.compile(r"^\s*(const\s+\w+\s*=.*)"),
    ],
    "TypeScript": [
        re.compile(r"^\s*(class\s+\w+.*)"),
        re.compile(r"^\s*(function\s+\w+.*)"),
        re.compile(r"^\s*(export\s+.*)"),
        re.compile(r"^\s*(const\s+\w+\s*[:=].*)"),
        re.compile(r"^\s*(interface\s+\w+.*)"),
        re.compile(r"^\s*(type\s+\w+.*)"),
    ],
    "Go": [
        re.compile(r"^\s*(func\s+.*)"),
        re.compile(r"^\s*(type\s+\w+\s+struct.*)"),
        re.compile(r"^\s*(type\s+\w+\s+interface.*)"),
    ],
    "Java": [
        re.compile(r"^\s*(public\s+class\s+.*)"),
        re.compile(r"^\s*(public\s+interface\s+.*)"),
        re.compile(r"^\s*(public\s+.+\(.*\).*)"),
        re.compile(r"^\s*(private\s+.+\(.*\).*)"),
        re.compile(r"^\s*(protected\s+.+\(.*\).*)"),
    ],
    "Kotlin": [
        re.compile(r"^\s*(class\s+.*)"),
        re.compile(r"^\s*(fun\s+.*)"),
        re.compile(r"^\s*(interface\s+.*)"),
        re.compile(r"^\s*(data\s+class\s+.*)"),
        re.compile(r"^\s*(object\s+.*)"),
    ],
}


def extract_key_files(
    project_path: str,
    max_lines: int = 100,
    exclude_patterns: list[str] | None = None,
) -> list[dict]:
    """Extract key file summaries from a project.

    Returns a list of dicts with keys: path, type, content.
    """
    root = Path(project_path)
    exclude = set(exclude_patterns or [])
    results: list[dict] = []
    seen_paths: set[Path] = set()

    for file_type, patterns in KEY_FILE_PATTERNS.items():
        for pattern in patterns:
            for file_path in root.rglob(pattern):
                if not file_path.is_file():
                    continue
                if file_path in seen_paths:
                    continue
                if _should_exclude(file_path, root, exclude):
                    continue
                seen_paths.add(file_path)

                content = _read_file_safe(file_path, max_lines)
                if content is None:
                    continue

                relative = str(file_path.relative_to(root))
                lang = _detect_language(file_path)
                signatures = extract_signatures(content, lang) if lang else ""

                summary = content
                if signatures:
                    summary = f"{content}\n\n# --- Signatures ---\n{signatures}"

                results.append({
                    "path": relative,
                    "type": file_type,
                    "content": summary,
                })

    return results


def extract_signatures(content: str, language: str) -> str:
    """Extract class and function signatures from source code using regex."""
    patterns = SIGNATURE_PATTERNS.get(language)
    if not patterns:
        return ""

    signatures: list[str] = []
    for line in content.splitlines():
        for pat in patterns:
            match = pat.match(line)
            if match:
                signatures.append(match.group(1).rstrip(" {:("))
                break

    return "\n".join(signatures)


LANG_EXT_MAP: dict[str, str] = {
    ".py": "Python",
    ".js": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".jsx": "JavaScript",
    ".go": "Go",
    ".java": "Java",
    ".kt": "Kotlin",
    ".rs": "Rust",
    ".rb": "Ruby",
    ".php": "PHP",
    ".swift": "Swift",
    ".dart": "Dart",
    ".c": "C",
    ".cpp": "C++",
    ".cs": "C#",
}


def _detect_language(file_path: Path) -> str:
    return LANG_EXT_MAP.get(file_path.suffix, "")


def _should_exclude(file_path: Path, root: Path, exclude: set[str]) -> bool:
    relative_parts = file_path.relative_to(root).parts
    for part in relative_parts:
        if part in exclude:
            return True
    return False


def _read_file_safe(file_path: Path, max_lines: int) -> str | None:
    try:
        text = file_path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None
    lines = text.splitlines()
    return "\n".join(lines[:max_lines])
