"""两芯联合树轮定年对齐服务。"""

from __future__ import annotations

from typing import List

from fastapi import FastAPI
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .alignment import (
    IndependentEvidence,
    NoSolution,
    Placement,
    Solution,
    joint_align,
)
from .schemas import (
    AlignRequest,
    AlignResponse,
    CoreEvidence,
    CoreMapping,
    JointMapping,
    NoSolutionResponse,
    RingMatch,
)

app = FastAPI(
    title="木构文物两芯联合树轮定年服务",
    version="1.0.0",
    description="同一根梁材两支树芯共同对入地区年表, 联合最优且防矛盾砍伐年代。",
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "status": "validation_error",
            "message": "请求参数未通过校验",
            "errors": jsonable_encoder(exc.errors()),
        },
    )


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/")
def root() -> dict:
    return {"service": "dendro-dual-core-align", "docs": "/docs", "health": "/health"}


# --------------------------------------------------------------------------- #
# 结果序列化
# --------------------------------------------------------------------------- #


def _build_core_mapping(
    placement: Placement,
    sample: List[int],
    chron: List[int],
    chron_start_year: int,
) -> CoreMapping:
    matched_sample = {i for i, _ in placement.pairs}
    matched_chron = {j for _, j in placement.pairs}

    matches: List[RingMatch] = []
    for i, j in sorted(placement.pairs, key=lambda p: p[1]):
        diff = abs(sample[i] - chron[j])
        matches.append(
            RingMatch(
                sample_ring_index=i,
                sample_ring_number=i + 1,
                chron_index=j,
                year=chron_start_year + j,
                sample_value=sample[i],
                chron_value=chron[j],
                diff=diff,
            )
        )

    # 缺环: 样芯跨度 (span_start..end) 内未匹配的年表项
    missing_years = [
        chron_start_year + j
        for j in range(placement.span_start, placement.end_index + 1)
        if j not in matched_chron
    ]
    # 伪环: 未参与匹配的样芯环 (含首条匹配之前的环)
    false_idx = [i for i in range(len(sample)) if i not in matched_sample]

    return CoreMapping(
        matches=matches,
        matched_count=len(matches),
        missing_ring_years=missing_years,
        missing_ring_count=len(missing_years),
        false_ring_indices=false_idx,
        false_ring_numbers=[i + 1 for i in false_idx],
        false_ring_count=len(false_idx),
        span_start_year=chron_start_year + placement.span_start,
        end_year=chron_start_year + placement.end_index,
        max_diff=placement.max_diff,
        sum_diff=placement.sum_diff,
    )


def _build_joint(
    pa: Placement,
    pb: Placement,
    req: AlignRequest,
) -> JointMapping:
    chron = req.chronology
    return JointMapping(
        core_a=_build_core_mapping(pa, req.core_a.sample, chron, req.chron_start_year),
        core_b=_build_core_mapping(pb, req.core_b.sample, chron, req.chron_start_year),
        end_year=req.chron_start_year + pa.end_index,
        total_skips=pa.skips + pb.skips,
        max_diff=max(pa.max_diff, pb.max_diff),
        sum_diff=pa.sum_diff + pb.sum_diff,
    )


def _build_evidence(ev: IndependentEvidence, req: AlignRequest, core_name: str) -> CoreEvidence:
    core = req.core_a if core_name == "a" else req.core_b
    indep = None
    if ev.best_placement is not None:
        indep = _build_core_mapping(
            ev.best_placement, core.sample, req.chronology, req.chron_start_year
        )
    return CoreEvidence(
        feasible_alone=ev.feasible_alone,
        minimum_skips=ev.minimum_skips,
        optimal_end_years_alone=[
            req.chron_start_year + j for j in ev.optimal_end_indices
        ],
        infeasible_reasons=ev.reasons,
        independent_mapping=indep,
    )


# --------------------------------------------------------------------------- #
# 路由
# --------------------------------------------------------------------------- #


@app.post("/api/dendro/align")
def align(req: AlignRequest):
    result = joint_align(
        chron=req.chronology,
        sample_a=req.core_a.sample,
        sample_b=req.core_b.sample,
        tolerance_a=req.core_a.tolerance,
        tolerance_b=req.core_b.tolerance,
        cap_missing_a=req.core_a.missing_ring_limit,
        cap_false_a=req.core_a.false_ring_limit,
        cap_missing_b=req.core_b.missing_ring_limit,
        cap_false_b=req.core_b.false_ring_limit,
    )

    if isinstance(result, NoSolution):
        body = NoSolutionResponse(
            status="no_solution",
            reason=result.reason,
            message=result.message,
            evidence_a=_build_evidence(result.evidence_a, req, "a"),
            evidence_b=_build_evidence(result.evidence_b, req, "b"),
        )
        return JSONResponse(status_code=409, content=body.model_dump())

    sol: Solution = result
    witnesses = [_build_joint(pa, pb, req) for pa, pb in sol.witnesses]
    primary = witnesses[0]
    return AlignResponse(
        status="optimal",
        unique=not sol.ambiguous,
        ambiguity="unique" if not sol.ambiguous else "ambiguous",
        end_year=primary.end_year,
        optimal_end_years=[req.chron_start_year + j for j in sol.optimal_end_indices],
        total_skips=sol.total_skips,
        max_diff=sol.max_diff,
        sum_diff=sol.sum_diff,
        mapping=primary,
        witnesses=witnesses,
        witness_count_returned=len(witnesses),
    )
