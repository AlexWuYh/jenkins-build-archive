import json
from typing import Any, List, Optional, Union

from pydantic import BaseModel, Field, field_validator

# Placeholders / empty tokens sometimes pushed from Jenkins scripts.
_FILE_PLACEHOLDERS = frozenset({"", "-", "—", "–", "n/a", "na", "null", "none"})


def _is_file_placeholder(text: str) -> bool:
    return text.lower() in _FILE_PLACEHOLDERS


def _split_file_blob(text: str) -> List[str]:
    """Split one blob into paths. Safe for single paths with no newline.

    Order of preference:
    1. Real newlines / CR (git name-only output)
    2. Literal ``\\n`` / ``\\r\\n`` only when that yields 2+ non-trivial parts
       (avoids mangling Windows-style paths like ``C:\\new\\file``)
    3. Otherwise keep the whole string as one path
    """
    if text is None:
        return []
    try:
        s = str(text).strip()
    except Exception:
        return []
    if not s or _is_file_placeholder(s):
        return []

    # 1) Real line breaks
    if "\n" in s or "\r" in s:
        normalized = s.replace("\r\n", "\n").replace("\r", "\n")
        parts = [ln.strip().strip('"').strip("'") for ln in normalized.split("\n")]
        return [p for p in parts if p and not _is_file_placeholder(p)]

    # 2) Literal backslash-n only when it clearly separates multiple entries
    if "\\n" in s or "\\r\\n" in s:
        trial = s.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\r", "\n")
        parts = [ln.strip().strip('"').strip("'") for ln in trial.split("\n")]
        parts = [p for p in parts if p and not _is_file_placeholder(p)]
        # Need 2+ parts; reject drive-letter-only fragments (e.g. "C:")
        if len(parts) >= 2 and not any(len(p) == 1 and p.isalpha() for p in parts):
            return parts

    # 3) Single path / no separator — keep as-is (including paths without \n)
    cleaned = s.strip('"').strip("'").strip()
    if cleaned and not _is_file_placeholder(cleaned):
        return [cleaned]
    return []


def expand_commit_files(value: Any) -> Optional[List[str]]:
    """Normalize commitFiles from Jenkins into a clean list of paths.

    Never raises: bad/odd input becomes None or a best-effort list.

    Accepts:
    - None / empty → None
    - ["a.py", "b.py"]  (no newlines — unchanged)
    - "a.py" / ["Jenkinsfile"]  (single path — one element)
    - "a.py\\nb.py" or real newlines
    - ["✏️ A\\n✏️ B"]  (single element with embedded separators)
    - JSON array string
    """
    try:
        if value is None:
            return None

        raw_items: List[Any] = []
        if isinstance(value, str):
            text = value.strip()
            if not text or _is_file_placeholder(text):
                return None
            if text.startswith("["):
                try:
                    parsed = json.loads(text)
                    if isinstance(parsed, list):
                        raw_items = list(parsed)
                    elif parsed is None:
                        return None
                    else:
                        raw_items = [parsed]
                except (json.JSONDecodeError, TypeError, ValueError):
                    raw_items = [text]
            else:
                raw_items = [text]
        elif isinstance(value, (list, tuple, set)):
            raw_items = list(value)
        else:
            # numbers / other scalars — stringify once, never crash
            try:
                raw_items = [value]
            except Exception:
                return None

        parts: List[str] = []
        for item in raw_items:
            if item is None:
                continue
            try:
                if isinstance(item, (list, tuple)):
                    # Nested list from odd Jenkins payloads
                    nested = expand_commit_files(list(item))
                    if nested:
                        parts.extend(nested)
                    continue
                parts.extend(_split_file_blob(item))
            except Exception:
                # Skip unreadable entry; do not fail the whole payload
                continue

        # De-dupe while preserving order
        seen: set[str] = set()
        out: List[str] = []
        for p in parts:
            if p in seen:
                continue
            seen.add(p)
            out.append(p)
        return out or None
    except Exception:
        # Absolute last resort: never break archive write/read
        try:
            if isinstance(value, str) and value.strip():
                return [value.strip()]
            if isinstance(value, list) and value:
                return [str(x) for x in value if x is not None and str(x).strip()]
        except Exception:
            pass
        return None


class BuildRecordIn(BaseModel):
    jobName: str = Field(min_length=1, max_length=500)
    buildId: int = Field(ge=1)
    buildDate: str = Field(min_length=1, max_length=100)
    gitRepository: Optional[str] = Field(default=None, max_length=1000)
    gitBranch: Optional[str] = Field(default=None, max_length=1000)
    gitCommit: Optional[str] = Field(default=None, max_length=200)
    commitMsg: Optional[str] = Field(default=None, max_length=8000)
    commitAuthor: Optional[str] = Field(default=None, max_length=500)
    commitId: Optional[str] = Field(default=None, max_length=200)
    # list of paths, or a single string / newline-joined text from Jenkins
    commitFiles: Optional[Union[List[str], str]] = None
    dockerRegistry: Optional[str] = Field(default=None, max_length=500)
    dockerRepository: Optional[str] = Field(default=None, max_length=1000)
    dockerImageTag: Optional[str] = Field(default=None, max_length=1000)
    dockerImageDigest: Optional[str] = Field(default=None, max_length=500)
    buildResult: Optional[str] = Field(default=None, max_length=50)
    buildUrl: Optional[str] = Field(default=None, max_length=2000)
    durationMs: Optional[int] = Field(default=None, ge=0)

    @field_validator("buildUrl")
    @classmethod
    def build_url_must_be_http(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        stripped = value.strip()
        if not stripped:
            return None
        lower = stripped.lower()
        if not (lower.startswith("http://") or lower.startswith("https://")):
            raise ValueError("buildUrl must start with http:// or https://")
        return stripped

    @field_validator("durationMs", mode="before")
    @classmethod
    def normalize_duration_ms(cls, value: Any) -> Optional[int]:
        """Accept int/float/numeric string; treat empty / placeholder as missing."""
        if value is None:
            return None
        if isinstance(value, str):
            text = value.strip()
            if not text or text in {"-", "—", "–"}:
                return None
            try:
                value = float(text)
            except ValueError as exc:
                raise ValueError("durationMs must be a non-negative number") from exc
        if isinstance(value, bool):
            raise ValueError("durationMs must be a non-negative number")
        if isinstance(value, (int, float)):
            if value < 0:
                raise ValueError("durationMs must be >= 0")
            return int(value)
        raise ValueError("durationMs must be a non-negative number")

    @field_validator("commitFiles", mode="before")
    @classmethod
    def normalize_commit_files(cls, value: Any) -> Optional[List[str]]:
        return expand_commit_files(value)

    def commit_files_json(self) -> Optional[str]:
        if not self.commitFiles:
            return None
        return json.dumps(self.commitFiles, ensure_ascii=False)


class BuildRecordOut(BuildRecordIn):
    id: int
    createdAt: str
    updatedAt: str
