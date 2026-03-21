from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from neocortex.models import (
    ArchitectureSkill,
    DomainSkill,
    IntegrationSkill,
    LanguageSkill,
    ProjectInfo,
    SkillLevel,
    Skills,
)
from neocortex.scanner.analyzer import analyze_project, _parse_skills
from neocortex.scanner.extractors import (
    extract_key_files,
    extract_signatures,
)
from neocortex.scanner.profile import merge_profiles
from neocortex.scanner.project import ProjectScanner


# ---------------------------------------------------------------------------
# 1. ProjectScanner
# ---------------------------------------------------------------------------


class TestProjectScanner:
    def test_scan_python_project(self, tmp_path: Path):
        (tmp_path / "requirements.txt").write_text("flask\n")
        (tmp_path / "app.py").write_text("print('hello')\nprint('world')\n")
        (tmp_path / "utils.py").write_text("x = 1\n")

        scanner = ProjectScanner(exclude_patterns=["node_modules", "__pycache__"])
        info = scanner.scan(str(tmp_path))

        assert info.name == tmp_path.name
        assert "requirements.txt" in info.config_files
        assert "Python" in info.languages
        assert info.languages["Python"] == 3

    def test_scan_js_project(self, tmp_path: Path):
        pkg = {"name": "demo", "dependencies": {"express": "^4.0.0"}}
        (tmp_path / "package.json").write_text(json.dumps(pkg))
        (tmp_path / "index.js").write_text("const a = 1;\nconst b = 2;\n")

        scanner = ProjectScanner(exclude_patterns=[])
        info = scanner.scan(str(tmp_path))

        assert "package.json" in info.config_files
        assert "JavaScript" in info.languages
        assert info.languages["JavaScript"] == 2

    def test_line_count_accuracy(self, tmp_path: Path):
        lines = ["line"] * 50
        (tmp_path / "big.py").write_text("\n".join(lines))

        scanner = ProjectScanner(exclude_patterns=[])
        info = scanner.scan(str(tmp_path))

        assert info.languages["Python"] == 50

    def test_exclude_directories(self, tmp_path: Path):
        nm = tmp_path / "node_modules" / "pkg"
        nm.mkdir(parents=True)
        (nm / "index.js").write_text("module.exports = {}\n")

        (tmp_path / "app.js").write_text("const x = 1;\n")

        scanner = ProjectScanner(exclude_patterns=["node_modules"])
        info = scanner.scan(str(tmp_path))

        assert info.languages.get("JavaScript", 0) == 1

    def test_empty_directory(self, tmp_path: Path):
        scanner = ProjectScanner(exclude_patterns=[])
        info = scanner.scan(str(tmp_path))

        assert info.languages == {}
        assert info.config_files == []
        assert info.frameworks == []

    def test_binary_file_skipped(self, tmp_path: Path):
        (tmp_path / "image.py").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        (tmp_path / "app.py").write_text("x = 1\n")

        scanner = ProjectScanner(exclude_patterns=[])
        info = scanner.scan(str(tmp_path))

        assert info.languages["Python"] == 1

    def test_not_a_directory_raises(self, tmp_path: Path):
        f = tmp_path / "file.txt"
        f.write_text("hi")
        scanner = ProjectScanner(exclude_patterns=[])
        with pytest.raises(ValueError, match="Not a directory"):
            scanner.scan(str(f))


# ---------------------------------------------------------------------------
# 2. extractors
# ---------------------------------------------------------------------------


