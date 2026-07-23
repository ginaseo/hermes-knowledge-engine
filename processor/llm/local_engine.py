"""Deterministic, zero-cost stand-in for the remote LLM — no network calls.

Approximates what summary/entity/keyword/related processors get from an LLM
using corpus-wide TF-IDF and dictionary matching against the vault's own
existing projects/people. Quality is lower than an LLM (no real semantic
understanding), but it costs nothing and never hallucinates outside the
grounded doc list. Enabled via HERMES_LOCAL_HEURISTIC=1 (see client.py).

Task type is detected from the fixed preamble text of each prompt template
in processor/prompts/ — the placeholder content changes, the template
wording around it doesn't.
"""

import json
import math
import re
from collections import Counter

from processor.paths import VAULT

_ENTITY_MARK = "Obsidian Knowledge Graph"
_KEYWORD_MARK = "중요 키워드만 추출"
_RELATED_MARK = "관련 문서를 추천"
# description_fill_prompt.txt also opens with "Obsidian Knowledge Graph" --
# must be checked before _ENTITY_MARK or every description-fill call gets
# misrouted to _entity() and handed back a list where a dict is expected.
_DESC_FILL_MARK = "related_entities는 문서에서 언급된"
_CONTENT_DELIM = "====================\n"
_DESC_FILL_HEADER_RE = re.compile(r'"(.+?)"\((.+?)\)\s*문서를 보강')
_DESC_FILL_EXISTING_RE = re.compile(r"\[기존 문서\]\n\n(.*?)\n\n\[새 자료\]", re.S)
_DESC_FILL_SOURCE_RE = re.compile(r"\[새 자료\]\n\n(.*)$", re.S)

_TOKEN_RE = re.compile(r"[가-힣]{2,}|[A-Za-z][A-Za-z0-9_.+-]{1,}|\d[\d,.]*%?")
_NUMERIC_RE = re.compile(r"[\d][\d,.]*\s*(?:%|원|조|억|만원|만|배|건|개|점|위|년|월|일)")

_STOPWORDS = {
    "그리고",
    "그래서",
    "하지만",
    "그러나",
    "이런",
    "저런",
    "합니다",
    "있습니다",
    "때문에",
    "이것",
    "저것",
    "우리",
    "제가",
    "저는",
    "그는",
    "위해",
    "대한",
    "그것",
    "이제",
    "지금",
    "먼저",
    "다시",
    "여기",
    "저기",
    "그냥",
    "정말",
    "있다",
    "없다",
    "한다",
    "된다",
    "것을",
    "것은",
    "것이",
    "수있는",
    "합니다만",
    # English function words -- corpus has many English-language conversations
    "the",
    "a",
    "an",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "to",
    "of",
    "and",
    "or",
    "but",
    "in",
    "on",
    "at",
    "for",
    "with",
    "this",
    "that",
    "these",
    "those",
    "it",
    "its",
    "as",
    "by",
    "from",
    "will",
    "would",
    "can",
    "could",
    "should",
    "shall",
    "may",
    "might",
    "not",
    "no",
    "do",
    "does",
    "did",
    "done",
    "have",
    "has",
    "had",
    "you",
    "your",
    "yours",
    "we",
    "our",
    "ours",
    "they",
    "their",
    "them",
    "he",
    "she",
    "his",
    "her",
    "if",
    "then",
    "than",
    "so",
    "such",
    "also",
    "there",
    "here",
    "what",
    "which",
    "who",
    "whom",
    "when",
    "where",
    "why",
    "how",
    "i.e.",
    "e.g.",
    "into",
    "about",
    "up",
    "out",
    "just",
    "only",
    "some",
    "any",
    "all",
    "each",
    "other",
    "more",
    "most",
}

