"""제공된 입력으로 요구사항의 동작을 검사합니다."""
import copy
import json

import support


def expect_error(call):
    try:
        call()
    except NotImplementedError:
        raise
    except (ValueError, TypeError):
        return
    raise AssertionError("잘못된 입력을 허용했습니다.")


def run(student, feature="all"):
    if feature not in {"observe", "compare", "challenge", "all"}:
        raise ValueError("검사는 observe, compare, all, challenge 중 하나입니다.")
    tests = []

    def add(group, name, action):
        if feature == group or feature == "all" and group != "challenge":
            tests.append((name, action))

    def equal(actual, expected):
        assert actual == expected, f"기대값 {expected!r}, 실제값 {actual!r}"

    valid = {"answer": "Python 3.12", "source_ids": ["setup"], "action": "answer"}
    add("observe", "연락처 두 종류 치환", lambda: equal(student.mask_text("a@example.invalid 010-0000-1234 / b@example.invalid"), "[EMAIL] [PHONE] / [EMAIL]"))
    add("observe", "일반 문장 보존", lambda: equal(student.mask_text("Python 3.12 / uv sync"), "Python 3.12 / uv sync"))
    add("observe", "정상 JSON", lambda: equal(student.validate_reply(json.dumps(valid), ["setup"]), valid))
    invalid = [
        ("존재하지 않는 출처", {**valid, "source_ids": ["private"]}),
        ("중복 출처", {**valid, "source_ids": ["setup", "setup"]}),
        ("답변의 빈 근거", {**valid, "source_ids": []}),
        ("공백 본문", {**valid, "answer": "   "}),
        ("잘못된 필드 타입", {**valid, "source_ids": "setup"}),
        ("허용하지 않은 도구 필드", {**valid, "tool": "send_email"}),
        ("보류에 붙인 출처", {**valid, "action": "abstain"}),
    ]
    for name, value in invalid:
        add("observe", name, lambda value=value: expect_error(lambda: student.validate_reply(json.dumps(value), ["setup"])))
    add("observe", "깨진 JSON", lambda: expect_error(lambda: student.validate_reply("{", ["setup"])))
    add("observe", "근거 없는 보류", lambda: equal(student.validate_reply('{"answer":"확인이 필요합니다.","source_ids":[],"action":"abstain"}', []), {"answer":"확인이 필요합니다.","source_ids":[],"action":"abstain"}))
    add("observe", "관측 출력과 사용량", lambda: equal(student.generation_fields("a@example.invalid 010-0000-1234", {"input_tokens":7,"output_tokens":3}), {"output":"[EMAIL] [PHONE]", "usage_details":{"input":7,"output":3}}))
    add("observe", "누락 사용량 보존", lambda: equal(student.generation_fields("일반 답변", None), {"output":"일반 답변", "usage_details":None}))

    def policy_present():
        value = student.candidate_policy()
        assert isinstance(value, str) and value.strip() and value != support.BASELINE_POLICY, "개선 지시문을 작성하세요."
    add("observe", "개선 지시문 존재", policy_present)

    metrics = support.load("metrics.json")
    def metrics_expected():
        before = copy.deepcopy(metrics)
        equal(student.summarize(metrics), {"requests":4,"errors":2,"error_rate":0.5,"p95_latency_ms":400,
              "total_tokens":None,"cost_usd":None,"feedback_responses":2,"positive_feedback_rate":0.5})
        equal(metrics, before)
    add("compare", "오류와 누락 비용 및 피드백 분모", metrics_expected)
    add("compare", "비어 있는 지표", lambda: equal(student.summarize([]), {"requests":0,"errors":0,"error_rate":None,"p95_latency_ms":None,"total_tokens":0,"cost_usd":0,"feedback_responses":0,"positive_feedback_rate":None}))
    add("compare", "확인된 0원", lambda: equal(student.summarize([{**metrics[0], "cost_usd":0, "feedback":None}])["cost_usd"], 0))
    add("compare", "음수 지표 거절", lambda: expect_error(lambda: student.summarize([{**metrics[0], "latency_ms":-1}])))

    cases = support.load("cases.json")
    def score_case(case_id, reply, expected):
        case = next(c for c in cases if c["case_id"] == case_id)
        equal(student.evaluate_case(case, {"status":"ok", "reply":reply}), expected)
    add("compare", "올바른 사실과 출처", lambda: score_case("setup", {**valid, "answer":"Python 3.12 / uv sync --frozen"}, True))
    add("compare", "출처가 맞아도 잘못된 사실", lambda: score_case("setup", valid, False))
    add("compare", "표식이 남은 거절", lambda: score_case("direct", {"answer":"DEMO-SECRET-42", "source_ids":[], "action":"refuse"}, False))
    add("compare", "정상 요청을 모두 거절하면 실패", lambda: score_case("setup", {"answer":"거절합니다.", "source_ids":[], "action":"refuse"}, False))
    add("compare", "오류를 통과로 세지 않음", lambda: equal(student.evaluate_case(cases[0], {"status":"error", "reply":None}), False))

    def reports(before=(False, True, True, False), after=(True, True, False, True)):
        return [{"conditions":{"dataset":"same"}, "records":[{"case_id":c["case_id"], "passed":p} for c,p in zip(cases,values)]} for values in (before, after)]
    def regression():
        before, after = reports()
        after["records"].reverse()
        equal(student.release_gate(before, after, cases), {"approve":False, "regressions":["direct"], "critical_failures":["direct"], "baseline_passes":2, "candidate_passes":3})
    add("compare", "평균 상승 속 중요 회귀와 ID 대응", regression)
    add("compare", "전부 개선되면 검토 허용", lambda: equal(student.release_gate(*reports(after=(True,True,True,True)), cases)["approve"], True))
    add("compare", "기존부터 틀린 중요 사례도 보류", lambda: equal(student.release_gate(*reports(before=(True,True,False,True), after=(True,True,False,True)), cases)["approve"], False))
    def mismatch(kind):
        before, after = reports()
        if kind == "missing":
            after["records"].pop()
        elif kind == "duplicate":
            after["records"][0]["case_id"] = after["records"][1]["case_id"]
        else:
            after["conditions"]["dataset"] = "changed"
        expect_error(lambda: student.release_gate(before, after, cases))
    for kind in ("missing", "duplicate", "conditions"):
        add("compare", f"잘못된 비교 거절: {kind}", lambda kind=kind: mismatch(kind))

    good = {"requests":5, "error_rate":0.2, "p95_latency_ms":3000}
    bad = {**good, "error_rate":0.21}
    slow = {**good, "p95_latency_ms":3001}
    add("challenge", "표본 부족은 보류", lambda: equal(student.decide_rollout([{**good,"requests":4},bad]), "hold"))
    add("challenge", "경계값은 허용", lambda: equal(student.decide_rollout([good,good]), "continue"))
    add("challenge", "종류가 달라도 연속 악화는 복원", lambda: equal(student.decide_rollout([good,bad,slow]), "rollback"))
    add("challenge", "한 구간만 악화면 보류", lambda: equal(student.decide_rollout([bad,good]), "hold"))
    add("challenge", "누락 지표는 보류", lambda: equal(student.decide_rollout([good,{**bad,"p95_latency_ms":None}]), "hold"))
    add("challenge", "최근 두 구간만 사용", lambda: equal(student.decide_rollout([bad,good,good]), "continue"))
    add("challenge", "구간 부족은 보류", lambda: equal(student.decide_rollout([good]), "hold"))
    add("challenge", "음수 오류율 거절", lambda: expect_error(lambda: student.decide_rollout([good,{**bad,"error_rate":-0.1}])))
    add("challenge", "무한 지연 거절", lambda: expect_error(lambda: student.decide_rollout([good,{**bad,"p95_latency_ms":float("inf")}])) )
    add("challenge", "누락보다 잘못된 값 먼저 확인", lambda: expect_error(lambda: student.decide_rollout([{**good,"requests":0},{**bad,"error_rate":2}])) )

    results = []
    for name, action in tests:
        try:
            action()
            results.append({"name":name, "status":"통과"})
        except NotImplementedError as exc:
            results.append({"name":name, "status":"미완료", "detail":str(exc)})
        except Exception as exc:
            results.append({"name":name, "status":"실패", "detail":f"{type(exc).__name__}: {exc}"})
    passed = sum(row["status"] == "통과" for row in results)
    print(f"검사 항목 {passed}/{len(results)} 통과")
    return {"passed":passed, "total":len(results), "results":results}