class TestExtractSignatures:
    def test_python_signatures(self):
        code = (
            "class MyModel:\n"
            "    pass\n"
            "\n"
            "def helper(x):\n"
            "    return x\n"
            "\n"
            "async def fetch_data(url):\n"
            "    pass\n"
        )
        result = extract_signatures(code, "Python")
        assert "class MyModel" in result
        assert "def helper" in result
        assert "async def fetch_data" in result

    def test_javascript_signatures(self):
        code = (
            "class App {\n"
            "  constructor() {}\n"
            "}\n"
            "\n"
            "function handleClick(e) {\n"
            "  return e;\n"
            "}\n"
            "\n"
            "export default App;\n"
            "const PI = 3.14;\n"
        )
        result = extract_signatures(code, "JavaScript")
        assert "class App" in result
        assert "function handleClick" in result
        assert "export default App" in result
        assert "const PI" in result

    def test_go_signatures(self):
        code = (
            "func main() {\n"
            "    fmt.Println(\"hello\")\n"
            "}\n"
            "\n"
            "type User struct {\n"
            "    Name string\n"
            "}\n"
        )
        result = extract_signatures(code, "Go")
        assert "func main" in result
        assert "type User struct" in result

    def test_unknown_language_returns_empty(self):
        result = extract_signatures("some code", "Brainfuck")
        assert result == ""


class TestExtractKeyFiles:
    def test_finds_models_py(self, tmp_path: Path):
        models = tmp_path / "app" / "models.py"
        models.parent.mkdir(parents=True)
        models.write_text("class User:\n    pass\n")

        results = extract_key_files(str(tmp_path))
        paths = [r["path"] for r in results]
        assert any("models.py" in p for p in paths)

    def test_finds_routes_file(self, tmp_path: Path):
        routes = tmp_path / "server" / "routes.py"
        routes.parent.mkdir(parents=True)
        routes.write_text("def index():\n    pass\n")

        results = extract_key_files(str(tmp_path))
        paths = [r["path"] for r in results]
        assert any("routes.py" in p for p in paths)

    def test_file_truncation(self, tmp_path: Path):
        long_content = "\n".join(f"line_{i} = {i}" for i in range(200))
        models = tmp_path / "models.py"
        models.write_text(long_content)

        results = extract_key_files(str(tmp_path), max_lines=10)
        for r in results:
            if "models.py" in r["path"]:
                content_lines = r["content"].split("\n# --- Signatures ---\n")[0]
                assert content_lines.count("\n") < 200
                break
        else:
            pytest.fail("models.py not found in results")

    def test_exclude_patterns(self, tmp_path: Path):
        excluded = tmp_path / "node_modules" / "pkg" / "models.py"
        excluded.parent.mkdir(parents=True)
        excluded.write_text("class Foo:\n    pass\n")

        results = extract_key_files(str(tmp_path), exclude_patterns=["node_modules"])
        paths = [r["path"] for r in results]
        assert not any("node_modules" in p for p in paths)


# ---------------------------------------------------------------------------
# 3. profile (merge_profiles)
# ---------------------------------------------------------------------------


