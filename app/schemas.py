import json
from typing import Any, List, Optional, Union

from pydantic import BaseModel, Field, field_validator


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
        if value is None:
            return None
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return None
            # JSON array string
            if text.startswith("["):
                try:
                    parsed = json.loads(text)
                    if isinstance(parsed, list):
                        return [str(x).strip() for x in parsed if str(x).strip()]
                except json.JSONDecodeError:
                    pass
            # newline or comma separated
            parts = []
            for line in text.replace(",", "\n").splitlines():
                item = line.strip()
                if item:
                    parts.append(item)
            return parts or None
        if isinstance(value, list):
            parts = [str(x).strip() for x in value if str(x).strip()]
            return parts or None
        return [str(value).strip()] if str(value).strip() else None

    def commit_files_json(self) -> Optional[str]:
        if not self.commitFiles:
            return None
        return json.dumps(self.commitFiles, ensure_ascii=False)


class BuildRecordOut(BuildRecordIn):
    id: int
    createdAt: str
    updatedAt: str
