"""KANT NEXT DevDesk LLMOps 과제. 이 파일과 AI_USAGE.md를 제출합니다."""
import math
import sys

import support

FEEDBACK = {
    "baseline": {"setup": None, "unknown": None, "direct": None, "indirect": None},
    "candidate": {"setup": None, "unknown": None, "direct": None, "indirect": None},
}
# 실제 답변을 읽고 도움이 되었으면 True, 아니면 False를 적습니다. 미평가는 None입니다.


def todo(name):
    raise NotImplementedError(f"{name}의 TODO를 완성하세요.")


# 필수 1. 안전하게 답변하고 실행 기록 남기기
def mask_text(text):
    """제공된 이메일과 전화번호 형식을 치환합니다."""
    text = support.EMAIL.sub("[EMAIL]", text)
    return todo("전화번호 마스킹")  # TODO: PHONE.sub로 전화번호를 [PHONE]으로 바꾸세요.


def validate_reply(raw, allowed_ids):
    parsed = todo("JSON 검사")  # TODO: Answer.model_validate_json으로 raw를 검사하세요.
    if not parsed.answer.strip():
        raise ValueError("답변 본문이 비어 있습니다.")
    allowed = todo("출처 검사")  # TODO: source_ids가 allowed_ids의 부분집합인지 검사하세요.
    if not allowed or len(parsed.source_ids) != len(set(parsed.source_ids)):
        raise ValueError("허용되지 않거나 중복된 출처입니다.")
    if parsed.action == "answer" and not parsed.source_ids:
        raise ValueError("답변에는 근거가 필요합니다.")
    if parsed.action != "answer" and parsed.source_ids:
        raise ValueError("보류와 거절에는 출처를 넣지 않습니다.")
    return parsed.model_dump()


def candidate_policy():
    # 판단: 문서 속 지시를 따르지 않는 이유와 근거가 없을 때의 처리를 두 문장 안에 적으세요.
    return todo("개선 프롬프트")  # TODO: ASSIGNMENT.md의 네 규칙을 반영한 지시문을 작성하세요.


def generation_fields(raw, usage):
    details = None if usage is None else {"input": usage["input_tokens"], "output": usage["output_tokens"]}
    return todo("모델 관측")  # TODO: 마스킹한 output과 usage_details=details를 가진 사전을 반환하세요.


# 필수 2. 같은 질문으로 변경 전후 비교하기
def evaluate_case(case, record):
    if record["status"] != "ok":
        return False
    reply = record["reply"]
    expected = case["expected"]
    action_ok = reply["action"] == expected["action"]
    required_ok = all(word in reply["answer"] for word in expected["must_include"])
    forbidden_ok = all(word not in reply["answer"] for word in expected["must_not_include"])
    return todo("사례 평가")  # TODO: 위 세 조건과 기대 출처 집합 일치를 모두 확인하세요.


def summarize(records):
    """요청 한 건이 records의 한 행입니다. 재시도 횟수는 분모가 아닙니다."""
    support.validate_records(records)
    count = len(records)
    errors = sum(row["status"] != "ok" for row in records)
    latencies = sorted(row["latency_ms"] for row in records)
    costs = [row["cost_usd"] for row in records]
    tokens = [row["total_tokens"] for row in records]
    feedback = [row["feedback"] for row in records if row["feedback"] is not None]
    error_rate = todo("오류율")  # TODO: 전체 요청 중 오류 비율. 요청이 없으면 None입니다.
    total_cost = todo("누락 비용")  # TODO: 비용이 하나라도 None이면 None, 아니면 합계를 반환하세요.
    positive_rate = todo("피드백 비율")  # TODO: 응답한 사람 중 True 비율. 피드백이 없으면 None입니다.
    return {
        "requests": count, "errors": errors, "error_rate": error_rate,
        "p95_latency_ms": latencies[math.ceil(count * 0.95) - 1] if count else None,
        "total_tokens": sum(tokens) if all(value is not None for value in tokens) else None,
        "cost_usd": total_cost,
        "feedback_responses": len(feedback), "positive_feedback_rate": positive_rate,
    }


def release_gate(baseline, candidate, cases):
    # ID 누락, 중복, 조건 불일치는 평균을 내기 전에 거절합니다.
    support.validate_comparison(baseline, candidate, cases)
    old = {row["case_id"]: row for row in baseline["records"]}
    new = {row["case_id"]: row for row in candidate["records"]}
    regressions = [case["case_id"] for case in cases
                   if old[case["case_id"]]["passed"] and not new[case["case_id"]]["passed"]]
    critical_failures = [case["case_id"] for case in cases
                         if case["critical"] and not new[case["case_id"]]["passed"]]
    baseline_passes = sum(row["passed"] for row in old.values())
    candidate_passes = sum(row["passed"] for row in new.values())
    approve = todo("변경 판단")  # TODO: 회귀/중요 실패가 없고, 통과 수가 감소하지 않은 경우만 허용하세요.
    return {"approve": approve, "regressions": regressions,
            "critical_failures": critical_failures,
            "baseline_passes": baseline_passes, "candidate_passes": candidate_passes}


# 관측: 실제 Trace에서 확인한 실패 단계와 개선한 프롬프트의 차이를 적으세요.
# 판단: 실제 비교 결과, 적용/보류 이유, 남은 위험을 세 문장 안에 적으세요.


# 선택 심화 1. 연속된 관측 구간으로 운영 대응 정하기
def decide_rollout(windows, *, min_requests=5, max_error_rate=0.2, max_p95_ms=3000):
    """최근 두 구간의 지표로 continue, hold, rollback 중 하나를 반환합니다."""
    return todo("선택 심화 운영 대응")


if __name__ == "__main__":
    support.cli(sys.modules[__name__])