class TestMergeProfiles:
    def test_higher_level_wins(self):
        existing = Skills(
            languages={
                "Python": LanguageSkill(level=SkillLevel.BEGINNER, lines=100),
            }
        )
        new = Skills(
            languages={
                "Python": LanguageSkill(level=SkillLevel.ADVANCED, lines=200),
            }
        )
        merged = merge_profiles(existing, new)
        assert merged.languages["Python"].level == SkillLevel.ADVANCED

    def test_higher_level_wins_reverse(self):
        existing = Skills(
            languages={
                "Python": LanguageSkill(level=SkillLevel.EXPERT, lines=500),
            }
        )
        new = Skills(
            languages={
                "Python": LanguageSkill(level=SkillLevel.BEGINNER, lines=10),
            }
        )
        merged = merge_profiles(existing, new)
        assert merged.languages["Python"].level == SkillLevel.EXPERT

    def test_lines_accumulate(self):
        existing = Skills(
            languages={
                "Python": LanguageSkill(lines=100),
            }
        )
        new = Skills(
            languages={
                "Python": LanguageSkill(lines=200),
            }
        )
        merged = merge_profiles(existing, new)
        assert merged.languages["Python"].lines == 300

    def test_evidence_merge_dedup(self):
        existing = Skills(
            domains={
                "web": DomainSkill(
                    level=SkillLevel.PROFICIENT,
                    evidence=["uses Flask", "REST API"],
                ),
            }
        )
        new = Skills(
            domains={
                "web": DomainSkill(
                    level=SkillLevel.ADVANCED,
                    evidence=["REST API", "uses Django"],
                ),
            }
        )
        merged = merge_profiles(existing, new)
        ev = merged.domains["web"].evidence
        assert ev == ["uses Flask", "REST API", "uses Django"]

    def test_gaps_union(self):
        existing = Skills(
            domains={
                "web": DomainSkill(
                    level=SkillLevel.PROFICIENT,
                    gaps=["no caching"],
                ),
            }
        )
        new = Skills(
            domains={
                "web": DomainSkill(
                    level=SkillLevel.PROFICIENT,
                    gaps=["no rate limiting", "no caching"],
                ),
            }
        )
        merged = merge_profiles(existing, new)
        gaps = merged.domains["web"].gaps
        assert "no_caching" in gaps
        assert "no_rate_limiting" in gaps
        assert len(gaps) == 2

    def test_merge_empty_skills(self):
        existing = Skills()
        new = Skills()
        merged = merge_profiles(existing, new)
        assert merged.languages == {}
        assert merged.domains == {}
        assert merged.integrations == {}
        assert merged.architecture == {}

    def test_merge_one_empty(self):
        existing = Skills(
            languages={
                "Go": LanguageSkill(level=SkillLevel.PROFICIENT, lines=500),
            }
        )
        new = Skills()
        merged = merge_profiles(existing, new)
        assert "Go" in merged.languages
        assert merged.languages["Go"].level == SkillLevel.PROFICIENT

    def test_merge_new_skill_appears(self):
        existing = Skills(
            languages={
                "Python": LanguageSkill(level=SkillLevel.ADVANCED, lines=1000),
            }
        )
        new = Skills(
            languages={
                "Rust": LanguageSkill(level=SkillLevel.BEGINNER, lines=50),
            }
        )
        merged = merge_profiles(existing, new)
        assert "Python" in merged.languages
        assert "Rust" in merged.languages

    def test_merge_integrations(self):
        existing = Skills(
            integrations={
                "stripe": IntegrationSkill(
                    level=SkillLevel.PROFICIENT,
                    providers=["stripe"],
                    gaps=["no webhooks"],
                ),
            }
        )
        new = Skills(
            integrations={
                "stripe": IntegrationSkill(
                    level=SkillLevel.ADVANCED,
                    providers=["stripe"],
                    gaps=["no 3D secure"],
                ),
            }
        )
        merged = merge_profiles(existing, new)
        stripe = merged.integrations["stripe"]
        assert stripe.level == SkillLevel.ADVANCED
        assert stripe.providers == ["stripe"]
        assert "no_webhooks" in stripe.gaps
        assert "no_3d_secure" in stripe.gaps

    def test_merge_architecture(self):
        existing = Skills(
            architecture={
                "microservices": ArchitectureSkill(
                    level=SkillLevel.BEGINNER,
                    patterns=["docker-compose"],
                    evidence=["2 services"],
                ),
            }
        )
        new = Skills(
            architecture={
                "microservices": ArchitectureSkill(
                    level=SkillLevel.PROFICIENT,
                    patterns=["kubernetes"],
                    evidence=["5 services"],
                ),
            }
        )
        merged = merge_profiles(existing, new)
        arch = merged.architecture["microservices"]
        assert arch.level == SkillLevel.PROFICIENT
        assert "docker-compose" in arch.patterns
        assert "kubernetes" in arch.patterns
        assert "2 services" in arch.evidence
        assert "5 services" in arch.evidence


