"""Static codebase analysis for project discovery.

Analyzes project structure, detects languages/frameworks, and counts lines of code.
"""

import re
from pathlib import Path
from typing import Optional

from ..models import ProjectSummary


# Language detection patterns (file extensions and marker files)
LANGUAGE_PATTERNS: dict[str, list[str]] = {
    "python": ["*.py", "pyproject.toml", "requirements.txt", "setup.py", "Pipfile"],
    "javascript": ["*.js", "*.mjs", "*.cjs", "package.json"],
    "typescript": ["*.ts", "*.tsx", "tsconfig.json"],
    "rust": ["*.rs", "Cargo.toml"],
    "go": ["*.go", "go.mod", "go.sum"],
    "java": ["*.java", "pom.xml", "build.gradle"],
    "csharp": ["*.cs", "*.csproj", "*.sln"],
    "cpp": ["*.cpp", "*.cc", "*.cxx", "*.hpp", "*.h", "CMakeLists.txt"],
    "ruby": ["*.rb", "Gemfile", "Rakefile"],
    "php": ["*.php", "composer.json"],
    "swift": ["*.swift", "Package.swift"],
    "kotlin": ["*.kt", "*.kts", "build.gradle.kts"],
}

# Framework detection patterns (search in file content)
FRAMEWORK_PATTERNS: dict[str, list[str]] = {
    # Python frameworks
    "fastapi": ["from fastapi", "import fastapi", "FastAPI("],
    "django": ["from django", "import django", "DJANGO_SETTINGS"],
    "flask": ["from flask", "import flask", "Flask("],
    "pytest": ["import pytest", "from pytest"],
    "pydantic": ["from pydantic", "import pydantic", "BaseModel"],
    "click": ["import click", "from click", "@click."],
    "rich": ["from rich", "import rich"],
    # JavaScript/TypeScript frameworks
    "react": ["from 'react'", 'from "react"', "import React"],
    "next": ["next.config", "from 'next", 'from "next'],
    "vue": ["from 'vue'", 'from "vue"', "createApp("],
    "angular": ["@angular/core", "NgModule"],
    "express": ["from 'express'", 'from "express"', "require('express')"],
    "nest": ["@nestjs/", "NestFactory"],
    # Other frameworks
    "spring": ["org.springframework", "@SpringBootApplication"],
    "rails": ["Rails.application", "ActionController"],
    "dotnet": ["Microsoft.AspNetCore", "IHostBuilder"],
}

# Directories to exclude from analysis
EXCLUDED_DIRS: set[str] = {
    "node_modules",
    "__pycache__",
    ".git",
    ".svn",
    ".hg",
    "venv",
    ".venv",
    "env",
    ".env",
    "dist",
    "build",
    "target",
    ".tox",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "coverage",
    ".coverage",
    "htmlcov",
    ".eggs",
    "*.egg-info",
}

# Common entry point patterns
ENTRY_POINT_PATTERNS: list[str] = [
    "main.py",
    "app.py",
    "cli.py",
    "__main__.py",
    "index.js",
    "index.ts",
    "main.js",
    "main.ts",
    "server.js",
    "server.ts",
    "app.js",
    "app.ts",
    "main.go",
    "main.rs",
    "Program.cs",
    "Main.java",
]

# Directory purposes (common directory names and their likely purpose)
DIRECTORY_PURPOSES: dict[str, str] = {
    "src": "Source code",
    "lib": "Library code",
    "app": "Application code",
    "tests": "Test files",
    "test": "Test files",
    "spec": "Test specifications",
    "docs": "Documentation",
    "doc": "Documentation",
    "examples": "Example code",
    "scripts": "Utility scripts",
    "bin": "Binary/executable scripts",
    "config": "Configuration files",
    "assets": "Static assets",
    "public": "Public assets",
    "static": "Static files",
    "templates": "Template files",
    "views": "View templates",
    "models": "Data models",
    "controllers": "Controller logic",
    "services": "Service layer",
    "utils": "Utility functions",
    "helpers": "Helper functions",
    "middleware": "Middleware",
    "api": "API endpoints",
    "routes": "Route definitions",
    "components": "UI components",
    "pages": "Page components",
    "hooks": "Custom hooks",
    "store": "State management",
    "types": "Type definitions",
    "interfaces": "Interface definitions",
}


