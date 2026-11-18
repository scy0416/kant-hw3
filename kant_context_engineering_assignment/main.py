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
    # print(items)
    # print(user_id)
    # print(now)
    #print(items)
    for item in items:
        #allowed = todo("접근 범위, 신뢰, 현행 여부와 만료 조건")
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
    #print(records, key, action, value)
    if action == "read":
        #return todo("현재 사용자의 기억 조회")
        return copy.deepcopy(records.get(key))
    if action == "create":
        if key in records:
            raise ValueError("이미 있는 기억입니다. update를 사용하세요.")
        #records[key] = todo("새 기억 저장")
        records[key] = copy.deepcopy(value)
    elif action == "update":
        if key not in records:
            raise KeyError("수정할 기억이 없습니다.")
        #records[key] = todo("기존 기억 수정")
        records[key] = copy.deepcopy(value)
    elif action == "delete":
        #return todo("현재 사용자의 기억 삭제")
        return records.pop(key) if key in records else None
    return copy.deepcopy(records[key])


def build_messages(prefix, question, context, turns, summary):
    data = json.dumps({"reference_data": context, "summary": summary}, ensure_ascii=False)
    history = [message for turn in turns for message in turn["messages"]]
    # print(data)
    # print(history)
    ####################################################################################################
    # 이유: 장기 기억과 세션 상태의 차이, 자료와 지시를 나누는 이유를 적으세요.
    ####################################################################################################
    # 장기 기억(style)은 여러 세션 전반에 거쳐 접근할 수 있는 기억이고 세션이 끝나도 사라지지 않는다.
    # 세션 상태(task)는 세션 내에서만 접근 가능하며 세션이 끝나면 세션 상태도 사라진다.
    # 지시는 LLM이 따라야 하는 사항에 대한 것이고, 자료는 지시를 수행하는데 있어 참고할 수 있는 요소이다.
    ####################################################################################################
    #return todo("고정 지시, 참고 자료, 대화, 현재 질문 순서의 메시지")
    return [
        {"role": "developer", "content": prefix},
        {"role": "user", "content": data},
        #*[{"role": h["role"], "content": h["content"]} for h in history],
        *history,
        {"role": "user", "content": question},
    ]


# 필수 2. 긴 대화를 줄이고 반복 입력 재사용하기
def summarize(turns):
    summary = {}
    for turn in turns:
        for name, value in support.fact_lines(turn["messages"][0]["content"]):
            summary[name] = todo("최신 값과 출처 턴")
    return summary


def select_window(turns, limit, reserve, margin, make_messages, count):
    support.validate_budget(limit, reserve, margin)
    budget = todo("입력에 쓸 수 있는 예산")
    if budget <= 0 or count(make_messages([])) > budget:
        raise ValueError("고정 입력만으로 예산을 넘었습니다.")
    kept = []
    for turn in reversed(turns):
        candidate = [turn, *kept]
        if todo("전체 후보 입력이 예산을 넘는지"):
            break
        kept = candidate
    # 관측: 압축 비교 후 토큰 수, 빠진 사실, 선택한 한도를 기록합니다.
    return kept


def cache_key(prefix, user_id):
    return todo("사용자와 고정 지시로 만드는 캐시 키")
    # 관측: 실제 캐시 읽기/쓰기와 비용을 확인하고 미관측이면 그대로 적습니다.


# 선택 심화 1. 새 대화만 반영하고 변경 이력 남기기
def merge_summary(previous, turns):
    return todo("선택 심화: 새 턴의 요약과 변경 이력")


if __name__ == "__main__":
    raise SystemExit(support.cli(sys.modules[__name__]))