# ---------------------------------------------------------------------------
# 4. analyzer (mock LLM)
# ---------------------------------------------------------------------------


def _make_mock_provider(response: str) -> MagicMock:
    provider = MagicMock()
    provider.chat = AsyncMock(return_value=response)
    return provider


def _make_project_info() -> ProjectInfo:
    return ProjectInfo(
        path="/tmp/demo",
        name="demo",
        languages={"Python": 500},
        config_files=["requirements.txt"],
        frameworks=["Flask"],
        architecture_signals=[],
    )


class TestAnalyzer:
    @pytest.mark.asyncio
    async def test_analyze_project_parses_response(self):
        llm_response = json.dumps({
            "languages": {
                "Python": {
                    "level": "advanced",
                    "lines": 0,
                    "frameworks": ["Flask"],
                    "patterns": ["MVC"],
                    "projects": ["demo"],
                }
            },
            "domains": {
                "web_backend": {
                    "level": "proficient",
                    "evidence": ["REST API"],
                    "gaps": ["no caching"],
                }
            },
            "integrations": {},
            "architecture": {},
        })
        provider = _make_mock_provider(llm_response)
        info = _make_project_info()

        skills = await analyze_project(info, [], provider)

        assert "Python" in skills.languages
        assert skills.languages["Python"].level == SkillLevel.ADVANCED
        assert skills.languages["Python"].lines == 500
        assert "Flask" in skills.languages["Python"].frameworks
        assert "web_backend" in skills.domains
        assert skills.domains["web_backend"].level == SkillLevel.PROFICIENT

    @pytest.mark.asyncio
    async def test_analyze_project_invalid_json_returns_empty(self):
        provider = _make_mock_provider("this is not json at all {{{")
        info = _make_project_info()

        skills = await analyze_project(info, [], provider)

        assert skills.languages == {}
        assert skills.domains == {}

    @pytest.mark.asyncio
    async def test_analyze_project_markdown_wrapped_json(self):
        raw = json.dumps({
            "languages": {
                "Python": {
                    "level": "expert",
                    "lines": 0,
                    "frameworks": ["Django"],
                    "patterns": [],
                    "projects": ["demo"],
                }
            },
            "domains": {},
            "integrations": {},
            "architecture": {},
        })
        wrapped = f"```json\n{raw}\n```"
        provider = _make_mock_provider(wrapped)
        info = _make_project_info()

        skills = await analyze_project(info, [], provider)

        assert "Python" in skills.languages
        assert skills.languages["Python"].level == SkillLevel.EXPERT
        assert skills.languages["Python"].lines == 500

    def test_parse_skills_direct(self):
        raw = json.dumps({
            "languages": {
                "Go": {
                    "level": "proficient",
                    "lines": 1000,
                    "frameworks": [],
                    "patterns": ["concurrency"],
                    "projects": ["svc"],
                }
            },
            "domains": {},
            "integrations": {
                "redis": {
                    "level": "advanced",
                    "providers": ["redis"],
                    "gaps": [],
                }
            },
            "architecture": {
                "microservices": {
                    "level": "proficient",
                    "patterns": ["k8s"],
                    "evidence": ["3 services"],
                }
            },
        })
        skills = _parse_skills(raw)

        assert skills.languages["Go"].level == SkillLevel.PROFICIENT
        assert skills.languages["Go"].lines == 1000
        assert skills.integrations["redis"].level == SkillLevel.ADVANCED
        assert skills.architecture["microservices"].patterns == ["k8s"]

    def test_parse_skills_markdown_fences(self):
        raw = json.dumps({
            "languages": {},
            "domains": {"web": {"level": "beginner", "evidence": [], "gaps": []}},
            "integrations": {},
            "architecture": {},
        })
        wrapped = f"```json\n{raw}\n```"
        skills = _parse_skills(wrapped)
        assert "web" in skills.domains
        assert skills.domains["web"].level == SkillLevel.BEGINNER
