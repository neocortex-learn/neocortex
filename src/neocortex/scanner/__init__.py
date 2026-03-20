"""Scanner module — scan local projects to build skill profiles."""

from neocortex.scanner.analyzer import analyze_project
from neocortex.scanner.profile import merge_profiles
from neocortex.scanner.project import ProjectScanner

__all__ = ["ProjectScanner", "analyze_project", "merge_profiles"]
