"""main.py의 todo(...) 부분을 작성하세요. support.py와 checks.py는 그대로 사용합니다."""
import copy
import hashlib
import json
import sys

import support


def todo(message):
    raise NotImplementedError(message)


# 필수 1. 필요한 자료와 사용자 기억 관리하기
def select_context(items, user_id, now):
    kept = []
    for item in items:
        allowed = (
            (item["user_id"] == "public" or item["user_id"] == user_id)
            and item["trusted"]
            and item["active"]
            and (item["expires_at"] is None or item["expires_at"] > now)
        )
        if allowed:
            kept.append(copy.deepcopy(item))
    ####################################################################################################
    # 이유: 높은 우선순위의 자료를 먼저 고르면 어떤 문제가 생기는지 적으세요.
    ####################################################################################################
    # 높은 우선순위의 자료를 먼저 고르면 이미 만료가된 자료임에도 선택되는 경우가 발생할 수 있다.
    ####################################################################################################
    return sorted(kept, key=lambda item: (-item["priority"], item["id"]))


def memory_action(records, user_id, action, name, value=None):
    support.validate_memory_input(user_id, action, name, value)
    key = f"{user_id}:{name}"
    if action == "read":
        return copy.deepcopy(records.get(key))
    if action == "create":
        if key in records:
            raise ValueError("이미 있는 기억입니다. update를 사용하세요.")
        records[key] = copy.deepcopy(value)
    elif action == "update":
        if key not in records:
            raise KeyError("수정할 기억이 없습니다.")
        records[key] = copy.deepcopy(value)
    elif action == "delete":
        return records.pop(key) if key in records else None
    return copy.deepcopy(records[key])


def build_messages(prefix, question, context, turns, summary):
    data = json.dumps({"reference_data": context, "summary": summary}, ensure_ascii=False)
    history = [message for turn in turns for message in turn["messages"]]
    ####################################################################################################
    # 이유: 장기 기억과 세션 상태의 차이, 자료와 지시를 나누는 이유를 적으세요.
    ####################################################################################################
    # 장기 기억(style)은 여러 세션 전반에 거쳐 접근할 수 있는 기억이고 세션이 끝나도 사라지지 않는다.
    # 세션 상태(task)는 세션 내에서만 접근 가능하며 세션이 끝나면 세션 상태도 사라진다.
    # 지시는 LLM이 따라야 하는 사항에 대한 것이고, 자료는 지시를 수행하는데 있어 참고할 수 있는 요소이다.
    # 서로 역할이 다르기 때문에 명확하게 분리해서 전달한다.
    ####################################################################################################
    #return todo("고정 지시, 참고 자료, 대화, 현재 질문 순서의 메시지")
    return [
        {"role": "developer", "content": prefix},
        {"role": "user", "content": data},
        *history,
        {"role": "user", "content": question},
    ]


# 필수 2. 긴 대화를 줄이고 반복 입력 재사용하기
def summarize(turns):
    summary = {}
    for turn in turns:
        for name, value in support.fact_lines(turn["messages"][0]["content"]):
            summary[name] = {"value": value, "source_turn_id": turn["id"]}
    return summary


def select_window(turns, limit, reserve, margin, make_messages, count):
    support.validate_budget(limit, reserve, margin)
    budget = limit - reserve - margin
    if budget <= 0 or count(make_messages([])) > budget:
        raise ValueError("고정 입력만으로 예산을 넘었습니다.")
    kept = []
    for turn in reversed(turns):
        candidate = [turn, *kept]
        if count(make_messages(candidate)) > budget:
            break
        kept = candidate
    ####################################################################################################
    # 관측: 압축 비교 후 토큰 수, 빠진 사실, 선택한 한도를 기록합니다.
    ####################################################################################################
    # 전체 대화(5000토큰 제한)
    # - 입력 토큰 예산: 4488
    # - 예상 입력 토큰: 1999
    # - 입력된 대화: T01, T02, T03, T04, T05, T06, T07(전체)
    # - 답변
    #   - 담당자: 이지훈
    #   - 마감일: 2026-11-19
    #   - 승인조건: 배포 전에 보안틈 검토와 팀장 승인을 모두 받습니다.
    # - 사용량
    #   - 입력 토큰: 1938
    #   - 출력 토큰: 45
    #   - 전체 토큰: 1983
    # - 측정된 비용: 0.0004416usd
    # - 입력 토큰 비용: 0.0003876usd
    # - 지연시간: 2133.0ms
    #---------------------------------------------------------------------------------------------------
    # 최근 대화(2300토큰 제한)
    # - 입력 토큰 예산: 1788
    # - 예상 입력 토큰: 1744
    # - 입력된 대화: T05, T06, T07
    # - 답변
    #   - 담당자: 확인 필요
    #   - 마감일: 확인 필요
    #   - 승인조건: 배포 전에는 담당자의 확인과 팀장의 승인이 필요합니다.
    # - 사용량
    #   - 입력 토큰: 1699
    #   - 출력 토큰: 41
    #   - 전체 토큰: 1740
    # - 측정된 비용: 0.000389usd
    # - 입력 토큰 비용: 0.00033986usd
    # - 지연시간: 1443.3ms
    # ---------------------------------------------------------------------------------------------------
    # 요약과 최근 대화(2300토큰 제한)
    # - 입력 토큰 예산: 1788
    # - 예상 입력 토큰: 1744
    # - 입력된 대화: T06, T07
    # - 답변
    #   - 담당자: 이지훈
    #   - 마감일: 2026-11-19
    #   - 승인조건: 배포 전에 보안틈 검토와 팀장 승인을 모두 받습니다.
    # - 사용량
    #   - 입력 토큰: 1695
    #   - 출력 토큰: 45
    #   - 전체 토큰: 1740
    # - 측정된 비용: 0.000393usd
    # - 입력 토큰 비용: 0.000339usd
    # - 지연시간: 1257.6ms
    ####################################################################################################
    # 선택은 요약과 최근 대화로 하며, 이유는 정상적으로 결과를 만들어낼 수 있으면서, 입력 토큰, 비용, 지연시간이 가장 적다.
    ####################################################################################################
    return kept


