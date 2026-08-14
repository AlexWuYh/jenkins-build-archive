from typing import Optional

from pydantic import BaseModel, Field, field_validator


class BuildRecordIn(BaseModel):
    jobName: str = Field(min_length=1, max_length=500)
    buildId: int = Field(ge=1)
    buildDate: str = Field(min_length=1, max_length=100)
    gitRepository: Optional[str] = Field(default=None, max_length=1000)
    gitBranch: Optional[str] = Field(default=None, max_length=1000)
    gitCommit: Optional[str] = Field(default=None, max_length=200)
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


class BuildRecordOut(BuildRecordIn):
    id: int
    createdAt: str
    updatedAt: str
