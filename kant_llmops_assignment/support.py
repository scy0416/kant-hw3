"""제공 코드: 자료, API 연결, 실행과 결과 저장."""
import argparse
import hashlib
import json
import math
import os
from contextlib import nullcontext
from pathlib import Path
import re
import sys
import time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parent
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE = re.compile(r"(?<!\d)01[016789]-\d{3,4}-\d{4}(?!\d)")
BASELINE_POLICY = "DevDesk 문서로 답하세요. 일반적인 지식으로 내용을 보충할 수 있습니다."
CHAIN_VERSION = "devdesk-qa-2"
EVALUATOR_VERSION = "exact-conditions-1"


class Answer(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    answer: str = Field(min_length=1, max_length=600)
    source_ids: list[str]
    action: Literal["answer", "abstain", "refuse"]


def load(name):
    return json.loads((ROOT / "data" / name).read_text(encoding="utf-8"))


def save(name, value):
    path = ROOT / "artifacts" / name
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(f"저장: artifacts/{name}")
    return path


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def safe_output(student, raw):
    # JSON escape를 복원한 뒤 같은 연락처 필터를 키와 값에 적용합니다.
    # 깨진 JSON은 원문을 기록하지 않고, 형식 검사는 validate 단계에서 원문으로 수행합니다.
    try:
        text = json.dumps(json.loads(raw), ensure_ascii=False)
    except json.JSONDecodeError:
        return "[INVALID_JSON_OUTPUT]"
    return student.mask_text(text)


def validate_records(records):
    seen = set()
    for row in records:
        if row["case_id"] in seen or row["status"] not in {"ok", "error"}:
            raise ValueError("요청 ID 중복 또는 잘못된 상태입니다.")
        seen.add(row["case_id"])
        for key in ("latency_ms", "total_tokens", "cost_usd"):
            value = row[key]
            if value is None and key != "latency_ms":
                continue
            if type(value) not in {int, float} or not math.isfinite(value) or value < 0:
                raise ValueError(f"{key}는 0 이상의 유한한 수여야 합니다.")
        if row["feedback"] is not None and type(row["feedback"]) is not bool:
            raise ValueError("피드백은 True, False, None 중 하나입니다.")


def validate_comparison(baseline, candidate, cases):
    expected_ids = {case["case_id"] for case in cases}
    if len(expected_ids) != len(cases) or not cases:
        raise ValueError("평가 사례가 비었거나 ID가 중복됩니다.")
    if baseline["conditions"] != candidate["conditions"]:
        raise ValueError("데이터, 모델, 평가 조건이 다릅니다.")
    for report in (baseline, candidate):
        rows = report["records"]
        if len(rows) != len(expected_ids) or {r["case_id"] for r in rows} != expected_ids:
            raise ValueError("평가 사례에 누락 또는 중복이 있습니다.")
        if any(type(r["passed"]) is not bool for r in rows):
            raise ValueError("평가 결과는 불리언이어야 합니다.")


def connection(student):
    from dotenv import load_dotenv
    from langfuse import Langfuse
    from openai import OpenAI
    load_dotenv(ROOT / ".env", override=False)
    required = ("OPENAI_API_KEY", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_BASE_URL")
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise ValueError(".env 설정이 필요합니다: " + ", ".join(missing))

    def mask(data, **_):
        if isinstance(data, str):
            return student.mask_text(data)
        if isinstance(data, dict):
            return {k: mask(v) for k, v in data.items()}
        if isinstance(data, (list, tuple)):
            return [mask(v) for v in data]
        return data

    langfuse = Langfuse(environment="devdesk-assignment", mask=mask)
    if not langfuse.auth_check():
        langfuse.shutdown()
        raise ValueError("Langfuse 인증을 확인하세요. 키와 지역 주소는 출력하지 않습니다.")
    model = OpenAI(max_retries=0, timeout=45)
    return model, langfuse, os.environ.get("OPENAI_MODEL", "gpt-5.6-luna")


def observation(client, name, **kwargs):
    return client.start_as_current_observation(name=name, **kwargs) if client else nullcontext()


def request(student, case, version, *, model_client=None, langfuse=None, model_name="fixture"):
    mode = "live" if model_client else "fixture"
    question = student.mask_text(case["question"])
    documents = [dict(row, body=student.mask_text(row["body"])) for row in load("documents.json")
                 if row["doc_id"] in case["document_ids"]]
    metadata = {"case_id": case["case_id"], "version": version, "mode": mode}
    policy = student.candidate_policy() if version == "candidate" else BASELINE_POLICY
    if not isinstance(policy, str) or not policy.strip():
        raise ValueError("지시문이 비어 있습니다.")
    result = {"case_id": case["case_id"], "version": version, "mode": mode,
              "status": "error", "reply": None, "error_stage": None,
              "total_tokens": None, "cost_usd": None, "feedback": None,
              "trace_id": None, "trace_url": None, "stages": [], "usage": None,
              "model_input": None, "model_output": None, "request_payload": None,
              "response_received": False, "response_status": None}
    start = time.perf_counter()
    with observation(langfuse, "devdesk-request", input={"question": question}, metadata=metadata) as root:
        if root:
            result["trace_id"] = root.trace_id
            result["trace_url"] = langfuse.get_trace_url(trace_id=root.trace_id)
        stage = "retrieve"
        try:
            with observation(langfuse, stage, as_type="retriever", input={"document_ids": case["document_ids"]}) as span:
                if span:
                    span.update(output=documents)
            result["stages"].append({"name": stage, "status": "ok", "document_ids": [d["doc_id"] for d in documents]})
            stage = "ticket-status"
            # 과제용 읽기 전용 조회입니다. 사용자 지정 도구나 외부 시스템을 실행하지 않습니다.
            tool_result = {"ticket_id": "DEV-100", "status": "담당자 확인 중"}
            with observation(langfuse, stage, as_type="tool", input={"ticket_id": "DEV-100"}) as span:
                if span:
                    span.update(output=tool_result)
            result["stages"].append({"name": stage, "status": "ok", "output": tool_result})
            stage = "generate"
            model_input = {"question": question, "documents": documents, "ticket": tool_result}
            result["model_input"] = model_input
            request_payload = {"instructions":policy + "\n다음 JSON 형식만 반환하세요:\n" + json.dumps(Answer.model_json_schema(), ensure_ascii=False),
                               "input":model_input}
            result["request_payload"] = request_payload
            with observation(langfuse, stage, as_type="generation", input=request_payload,
                             model=model_name, metadata={"prompt_sha256": digest(policy), "chain_version": CHAIN_VERSION}) as span:
                if model_client:
                    try:
                        response = model_client.responses.create(
                            model=model_name, instructions=request_payload["instructions"],
                            input=json.dumps(model_input, ensure_ascii=False), max_output_tokens=800,
                        )
                    except Exception as exc:
                        # 원래 SDK 예외의 요청 본문이 자동 예외 관측에 남지 않게 합니다.
                        result["error_type"] = type(exc).__name__
                        raise RuntimeError(type(exc).__name__) from None
                    raw = response.output_text
                    result["response_received"] = True
                    result["response_status"] = response.status
                    result["model_output"] = safe_output(student, raw)
                    usage = response.usage
                    if usage is not None:
                        result["total_tokens"] = usage.total_tokens
                        result["usage"] = {"input": usage.input_tokens, "output": usage.output_tokens}
                    fields = student.generation_fields(result["model_output"], usage.model_dump() if usage else None)
                    if span:
                        span.update(**fields)
                    if response.status != "completed":
                        raise ValueError("MODEL_INCOMPLETE")
                else:
                    raw = json.dumps(load("responses.json")[version][case["case_id"]], ensure_ascii=False)
                    result["model_output"] = safe_output(student, raw)
            result["stages"].append({"name": stage, "status": "ok"})
            stage = "validate"
            with observation(langfuse, stage, as_type="guardrail") as span:
                try:
                    reply = student.validate_reply(raw, [row["doc_id"] for row in documents])
                    reply["answer"] = student.mask_text(reply["answer"])
                except NotImplementedError:
                    raise
                except Exception as exc:
                    # 검증 오류의 입력 값도 SDK 자동 예외 관측에 남지 않게 합니다.
                    result["error_type"] = type(exc).__name__
                    raise RuntimeError(type(exc).__name__) from None
                result.update(status="ok", reply=reply)
                if span:
                    span.update(output={"valid": True})
            result["stages"].append({"name": stage, "status": "ok"})
        except NotImplementedError:
            raise
        except Exception as exc:
            # SDK 예외 메시지는 요청 원문을 포함할 수 있어 클래스 이름만 저장합니다.
            result["error_stage"] = stage
            result.setdefault("error_type", type(exc).__name__)
            result["stages"].append({"name": stage, "status": "error"})
            if root:
                root.update(level="ERROR", status_message=f"{stage}: {result['error_type']}")
        result["latency_ms"] = round((time.perf_counter() - start) * 1000, 3)
        if root:
            root.update(output={"status": result["status"], "reply": result["reply"], "error_stage": result["error_stage"]})
    return result


def comparison(student, *, live=False):
    cases = load("cases.json")
    model, langfuse, name = connection(student) if live else (None, None, "fixture")
    conditions = {"cases_sha256": digest(cases), "documents_sha256": digest(load("documents.json")),
                  "model": name, "max_output_tokens":800, "evaluator": EVALUATOR_VERSION, "mode": "live" if live else "fixture"}
    reports = {}
    try:
        for version in ("baseline", "candidate"):
            rows = []
            for case in cases:
                row = request(student, case, version, model_client=model, langfuse=langfuse, model_name=name)
                row["passed"] = student.evaluate_case(case, row)
                rows.append(row)
                if langfuse:
                    langfuse.create_score(trace_id=row["trace_id"], name="case_passed", value=int(row["passed"]), data_type="BOOLEAN")
            policy = BASELINE_POLICY if version == "baseline" else student.candidate_policy()
            reports[version] = {"conditions": dict(conditions), "prompt": policy, "prompt_sha256": digest(policy),
                                "chain_version": CHAIN_VERSION, "records": rows, "metrics": student.summarize(rows)}
        reports["gate"] = student.release_gate(reports["baseline"], reports["candidate"], cases)
    finally:
        if langfuse:
            langfuse.flush()
            langfuse.shutdown()
        if model:
            model.close()
    return reports


def verify_saved(student, name):
    from dotenv import load_dotenv
    from langfuse import Langfuse
    load_dotenv(ROOT / ".env", override=False)
    for key in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_BASE_URL"):
        if not os.environ.get(key):
            raise ValueError(f".env 설정이 필요합니다: {key}")
    path = ROOT / "artifacts" / name
    report = json.loads(path.read_text(encoding="utf-8"))
    if report.get("baseline", {}).get("conditions", {}).get("mode") != "live":
        raise ValueError("실제 비교 결과만 서버에서 조회할 수 있습니다.")
    client = Langfuse(tracing_enabled=False)
    checks = []
    try:
        for version in ("baseline", "candidate"):
            for row in report[version]["records"]:
                observations = client.api.observations.get_many(trace_id=row["trace_id"], limit=100, fields="core,basic,io,usage").data
                scores = client.api.scores_v3.get_many_v3(trace_id=row["trace_id"], limit=100).data
                score_ok = any(item.name == "case_passed" and item.value == int(row["passed"]) for item in scores)
                evidence = verify_observations(student, row, observations)
                complete = all(evidence.values()) and score_ok
                generations = [item for item in observations if item.name == "generate"]
                if generations and generations[0].total_cost is not None:
                    row["cost_usd"] = generations[0].total_cost
                row["feedback"] = student.FEEDBACK[version][row["case_id"]]
                checks.append({"case_id": row["case_id"], "version": version, "trace_id": row["trace_id"],
                               "observations": len(observations), "score_found": score_ok, "checks": evidence,
                               "usage_status": ("not_measured_before_response" if evidence.get("usage_match") and row.get("response_received") is False
                                                else "matched" if evidence.get("usage_match") else "unconfirmed"),
                               "verified": complete})
            report[version]["metrics"] = student.summarize(report[version]["records"])
    finally:
        client.shutdown()
    save(name, report)
    result = {"all_verified": all(row["verified"] for row in checks), "traces": checks}
    save("verification-live.json", result)
    return result


def verify_observations(student, row, observations):
    by_name = {item.name: item for item in observations}
    required = {"devdesk-request", "retrieve", "ticket-status", "generate"}
    if row["status"] == "ok" or row["error_stage"] == "validate":
        required.add("validate")
    present = required.issubset(by_name) and len(by_name) == len(observations)
    if not present:
        return {"required_stages": False}
    root = by_name["devdesk-request"]
    generation = by_name["generate"]
    parent_ok = root.parent_observation_id is None and all(
        item.parent_observation_id == root.id and item.trace_id == row["trace_id"]
        for item in observations if item.id != root.id)
    # 서버가 JSON 문자열을 객체로 해석해 반환해도 같은 내용으로 비교합니다.
    def comparable(value):
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        return value
    expected = row["model_input"]
    io_ok = (comparable(root.input) == {"question": expected["question"]}
             and comparable(root.output) == {"status":row["status"],"reply":row["reply"],"error_stage":row["error_stage"]}
             and comparable(generation.input) == row["request_payload"]
             and comparable(generation.output) == comparable(row["model_output"])
             and comparable(by_name["retrieve"].output) == expected["documents"]
             and comparable(by_name["ticket-status"].output) == expected["ticket"])
    if row["status"] == "ok":
        io_ok = io_ok and comparable(by_name["validate"].output) == {"valid": True}
    usage = generation.usage_details or {}
    failed_before_response = (row.get("response_received") is False and row["status"] == "error"
                              and row["error_stage"] == "generate" and row["model_output"] is None)
    usage_ok = ((row["usage"] is not None and all(usage.get(key) == value for key, value in row["usage"].items()))
                or (failed_before_response and row["usage"] is None and not usage))
    observed_io = json.dumps([{ "input": comparable(item.input), "output": comparable(item.output) }
                              for item in observations], ensure_ascii=False)
    return {"required_stages": present,
            "same_trace": root.trace_id == row["trace_id"], "parents": parent_ok,
            "closed": all(item.end_time is not None for item in observations),
            "input_output_match": bool(io_ok), "usage_match": usage_ok,
            "masked": student.mask_text(observed_io) == observed_io}


def cli(student):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="DevDesk LLMOps 과제")
    parser.add_argument("command", choices=("demo", "run", "check", "challenge", "verify"))
    parser.add_argument("feature", nargs="?", default="all")
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    if args.live and (args.command != "run" or args.feature != "compare"):
        parser.error("--live는 run compare에서만 사용합니다.")
    try:
        if args.command == "demo":
            print(f"자료 준비 완료: 문서 {len(load('documents.json'))}개, 질문 {len(load('cases.json'))}개. TODO 완료를 뜻하지 않습니다.")
        elif args.command == "check":
            import checks
            result = checks.run(student, args.feature)
            save(f"checks-{args.feature}.json", result)
            raise SystemExit(0 if result["passed"] == result["total"] else 1)
        elif args.command == "challenge":
            result = student.decide_rollout(load("windows.json"))
            save("challenge.json", {"decision": result})
        elif args.command == "verify":
            result = verify_saved(student, "compare-live.json")
            print("서버 확인 완료" if result["all_verified"] else "일부 기록 미확인. verification-live.json의 checks를 확인하세요. 반영 지연인 경우에만 잠시 뒤 verify를 다시 실행하세요.")
            raise SystemExit(0 if result["all_verified"] else 1)
        elif args.feature == "observe":
            save("observe-fixture.json", [request(student, case, "candidate") for case in load("cases.json")])
        elif args.feature == "metrics":
            save("metrics-fixture.json", student.summarize(load("metrics.json")))
        elif args.feature == "compare":
            mode = "live" if args.live else "fixture"
            report = comparison(student, live=args.live)
            save(f"compare-{mode}.json", report)
            print(f"변경 적용 판단: {report['gate']['approve']}. 사례별 답변과 실패 이유를 확인하세요.")
            if args.live:
                print("전송을 요청했습니다. verify 명령과 Langfuse 화면에서 저장 여부를 확인하세요.")
        else:
            parser.error("run 기능은 observe, metrics, compare입니다.")
    except (NotImplementedError, ValueError) as exc:
        print(str(exc))
        raise SystemExit(1)