# Korean verb/particle endings -- a naive [가-힣]{2,} token match often grabs
# a sentence-final fragment (e.g. "하지 마세요" -> "마세요") that isn't a real
# noun/concept. Reject candidates ending in these before treating as a Concept.
_KO_VERB_ENDINGS = (
    "습니다",
    "입니다",
    "합니다",
    "합니다만",
    "해요",
    "이에요",
    "예요",
    "세요",
    "네요",
    "군요",
    "잖아요",
    "거든요",
    "니다",
    "죠",
    "구요",
    "은데요",
    "는데요",
)

_TECH_TERMS = [
    "Python",
    "Docker",
    "Kubernetes",
    "AWS",
    "EC2",
    "Slack",
    "Claude",
    "ChatGPT",
    "OpenAI",
    "DeepSeek",
    "React",
    "JavaScript",
    "TypeScript",
    "Node.js",
    "FastAPI",
    "PostgreSQL",
    "MySQL",
    "Redis",
    "Git",
    "GitHub",
    "Jenkins",
    "CI/CD",
    "Nginx",
    "Linux",
    "Ubuntu",
    "MCP",
    "LLM",
    "API",
    "JSON",
    "HTTP",
    "REST",
    "GraphQL",
    "Figma",
    "Notion",
    "Obsidian",
    "Syncthing",
    "Terraform",
    "Ollama",
    "Gemini",
    "Groq",
    "Qdrant",
    "Java",
    "Spring",
    "Kafka",
    "MSA",
    "SQL",
    "HTML",
    "CSS",
    "Vue",
    "Next.js",
]


