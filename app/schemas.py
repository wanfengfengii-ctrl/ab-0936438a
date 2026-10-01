"""请求 / 响应模型与入参校验。"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field, model_validator

CHRON_MIN, CHRON_MAX = 25, 60
SAMPLE_MIN, SAMPLE_MAX = 10, 24
QUOTA_MAX = 3


class CoreInput(BaseModel):
    """一支样芯: 指数序列、逐环容差、缺环/伪环限额。"""

    sample: List[int] = Field(
        ...,
        description="样芯逐环指数, 长度 10-24 (按环序, 索引 0 为最内环/最早年)",
    )
    tolerance: List[int] = Field(
        ..., description="逐环绝对容差, 与 sample 等长, 非负整数"
    )
    missing_ring_limit: int = Field(
        default=3, ge=0, le=QUOTA_MAX, description="缺环(跳过年表项)上限, 0-3"
    )
    false_ring_limit: int = Field(
        default=3, ge=0, le=QUOTA_MAX, description="伪环(跳过样芯项)上限, 0-3"
    )

    @model_validator(mode="after")
    def _check(self) -> "CoreInput":
        n = len(self.sample)
        if not (SAMPLE_MIN <= n <= SAMPLE_MAX):
            raise ValueError(
                f"样芯指数序列长度须在 {SAMPLE_MIN}-{SAMPLE_MAX} 之间, 实际 {n}"
            )
        if len(self.tolerance) != n:
            raise ValueError(
                f"容差序列长度({len(self.tolerance)})须与样芯长度({n})一致"
            )
        if any(t < 0 for t in self.tolerance):
            raise ValueError("容差须为非负整数")
        return self


class AlignRequest(BaseModel):
    chronology: List[int] = Field(
        ..., description="地区年表逐年生长指数, 长度 25-60"
    )
    chron_start_year: int = Field(
        ..., description="年表首项对应的日历年(整数), 用于换算共同终年"
    )
    core_a: CoreInput
    core_b: CoreInput

    @model_validator(mode="after")
    def _check(self) -> "AlignRequest":
        m = len(self.chronology)
        if not (CHRON_MIN <= m <= CHRON_MAX):
            raise ValueError(
                f"地区年表长度须在 {CHRON_MIN}-{CHRON_MAX} 之间, 实际 {m}"
            )
        return self


# --------------------------------------------------------------------------- #
# 响应
# --------------------------------------------------------------------------- #


class RingMatch(BaseModel):
    sample_ring_index: int  # 0-based
    sample_ring_number: int  # 1-based
    chron_index: int
    year: int
    sample_value: int
    chron_value: int
    diff: int


class CoreMapping(BaseModel):
    matches: List[RingMatch]
    matched_count: int
    missing_ring_years: List[int]  # 跳过的年表项(缺环)对应日历年
    missing_ring_count: int
    false_ring_indices: List[int]  # 跳过的样芯项索引(0-based, 含首匹配之前)
    false_ring_numbers: List[int]  # 同上, 1-based
    false_ring_count: int
    span_start_year: int
    end_year: int
    max_diff: int
    sum_diff: int


class JointMapping(BaseModel):
    core_a: CoreMapping
    core_b: CoreMapping
    end_year: int
    total_skips: int
    max_diff: int
    sum_diff: int


class AlignResponse(BaseModel):
    status: str  # "optimal"
    unique: bool
    ambiguity: str  # "unique" | "ambiguous"
    end_year: int
    optimal_end_years: List[int]
    total_skips: int
    max_diff: int
    sum_diff: int
    mapping: JointMapping  # 最优(按映射序的第一份)
    witnesses: List[JointMapping]  # 按映射序稳定的前两份见证
    witness_count_returned: int


class CoreEvidence(BaseModel):
    feasible_alone: bool
    minimum_skips: Optional[int]
    optimal_end_years_alone: List[int]
    infeasible_reasons: List[str]
    independent_mapping: Optional[CoreMapping] = None


class NoSolutionResponse(BaseModel):
    status: str  # "no_solution"
    reason: str
    message: str
    evidence_a: CoreEvidence
    evidence_b: CoreEvidence
