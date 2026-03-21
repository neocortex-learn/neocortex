"""Project scanner — scan a project directory and extract structured info."""

from __future__ import annotations

from pathlib import Path

from neocortex.models import ProjectInfo

LANG_EXTENSIONS: dict[str, str] = {
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

CONFIG_FILES: dict[str, list[str]] = {
    "package.json": ["Node.js"],
    "requirements.txt": ["Python"],
    "pyproject.toml": ["Python"],
    "setup.py": ["Python"],
    "go.mod": ["Go"],
    "build.gradle": ["Java/Kotlin (Gradle)"],
    "build.gradle.kts": ["Kotlin (Gradle)"],
    "Cargo.toml": ["Rust"],
    "pom.xml": ["Java (Maven)"],
    "Gemfile": ["Ruby"],
    "composer.json": ["PHP (Composer)"],
    "pubspec.yaml": ["Dart/Flutter"],
    "Package.swift": ["Swift"],
    "CMakeLists.txt": ["C/C++ (CMake)"],
    "Makefile": ["Make"],
}

FRAMEWORK_INDICATORS: dict[str, str] = {
    "next.config": "Next.js",
    "nuxt.config": "Nuxt.js",
    "angular.json": "Angular",
    "vue.config": "Vue CLI",
    "vite.config": "Vite",
    "tailwind.config": "Tailwind CSS",
    "tsconfig.json": "TypeScript",
    "webpack.config": "Webpack",
    "babel.config": "Babel",
    ".eslintrc": "ESLint",
    "jest.config": "Jest",
    "pytest.ini": "pytest",
    "setup.cfg": "setuptools",
    "tox.ini": "tox",
    "manage.py": "Django",
    "alembic.ini": "SQLAlchemy/Alembic",
    "prisma": "Prisma",
    "schema.prisma": "Prisma",
}

ARCHITECTURE_SIGNALS: list[tuple[str, list[str]]] = [
    ("microservices", ["docker-compose.yml", "docker-compose.yaml", "kubernetes", "k8s"]),
    ("database:postgresql", ["psycopg", "postgres", "postgresql"]),
    ("database:mysql", ["mysql", "pymysql", "mysqlclient"]),
    ("database:mongodb", ["mongo", "pymongo", "mongoose"]),
    ("database:redis", ["redis", "ioredis", "aioredis"]),
    ("message_queue:rabbitmq", ["rabbitmq", "amqp", "pika"]),
    ("message_queue:kafka", ["kafka", "confluent-kafka"]),
    ("cache:redis", ["redis"]),
    ("payment:stripe", ["stripe"]),
    ("payment:paypal", ["paypal"]),
    ("cloud:aws", ["boto3", "aws-sdk", "@aws-sdk"]),
    ("cloud:gcp", ["google-cloud", "@google-cloud"]),
    ("cloud:azure", ["azure", "@azure"]),
    ("realtime:websocket", ["websocket", "socket.io", "ws"]),
    ("realtime:socketio", ["socket.io", "python-socketio"]),
    ("ci:github_actions", [".github/workflows"]),
    ("ci:gitlab_ci", [".gitlab-ci.yml"]),
    ("ci:jenkins", ["Jenkinsfile"]),
    ("container:docker", ["Dockerfile"]),
    ("orm:sqlalchemy", ["sqlalchemy"]),
    ("orm:django_orm", ["django.db"]),
    ("orm:prisma", ["prisma"]),
    ("orm:typeorm", ["typeorm"]),
    ("orm:sequelize", ["sequelize"]),
    ("orm:gorm", ["gorm"]),
]


class ProjectScanner:
    def __init__(self, exclude_patterns: list[str]) -> None:
        self._exclude = set(exclude_patterns)

    def scan(self, path: str) -> ProjectInfo:
        root = Path(path).resolve()
        if not root.is_dir():
            raise ValueError(f"Not a directory: {root}")

        name = root.name
        config_files = self._detect_config_files(root)
        frameworks = self._detect_frameworks(root)
        languages = self._count_lines_by_language(root)
        signals = self._detect_architecture_signals(root, config_files)

        return ProjectInfo(
            path=str(root),
            name=name,
            languages=languages,
            config_files=config_files,
            frameworks=frameworks,
            architecture_signals=signals,
        )

    def _detect_config_files(self, root: Path) -> list[str]:
        found: list[str] = []
        for config_name in CONFIG_FILES:
            if (root / config_name).exists():
                found.append(config_name)
        return found

    def _detect_frameworks(self, root: Path) -> list[str]:
        frameworks: list[str] = []
        for indicator, framework in FRAMEWORK_INDICATORS.items():
            matches = list(root.glob(f"{indicator}*"))
            if matches:
                if framework not in frameworks:
                    frameworks.append(framework)
            if (root / indicator).is_dir():
                if framework not in frameworks:
                    frameworks.append(framework)
        return frameworks

    def _count_lines_by_language(self, root: Path) -> dict[str, int]:
        counts: dict[str, int] = {}
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if self._should_exclude(path, root):
                continue
            ext = path.suffix.lower()
            lang = LANG_EXTENSIONS.get(ext)
            if lang is None:
                continue
            try:
                lines = len(path.read_text(encoding="utf-8").splitlines())
            except (UnicodeDecodeError, OSError):
                continue
            counts[lang] = counts.get(lang, 0) + lines
        return counts

    def _detect_architecture_signals(
        self, root: Path, config_files: list[str]
    ) -> list[str]:
        signals: list[str] = []

        config_content = self._read_config_contents(root, config_files)

        dir_names = {p.name for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")}

        service_dirs = dir_names & {"services", "service", "server", "servers", "microservices"}
        if len(service_dirs) > 0:
            sub_services = []
            for sd in service_dirs:
                sd_path = root / sd
                sub_services.extend(
                    d.name for d in sd_path.iterdir() if d.is_dir() and not d.name.startswith(".")
                )
            if len(sub_services) >= 2:
                signals.append("microservices")

        for signal_name, keywords in ARCHITECTURE_SIGNALS:
            if signal_name == "microservices":
                continue
            for keyword in keywords:
                found = False
                if "/" in keyword or keyword.startswith("."):
                    kw_path = root / keyword
                    if kw_path.exists():
                        found = True
                    elif kw_path.parent.exists() and list(kw_path.parent.glob(kw_path.name)):
                        found = True
                elif keyword in config_content:
                    found = True
                if found:
                    if signal_name not in signals:
                        signals.append(signal_name)
                    break

        return signals

    def _read_config_contents(self, root: Path, config_files: list[str]) -> str:
        parts: list[str] = []
        for cf in config_files:
            cf_path = root / cf
            if cf_path.is_file():
                try:
                    parts.append(cf_path.read_text(encoding="utf-8"))
                except (UnicodeDecodeError, OSError):
                    continue

        lock_files = ["package-lock.json", "yarn.lock", "pnpm-lock.yaml", "Pipfile.lock"]
        for lf in lock_files:
            lf_path = root / lf
            if lf_path.is_file():
                try:
                    content = lf_path.read_text(encoding="utf-8")
                    parts.append(content[:5000])
                except (UnicodeDecodeError, OSError):
                    continue

        req_files = ["requirements.txt", "requirements.dev.txt", "requirements-dev.txt"]
        for rf in req_files:
            rf_path = root / rf
            if rf_path.is_file():
                try:
                    parts.append(rf_path.read_text(encoding="utf-8"))
                except (UnicodeDecodeError, OSError):
                    continue

        return "\n".join(parts).lower()

    def _should_exclude(self, file_path: Path, root: Path) -> bool:
        relative_parts = file_path.relative_to(root).parts
        for part in relative_parts:
            if part in self._exclude:
                return True
            if part.endswith(".egg-info"):
                return True
        return False

    def _count_lines(self, file_path: Path) -> int:
        try:
            text = file_path.read_text(encoding="utf-8")
            return len(text.splitlines())
        except (UnicodeDecodeError, OSError):
            return 0