class LocalHeuristicEngine:

    def __init__(self):
        self._corpus_df: Counter | None = None
        self._corpus_size = 0
        self._doc_texts: dict[str, str] | None = None
        self._known_projects: set[str] = set()
        self._known_people: set[str] = set()
        self._dicts_loaded = False

    def answer(self, prompt: str) -> str:
        # Only sniff the *template* portion (before the injected content) for
        # task type -- checking the whole prompt would misfire whenever the
        # injected document itself happens to quote one of these marker
        # phrases (e.g. a conversation that discusses this very pipeline).
        idx = prompt.rfind(_CONTENT_DELIM)
        header = prompt[:idx] if idx != -1 else prompt

        if _DESC_FILL_MARK in header:
            return self._description_fill(prompt)
        if _ENTITY_MARK in header:
            return self._entity(self._content(prompt))
        if _KEYWORD_MARK in header:
            return self._keyword(self._content(prompt))
        if _RELATED_MARK in header:
            return self._related(prompt)
        return self._summary(self._content(prompt))

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _content(prompt: str) -> str:
        idx = prompt.rfind(_CONTENT_DELIM)
        return prompt[idx + len(_CONTENT_DELIM) :].strip() if idx != -1 else prompt.strip()

    def _tokenize(self, text: str) -> list[str]:
        return [t for t in _TOKEN_RE.findall(text) if t.lower() not in _STOPWORDS and len(t) > 1]

    def _ensure_corpus(self) -> None:
        if self._corpus_df is not None:
            return
        df: Counter = Counter()
        size = 0
        summary_dir = VAULT / "knowledge" / "summary"
        if summary_dir.exists():
            for f in summary_dir.glob("*.md"):
                for t in set(self._tokenize(f.read_text(encoding="utf-8", errors="ignore"))):
                    df[t.lower()] += 1
                size += 1
        self._corpus_df = df
        self._corpus_size = max(size, 1)

    def _ensure_dicts(self) -> None:
        if self._dicts_loaded:
            return
        projects_dir = VAULT / "projects"
        if projects_dir.exists():
            self._known_projects = {f.stem for f in projects_dir.glob("*.md") if f.stem.strip()}
        people_dir = VAULT / "people"
        if people_dir.exists():
            self._known_people = {f.stem for f in people_dir.glob("*.md") if f.stem.strip()}
        self._dicts_loaded = True

    def _ensure_doc_texts(self) -> None:
        if self._doc_texts is not None:
            return
        texts: dict[str, str] = {}
        for folder in ("wiki", "projects", "people"):
            d = VAULT / folder
            if not d.exists():
                continue
            for f in d.glob("*.md"):
                texts.setdefault(f.stem, f.read_text(encoding="utf-8", errors="ignore"))
        summary_dir = VAULT / "knowledge" / "summary"
        if summary_dir.exists():
            for f in summary_dir.glob("*.md"):
                texts.setdefault(f.stem, f.read_text(encoding="utf-8", errors="ignore"))
        self._doc_texts = texts

    def _idf(self, term_lower: str) -> float:
        df = self._corpus_df.get(term_lower, 1) if self._corpus_df else 1
        return math.log((self._corpus_size + 1) / (df + 1)) + 1

    def _keyword_terms(self, text: str, top_n: int = 10) -> list[str]:
        self._ensure_corpus()
        tf = Counter(self._tokenize(text))
        scored = []
        for term, freq in tf.items():
            lower = term.lower()
            score = freq * self._idf(lower)
            if _NUMERIC_RE.search(term) or any(ch.isdigit() for ch in term):
                score *= 1.5
            scored.append((score, term, lower))
        scored.sort(key=lambda x: -x[0])
        result, seen = [], set()
        for _, term, lower in scored:
            if lower in seen:
                continue
            seen.add(lower)
            result.append(term)
            if len(result) >= top_n:
                break
        return result

    # ------------------------------------------------------------------
    # Task-specific generators
    # ------------------------------------------------------------------

    def _keyword(self, text: str) -> str:
        terms = self._keyword_terms(text, top_n=10)
        return "\n".join(f"- {t}" for t in terms) if terms else "- (키워드 없음)"

    def _entity(self, text: str) -> str:
        self._ensure_dicts()
        found: list[dict] = []
        seen: set[tuple[str, str]] = set()

        def add(entity_type: str, name: str) -> None:
            name = name.strip()
            key = (entity_type, name.lower())
            if not name or key in seen:
                return
            seen.add(key)
            found.append({"type": entity_type, "name": name})

        for name in self._known_projects:
            if name and name in text:
                add("Project", name)
        for name in self._known_people:
            if name and name in text:
                add("Person", name)
        for term in _TECH_TERMS:
            if re.search(rf"\b{re.escape(term)}\b", text, re.IGNORECASE):
                add("Technology", term)

        for term in self._keyword_terms(text, top_n=8):
            if len(found) >= 12:
                break
            if re.fullmatch(r"[가-힣]{2,}", term) and not term.endswith(_KO_VERB_ENDINGS):
                add("Concept", term)

        return json.dumps(found[:12], ensure_ascii=False, indent=2)

    def _description_fill(self, prompt: str) -> str:
        """description_fill_prompt.txt has its own {entity_name}/{entity_type}/
        [기존 문서]/[새 자료] shape, not the single {content-after-delimiter}
        shape the other three prompts use -- so this doesn't route through
        _content(). Returns the {description, summary, related_entities, tags}
        dict DescriptionFillProcessor expects, synthesized from [새 자료]."""
        header_m = _DESC_FILL_HEADER_RE.search(prompt)
        entity_name = header_m.group(1) if header_m else ""

        source_m = _DESC_FILL_SOURCE_RE.search(prompt)
        source = source_m.group(1).strip() if source_m else ""
        existing_m = _DESC_FILL_EXISTING_RE.search(prompt)
        existing = existing_m.group(1).strip() if existing_m else ""

        sentences = [
            s.strip() for s in re.split(r"(?<=[.!?])\s+|\n{2,}", source) if len(s.strip()) > 15
        ]
        description = " ".join(sentences[:2]) or existing[:200] or "TODO"

        scored_sent = sorted(
            ((len(self._tokenize(s)), s) for s in sentences[:200]),
            key=lambda x: -x[0],
        )
        summary_lines = [s for _, s in scored_sent[:4]]
        summary = "\n".join(f"- {line}" for line in summary_lines)

        entities_json = self._entity(source)
        related_entities, seen_names = [], set()
        for e in json.loads(entities_json):
            n = e["name"]
            if n.lower() in (entity_name.lower(), *seen_names):
                continue
            seen_names.add(n.lower())
            related_entities.append(n)
        related_entities = related_entities[:10]

        tags = [t.lower() for t in self._keyword_terms(source, top_n=8)]

        return json.dumps(
            {
                "description": description,
                "summary": summary,
                "related_entities": related_entities,
                "tags": tags,
            },
            ensure_ascii=False,
        )

    def _related(self, prompt: str) -> str:
        m = re.search(r"\[존재하는 문서 목록\]\n(.*?)\n\n=+", prompt, re.S)
        doc_names = (
            [line[2:].strip() for line in m.group(1).splitlines() if line.startswith("- ")]
            if m
            else []
        )
        if not doc_names:
            return ""

        self._ensure_corpus()
        self._ensure_doc_texts()
        text = self._content(prompt)
        target_tf = Counter(t.lower() for t in self._tokenize(text))
        if not target_tf:
            return ""

        scored = []
        for name in doc_names:
            content = self._doc_texts.get(name, name)
            cand_tokens = {t.lower() for t in self._tokenize(content)}
            score = sum(target_tf[t] * self._idf(t) for t in cand_tokens if t in target_tf)
            if score > 0:
                scored.append((score, name))
        scored.sort(key=lambda x: -x[0])
        return "\n".join(f"[[{n}]]" for _, n in scored[:10])

    def _summary(self, text: str) -> str:
        # markdown_processor wraps raw source content as
        # "# Summary\n\n> TODO\n\n# Original Content\n\n<original>" -- strip
        # that boilerplate so the title/body/TODO detection below reads the
        # actual source, not the wrapper's own placeholder text.
        marker = "# Original Content"
        idx = text.find(marker)
        content = text[idx + len(marker) :] if idx != -1 else text

        title_match = re.search(r"^#+\s*(.+)$", content, re.M)
        title = title_match.group(1).strip() if title_match else "요약"
        title = title.lstrip("#").strip()  # guard against "## nested #" leaking through

        numeric_lines = []
        for line in content.splitlines():
            if _NUMERIC_RE.search(line):
                cleaned = line.strip().lstrip("#-* ").strip()
                if cleaned and cleaned not in numeric_lines:
                    numeric_lines.append(cleaned)
            if len(numeric_lines) >= 8:
                break

        todo_lines = [
            line.strip("-* ").strip()
            for line in content.splitlines()
            if re.search(r"TODO|해야\s?함|해야할|필요함", line)
        ][:5]
        decision_lines = [
            line.strip("-* ").strip()
            for line in content.splitlines()
            if re.search(r"결정|하기로|채택|확정", line)
        ][:5]

        sentences = [
            s.strip() for s in re.split(r"(?<=[.!?])\s+|\n{2,}", content) if len(s.strip()) > 20
        ]
        scored_sent = sorted(
            ((len(self._tokenize(s)), s) for s in sentences[:400]),
            key=lambda x: -x[0],
        )
        excerpt = "\n\n".join(s for _, s in scored_sent[:5]) or (
            sentences[0] if sentences else content[:500]
        )
        keywords = self._keyword_terms(content, top_n=10)

        lines = [
            f"# 요약: {title}",
            "",
            "## 핵심 내용",
            "",
            excerpt,
            "",
            "## 수치 데이터",
            "",
            "\n".join(f"- {line}" for line in numeric_lines) if numeric_lines else "해당 없음",
            "",
            "## TODO",
            "",
            "\n".join(f"- {line}" for line in todo_lines) if todo_lines else "없음",
            "",
            "## 결정사항",
            "",
            "\n".join(f"- {line}" for line in decision_lines) if decision_lines else "없음",
            "",
            "## 중요 키워드",
            "",
            ", ".join(f"`{k}`" for k in keywords) if keywords else "없음",
        ]
        return "\n".join(lines)
