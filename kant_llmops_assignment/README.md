# KANT NEXT DevDesk LLMOps 시작 안내

답변을 안전하게 기록하고 같은 질문으로 변경 전후를 비교합니다. 필수 2문제와 선택 심화 1문제이며 이전 과제의 완성 코드 없이 시작할 수 있습니다.

세 번째 과제 묶음은 RAG, Context Engineering, LLMOps입니다. 웹사이트의 04, 05, 06은 전체 과목 순서입니다.

## 환경 준비와 첫 실행

ZIP을 풀고 `main.py`와 `pyproject.toml`이 바로 보이는 폴더를 VS Code로 엽니다. Windows에서는 바탕화면처럼 경로가 짧은 위치를 사용하세요. 폴더가 깊게 중첩되면 패키지를 불러오지 못할 수 있습니다.

VS Code의 Python 확장을 설치하고 새 터미널을 엽니다. uv가 없다면 [공식 설치 안내](https://docs.astral.sh/uv/getting-started/installation/)를 따른 뒤 터미널을 새로 여세요.

```text
uv --version
uv sync --frozen
uv run --frozen python --version
uv run --frozen python main.py demo
```

Python 3.12가 표시되어야 합니다. `.python-version`이 Python 버전을 선택하며 패키지는 `pyproject.toml`과 `uv.lock`에 맞춰 설치됩니다. 버전을 바꾸거나 가상환경을 따로 활성화할 필요는 없습니다.

`demo`는 자료를 읽는 준비 확인입니다. TODO 완료를 검사하지 않습니다. 첫 실행을 확인했으면 [과제 안내](ASSIGNMENT.md)의 필수 1부터 진행하세요.



## 진행 순서

기록과 답변 검사 → 지표 계산과 변경 판단 → 실제 답변 8개와 Langfuse 확인 → FEEDBACK과 관측 주석 작성

1. [과제 안내](ASSIGNMENT.md)에서 지금 작성할 함수의 조건과 예시를 읽습니다.
2. `main.py`의 해당 TODO를 채우고 바로 아래에 안내된 명령으로 검사하고 실행합니다.
3. 결과 파일을 읽고 요구된 이유와 관측 주석을 작성한 뒤 다음 기능으로 넘어갑니다.

작성할 파일은 `main.py`와 `AI_USAGE.md`입니다. [AI 활용 기준](AI_USAGE.md)을 먼저 확인하고 사용 여부를 기록하세요. 입력 필드가 궁금할 때 [제공 자료 안내](data/DATA_CARD.md)를 찾아봅니다.

`support.py`, `checks.py`, `uv.lock`의 내부를 모두 읽거나 이해할 필요는 없습니다. `todo` 함수 자체, 지원 코드, 검사, 데이터와 환경 버전은 제공된 상태로 사용합니다.

## 실제 연결 준비

필수 2의 실제 비교 전에 개인 `.env`를 이번 폴더에 준비합니다. 기존 파일은 유지하고, 없을 때만 `.env.example`을 복사해 `.env`로 만드세요. 아래 설정을 확인합니다.

| 설정 | 값 |
|---|---|
| `OPENAI_API_KEY` | 본인의 모델 API 키 |
| `OPENAI_MODEL` | 기본값 `gpt-5.6-luna` |
| `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` | 같은 개인 프로젝트의 키 |
| `LANGFUSE_BASE_URL` | 해당 프로젝트의 지역 주소 |

`run compare --live`는 모델을 8회 호출하고 Langfuse에 기록합니다. `verify`는 기존 기록만 조회하며 모델을 추가 호출하지 않습니다. 비용은 실제 비교를 재실행할 때마다 발생합니다. 모의 실행에는 키가 필요하지 않습니다.

실제 비교 후 답변을 읽고 `main.py`의 `FEEDBACK`을 채운 뒤 `verify`를 다시 실행합니다. Trace 확인, 개선 후 재비교와 주석 작성 순서는 [과제 안내](ASSIGNMENT.md)의 필수 2를 따르세요.

## 실행이 막혔을 때

`미완료`는 남은 TODO, `실패`는 구현한 조건을 다시 확인해야 한다는 뜻입니다. 결과는 `artifacts/`에 저장됩니다. 기능 검사 파일 `checks-기능명.json`에서 항목 이름과 오류 내용을 확인하세요. 검사 항목 수는 문제 수나 점수가 아닙니다.

패키지를 불러오지 못하면 폴더 위치와 `uv sync --frozen` 실행부터 확인합니다. 뒤 문제의 빈칸을 모두 채우기 전에 앞 기능부터 검사할 수 있습니다.

인증 오류는 같은 프로젝트의 두 키와 지역 주소를 확인합니다. 429나 시간 초과는 반복 호출을 멈추고 계정의 사용량과 연결을 확인하세요. 실패 단계는 결과의 `error_stage`, 오류 종류는 `error_type`에 남습니다.

기록 확인 실패는 `verification-live.json`의 `checks`를 읽습니다. 반영 지연일 때만 잠시 뒤 `verify`를 다시 실행하며, 기록 조회를 위해 모델을 재호출하지 않습니다. 사용량 누락과 서버 값 불일치의 해석은 과제 안내의 필수 2에 있습니다.

## 제출

필수 구현, 실제 실행과 지정된 주석 작성을 마쳤다면 마지막 검사를 실행합니다.

```text
uv run --frozen python main.py check all
```

`check all`에는 선택 심화가 포함되지 않습니다. 선택 심화는 해당 문제의 명령으로 별도 확인하며, 하지 않아도 필수 제출을 완료할 수 있습니다.

과목별로 `main.py`와 `AI_USAGE.md` 두 파일만 기존 과제 제출 시스템에 제출합니다. 구현 이유와 관측 내용은 `main.py`의 지정된 주석에 짧게 남기세요. 두 파일 외의 추가 자료나 화면 캡처는 제출하지 않습니다.

제공 코드, 검사, 데이터, 환경 파일, `artifacts/`, 캐시와 `.venv/`는 제출하지 않습니다. `.env`, API 키와 개인정보는 제출물, 화면, 코드 주석과 AI 대화에 넣지 마세요.