def cache_key(prefix, user_id):
    return hashlib.sha256((user_id+"\n"+prefix).encode("utf-8")).hexdigest()
    ####################################################################################################
    # 관측: 실제 캐시 읽기/쓰기와 비용을 확인하고 미관측이면 그대로 적습니다.
    ####################################################################################################
    # 캐시 미사용
    # - 입력 토큰: 1533
    # - 출력 토큰: 45
    # - 전체 토큰: 1578
    # - 측정된 비용: 0.0003606usd
    #   - 캐시되지 않은 입력 비용: 0.0003066usd
    #   - 정확한 입력 비용: 0.0003066usd
    # 지연시간: 3444.5ms
    # --------------------------------------------------------------------------------------------------
    # 캐시 사용1(캐시 쓰기)
    # - 입력 토큰: 1533
    #   - 캐시 쓰기 토큰: 1228
    #   - 캐시된(재사용된) 토큰: 0
    #   - 캐시 스기 토큰 상세정보
    #       - ttl 12h 토큰: 0
    #       - ttl 30m 토큰: 1228
    # - 출력 토큰: 45
    # - 전체 토큰: 1578
    # - 측정된 비용: 0.000422usd
    #   - 캐시되지 않은 입력 비용: 0.0003066usd
    #   - 정확한 입력 비용: 0.000368usd
    # 지연시간: 1507.5ms
    # --------------------------------------------------------------------------------------------------
    # 캐시 사용2(캐시 사용)
    # - 입력 토큰: 1533
    #   - 캐시 쓰기 토큰: 0
    #   - 캐시된(재사용된) 토큰: 1228
    #   - 캐시 스기 토큰 상세정보
    #       - ttl 12h 토큰: 0
    #       - ttl 30m 토큰: 0
    # - 출력 토큰: 45
    # - 전체 토큰: 1578
    # - 측정된 비용: 0.00013956usd
    #   - 캐시되지 않은 입력 비용: 0.0003066usd
    #   - 정확한 입력 비용: 0.0008.556e-05usd
    # 지연시간: 920.8ms
    ####################################################################################################


# 선택 심화 1. 새 대화만 반영하고 변경 이력 남기기
def merge_summary(previous, turns):
    # 반환하기 위한 요약 복사
    summary = copy.deepcopy(previous)

    # 모든 대화에 대해서 처리
    for turn in turns:
        turn_id = turn["id"]
        # 이미 처리된 대화면 스킵
        if turn_id in summary["processed_ids"]:
            continue

        # 처리한 대화 기록 추가
        summary["processed_ids"].append(turn_id)

        # 단일 대화 요약 정보 추출
        turn_summary = summarize([turn])
        for name, value in turn_summary.items():
            # 정보가 이미 존재하는 경우
            if name in summary["current"]:
                # 정보가 같은 경우
                if summary["current"][name]["value"] == value["value"]:
                    # 정보의 출처 갱신
                    summary["current"][name]["source_turn_id"] = turn_id
                # 정보가 다른 경우
                else:
                    # 정보 갱신 이력 추가
                    summary["changes"].append({
                        "name": name,
                        "before": summary["current"][name]["value"],
                        "after": value["value"]
                    })
                    # 정보 갱신
                    summary["current"][name] = value
            # 정보가 없는 경우
            else:
                # 정보 추가
                summary["current"][name] = value

    return summary


if __name__ == "__main__":
    raise SystemExit(support.cli(sys.modules[__name__]))