class CodebaseAnalyzer:
    """Analyzes a codebase to extract structure and metadata."""

    def __init__(self, project_path: Path | str):
        """Initialize the analyzer.

        Args:
            project_path: Path to the project root directory.
        """
        self.project_path = Path(project_path).resolve()
        self._file_cache: dict[str, list[Path]] = {}

    def analyze(self) -> ProjectSummary:
        """Perform full codebase analysis.

        Returns:
            ProjectSummary with detected languages, frameworks, structure, etc.
        """
        return ProjectSummary(
            languages=self.detect_languages(),
            frameworks=self.detect_frameworks(),
            structure=self.map_structure(),
            entry_points=self.find_entry_points(),
            dependencies=self.parse_dependencies(),
            line_counts=self.count_lines(),
        )

    def detect_languages(self) -> list[str]:
        """Detect programming languages used in the project.

        Returns:
            List of detected language names.
        """
        languages = []

        for language, patterns in LANGUAGE_PATTERNS.items():
            for pattern in patterns:
                if self._has_files(pattern):
                    languages.append(language)
                    break

        return sorted(set(languages))

    def detect_frameworks(self) -> list[str]:
        """Detect frameworks used in the project.

        Returns:
            List of detected framework names.
        """
        frameworks = []
        languages = self.detect_languages()

        # Only check relevant files based on detected languages
        extensions_to_check = []
        if "python" in languages:
            extensions_to_check.extend(["*.py"])
        if "javascript" in languages or "typescript" in languages:
            extensions_to_check.extend(["*.js", "*.ts", "*.tsx", "*.jsx"])
        if "java" in languages:
            extensions_to_check.extend(["*.java"])
        if "ruby" in languages:
            extensions_to_check.extend(["*.rb"])
        if "csharp" in languages:
            extensions_to_check.extend(["*.cs"])

        # Sample files to check (limit for performance)
        files_to_check: list[Path] = []
        for ext in extensions_to_check:
            files_to_check.extend(self._get_files(ext)[:50])

        # Read content and check for framework patterns
        for file_path in files_to_check:
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                for framework, patterns in FRAMEWORK_PATTERNS.items():
                    if framework not in frameworks:
                        for pattern in patterns:
                            if pattern in content:
                                frameworks.append(framework)
                                break
            except (OSError, IOError):
                continue

        return sorted(set(frameworks))

    def map_structure(self) -> dict[str, str]:
        """Map the project's directory structure.

        Returns:
            Dictionary mapping directory paths to their purpose.
        """
        structure = {}

        # Get immediate subdirectories
        try:
            for item in self.project_path.iterdir():
                if item.is_dir() and item.name not in EXCLUDED_DIRS and not item.name.startswith("."):
                    purpose = DIRECTORY_PURPOSES.get(item.name.lower(), "")
                    if purpose:
                        structure[item.name] = purpose
                    else:
                        # Try to infer purpose from contents
                        structure[item.name] = self._infer_directory_purpose(item)
        except (OSError, IOError):
            pass

        return structure

    def find_entry_points(self) -> list[str]:
        """Find likely entry points of the application.

        Returns:
            List of entry point file paths (relative to project root).
        """
        entry_points = []

        for pattern in ENTRY_POINT_PATTERNS:
            for file_path in self._get_files(pattern):
                relative_path = file_path.relative_to(self.project_path)
                entry_points.append(str(relative_path))

        # Also check pyproject.toml for Python entry points
        pyproject = self.project_path / "pyproject.toml"
        if pyproject.exists():
            try:
                content = pyproject.read_text(encoding="utf-8")
                # Simple pattern match for [project.scripts]
                if "[project.scripts]" in content:
                    match = re.search(r'\[project\.scripts\]([^\[]+)', content)
                    if match:
                        scripts_section = match.group(1)
                        for line in scripts_section.strip().split("\n"):
                            if "=" in line:
                                # Extract the module path
                                _, value = line.split("=", 1)
                                module_path = value.strip().strip('"').strip("'")
                                if ":" in module_path:
                                    module_path = module_path.split(":")[0]
                                module_path = module_path.replace(".", "/") + ".py"
                                if module_path not in entry_points:
                                    entry_points.append(module_path)
            except (OSError, IOError):
                pass

        # Check package.json for Node entry points
        package_json = self.project_path / "package.json"
        if package_json.exists():
            try:
                import json
                content = json.loads(package_json.read_text(encoding="utf-8"))
                if "main" in content:
                    main = content["main"]
                    if main not in entry_points:
                        entry_points.append(main)
                if "bin" in content:
                    bins = content["bin"]
                    if isinstance(bins, str):
                        if bins not in entry_points:
                            entry_points.append(bins)
                    elif isinstance(bins, dict):
                        for bin_path in bins.values():
                            if bin_path not in entry_points:
                                entry_points.append(bin_path)
            except (OSError, IOError, json.JSONDecodeError):
                pass

        return sorted(set(entry_points))

    def parse_dependencies(self) -> dict[str, str]:
        """Parse project dependencies from lockfiles.

        Returns:
            Dictionary mapping dependency names to versions.
        """
        dependencies: dict[str, str] = {}

        # Python: pyproject.toml
        pyproject = self.project_path / "pyproject.toml"
        if pyproject.exists():
            dependencies.update(self._parse_pyproject_deps(pyproject))

        # Python: requirements.txt
        requirements = self.project_path / "requirements.txt"
        if requirements.exists():
            dependencies.update(self._parse_requirements_txt(requirements))

        # Node: package.json
        package_json = self.project_path / "package.json"
        if package_json.exists():
            dependencies.update(self._parse_package_json(package_json))

        # Rust: Cargo.toml
        cargo = self.project_path / "Cargo.toml"
        if cargo.exists():
            dependencies.update(self._parse_cargo_toml(cargo))

        # Go: go.mod
        go_mod = self.project_path / "go.mod"
        if go_mod.exists():
            dependencies.update(self._parse_go_mod(go_mod))

        return dependencies

    def count_lines(self) -> dict[str, int]:
        """Count lines of code by category.

        Returns:
            Dictionary with keys 'code', 'tests', 'docs' and their line counts.
        """
        counts = {"code": 0, "tests": 0, "docs": 0}

        # Code file extensions
        code_extensions = [
            "*.py", "*.js", "*.ts", "*.tsx", "*.jsx", "*.rs", "*.go",
            "*.java", "*.cs", "*.cpp", "*.c", "*.h", "*.hpp",
            "*.rb", "*.php", "*.swift", "*.kt",
        ]

        # Count code lines (excluding tests)
        for ext in code_extensions:
            for file_path in self._get_files(ext):
                relative_path = str(file_path.relative_to(self.project_path))

                # Check if it's a test file
                is_test = (
                    "test" in relative_path.lower() or
                    "spec" in relative_path.lower() or
                    relative_path.startswith("tests/") or
                    relative_path.startswith("test/")
                )

                try:
                    line_count = len(file_path.read_text(encoding="utf-8", errors="ignore").splitlines())
                    if is_test:
                        counts["tests"] += line_count
                    else:
                        counts["code"] += line_count
                except (OSError, IOError):
                    continue

        # Count documentation lines
        doc_extensions = ["*.md", "*.rst", "*.txt"]
        for ext in doc_extensions:
            for file_path in self._get_files(ext):
                try:
                    line_count = len(file_path.read_text(encoding="utf-8", errors="ignore").splitlines())
                    counts["docs"] += line_count
                except (OSError, IOError):
                    continue

        return counts

    def _has_files(self, pattern: str) -> bool:
        """Check if any files match the given pattern.

        Args:
            pattern: Glob pattern to match.

        Returns:
            True if any files match.
        """
        return len(self._get_files(pattern)) > 0

    def _get_files(self, pattern: str) -> list[Path]:
        """Get all files matching a pattern.

        Args:
            pattern: Glob pattern to match.

        Returns:
            List of matching file paths.
        """
        if pattern in self._file_cache:
            return self._file_cache[pattern]

        files = []
        try:
            for file_path in self.project_path.rglob(pattern):
                # Skip excluded directories
                skip = False
                for part in file_path.parts:
                    if part in EXCLUDED_DIRS:
                        skip = True
                        break
                if not skip and file_path.is_file():
                    files.append(file_path)
        except (OSError, IOError):
            pass

        self._file_cache[pattern] = files
        return files

    def _infer_directory_purpose(self, dir_path: Path) -> str:
        """Infer the purpose of a directory from its contents.

        Args:
            dir_path: Path to the directory.

        Returns:
            Inferred purpose string.
        """
        try:
            files = list(dir_path.iterdir())[:20]  # Sample first 20 items

            # Check for test files
            test_indicators = sum(1 for f in files if "test" in f.name.lower())
            if test_indicators > len(files) / 2:
                return "Test files"

            # Check for documentation
            doc_indicators = sum(1 for f in files if f.suffix in {".md", ".rst", ".txt"})
            if doc_indicators > len(files) / 2:
                return "Documentation"

            # Check for source code
            code_indicators = sum(1 for f in files if f.suffix in {".py", ".js", ".ts", ".rs", ".go", ".java"})
            if code_indicators > len(files) / 2:
                return "Source code"

        except (OSError, IOError):
            pass

        return ""

    def _parse_pyproject_deps(self, path: Path) -> dict[str, str]:
        """Parse dependencies from pyproject.toml."""
        deps = {}
        try:
            content = path.read_text(encoding="utf-8")

            # Simple regex pattern for dependencies
            # Handles formats like: "package>=1.0.0", "package"
            dep_section = re.search(r'dependencies\s*=\s*\[(.*?)\]', content, re.DOTALL)
            if dep_section:
                dep_text = dep_section.group(1)
                for match in re.finditer(r'"([^"]+)"', dep_text):
                    dep = match.group(1)
                    # Parse version spec
                    for sep in [">=", "<=", "==", "~=", ">", "<", "!="]:
                        if sep in dep:
                            name, version = dep.split(sep, 1)
                            deps[name.strip()] = sep + version.strip()
                            break
                    else:
                        deps[dep.strip()] = "*"
        except (OSError, IOError):
            pass
        return deps

    def _parse_requirements_txt(self, path: Path) -> dict[str, str]:
        """Parse dependencies from requirements.txt."""
        deps = {}
        try:
            content = path.read_text(encoding="utf-8")
            for line in content.splitlines():
                line = line.strip()
                if line and not line.startswith("#") and not line.startswith("-"):
                    # Parse version spec
                    for sep in [">=", "<=", "==", "~=", ">", "<", "!="]:
                        if sep in line:
                            name, version = line.split(sep, 1)
                            deps[name.strip()] = sep + version.strip().split()[0]
                            break
                    else:
                        deps[line.split()[0]] = "*"
        except (OSError, IOError):
            pass
        return deps

    def _parse_package_json(self, path: Path) -> dict[str, str]:
        """Parse dependencies from package.json."""
        deps = {}
        try:
            import json
            content = json.loads(path.read_text(encoding="utf-8"))
            for section in ["dependencies", "devDependencies"]:
                if section in content:
                    for name, version in content[section].items():
                        deps[name] = version
        except (OSError, IOError, json.JSONDecodeError):
            pass
        return deps

    def _parse_cargo_toml(self, path: Path) -> dict[str, str]:
        """Parse dependencies from Cargo.toml."""
        deps = {}
        try:
            content = path.read_text(encoding="utf-8")
            in_deps = False
            for line in content.splitlines():
                line = line.strip()
                if line == "[dependencies]":
                    in_deps = True
                    continue
                elif line.startswith("[") and in_deps:
                    in_deps = False
                    continue
                if in_deps and "=" in line:
                    name, value = line.split("=", 1)
                    name = name.strip()
                    value = value.strip().strip('"').strip("'")
                    deps[name] = value
        except (OSError, IOError):
            pass
        return deps

    def _parse_go_mod(self, path: Path) -> dict[str, str]:
        """Parse dependencies from go.mod."""
        deps = {}
        try:
            content = path.read_text(encoding="utf-8")
            in_require = False
            for line in content.splitlines():
                line = line.strip()
                if line == "require (":
                    in_require = True
                    continue
                elif line == ")" and in_require:
                    in_require = False
                    continue
                if in_require and line:
                    parts = line.split()
                    if len(parts) >= 2:
                        deps[parts[0]] = parts[1]
                elif line.startswith("require "):
                    parts = line[8:].split()
                    if len(parts) >= 2:
                        deps[parts[0]] = parts[1]
        except (OSError, IOError):
            pass
        return deps
