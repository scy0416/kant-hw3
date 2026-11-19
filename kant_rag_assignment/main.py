"""KANT NEXT DevDesk RAG. 이 파일의 빈칸만 작성하세요."""
from qdrant_client import models

import support


def todo(message):
    raise NotImplementedError(message)


# 필수 1. 문서를 저장하고 현행 자료만 검색하기
def prepare_chunks(documents):
    chunks = []
    for document in documents:
        seen = set()
        number = 0
        for paragraph in document["paragraphs"]:
            text = " ".join(paragraph.split())
            if not text or text == "KANT NEXT | 내부 문서" or text in seen:
                continue
            seen.add(text)
            chunk = {
                "document_id": document["document_id"],
                "title": document["title"],
                "category": document["category"],
                "status": document["status"],
                "source": document["source"],
                "text": text,
                "chunk_id": f"{document["document_id"]}:{number}",
            }
            chunks.append(chunk)
            number += 1
    ####################################################################################################
    # 이유: 문단을 유지하는 이유와 보존해야 할 메타데이터를 한두 줄로 적으세요.
    ####################################################################################################
    # 문단을 유지하는 이유는 한 문단을 쪼개며 의미도 같이 쪼개져 원래의 의미가 소실될 수도 있으며, 충분히 짧아서 한 청크 단위로 설정하기 적합하기 때문이다.
    # 출처를 추적하는데에 필요한 메타데이터에는 원문의 ID(document_id)와 제목(title), 주제(category), 출처 정보(source)와 핵심으로 청크 id(chunk_id)가 있어야 한다.
    ####################################################################################################
    return chunks


def build_index(chunks, embedder):
    texts = ["passage: " + row["title"] + "\n" + row["text"] for row in chunks]
    vectors = embedder.encode(texts, normalize_embeddings=True)
    client = support.empty_store(len(vectors[0]))
    points = []
    for i, (row, vector) in enumerate(zip(chunks, vectors, strict=True)):
        point = models.PointStruct(id=i, vector=vector, payload=row)
        points.append(point)
    client.upsert(collection_name="devdesk", points=points, wait=True)
    return client


def search(client, embedder, question, category, top_k=2):
    if type(top_k) is not int or not 1 <= top_k <= 5:
        raise ValueError("top_k는 1~5의 정수여야 합니다.")
    vector = embedder.encode(["query: " + question], normalize_embeddings=True)[0]
    scope = models.Filter(
        must=[
            models.FieldCondition(key="category", match=models.MatchValue(value=category)),
            models.FieldCondition(key="status", match=models.MatchValue(value="current"))
        ]
    )
    hits = client.query_points(collection_name="devdesk", query=list(vector),
                               query_filter=scope, limit=top_k, with_payload=True).points
    return [{**hit.payload, "score": hit.score} for hit in hits]


# 필수 2. 별칭 검색을 개선하고 답변을 비교하기
def rewrite_query(question, aliases):
    rewritten = question
    for alias, formal_name in aliases.items():
        rewritten = rewritten.replace(alias, formal_name)
    return rewritten


def answer_question(question, rows, generate):
    if not rows:
        return {"answer": "확인할 문서가 없습니다.", "citations": [], "needs_human": True}
    context = "\n".join([f"[{row['chunk_id']}] {row['text']}" for row in rows])
    reply = support.validate_shape(generate(question, context))
    allowed = {row["chunk_id"] for row in rows}
    if set(reply["citations"]) - allowed:
        raise ValueError("검색하지 않은 출처가 있습니다.")
    if reply["needs_human"] == bool(reply["citations"]):
        raise ValueError("답변에는 출처가 필요하며 담당자 확인에는 출처를 비웁니다.")
    return reply


def make_golden():
    given_question = {
        "question_id": "given-vpn",
        "question": "초록문을 위해서는 어느 팀에 승인을 받아야 하나요?",
        "category": "access",
        "reference_answer": "VPN 원격 접속을 사용하려면 보안팀에 승인을 요청해야 합니다.",
        "relevant_document_ids": ["vpn"],
        "required_terms": ["보안팀"],
    }
    ungiven_question = {
        "question_id": "ungiven-docker",
        "question": "docker는 무슨 버전을 사용해야하나요?",
        "category": "overseas",
        "reference_answer": "docker에 대한 자료가 없습니다.",
        "relevant_document_ids": [],
        "required_terms": [],
    }
    return [given_question, ungiven_question]


def measure(case, rows, reply):
    expected = set(case["relevant_document_ids"])
    found = {row["document_id"] for row in rows}
    recall = len(found & expected) / len(expected) if len(expected) > 0 else None
    answer_ok = (all(term in reply["answer"] for term in case["required_terms"])
                 and not reply["needs_human"]) if expected else reply["needs_human"]
    failure = "없음"
    if expected and recall < 1:
        failure = "검색 누락"
    elif not answer_ok:
        failure = "답변 확인 필요" if expected else "보류 실패"
    ####################################################################################################
    # 관측: 실제 evaluate 결과에서 개선, 악화 질문과 답변 본문을 확인해 기록합니다.
    ####################################################################################################
    # baseline에서는 document_recall이 0.66, answer_check는 0.75였다.
    # rewritten에서는 document_recall, answer_check 모두 1로 상승했다.
    # 이유는 given-vpn질문에서 발생한 것으로, 기존에는 vpn에 대한 문서가 아니라 실제 문(door)에 대한 문서가 검색되어 정답 문서가 있는 3개 중 유일하게 검색에 실패했으며,
    # 이로 인해서 답변 확인이 활성화되어 document_recall은 2/3, answer_check는 3/4가 되었다.
    # rewritten으로 별칭에 대한 처리를 한 후에는 정상적으로 검색되고, 답변에 문제가 발생하지 않아 document_recall, answer_check모두 1로 개선된 것을 확인했다.
    ####################################################################################################
    return {"document_recall": recall, "answer_check": bool(answer_ok), "failure": failure}


# 선택 심화 1. 두 검색 순위를 합쳐 근거를 모으기
def fuse_rankings(rankings, top_k=2):
    # 선택 심화: 문제의 RRF 규칙에 맞춰 직접 작성하세요.
    # top_k의 유효성 검사
    if not (1 <= top_k <= 5) or not isinstance(top_k, int):
        raise ValueError

    # 랭킹 분리
    dense, keyword = rankings

    # 청크 룩업 생성
    # chunk_lookup = {}
    # for c in dense + keyword:
    #     chunk_lookup[c["chunk_id"]] = c["text"]

    #print(chunk_lookup)
    # 각 목록의 청크 중복 제거
    seen = []
    clean_dense = []
    for c in dense:
        if c not in seen:
            seen.append(c)
            clean_dense.append({"chunk_id": c["chunk_id"], "text": c["text"]})

    seen = []
    clean_keyword = []
    for c in keyword:
        if c not in seen:
            seen.append(c)
            clean_keyword.append({"chunk_id": c["chunk_id"], "text": c["text"]})

    # 각 청크에 순위 정보 추가
    for rank, c in enumerate(clean_dense, start=1):
        c["dense"] = rank

    for rank, c in enumerate(clean_keyword, start=1):
        c["keyword"] = rank

    # dense와 keyword 병합
    merge_chunk = []
    for c in clean_dense:
        merge_chunk.append(c)

    for c in clean_keyword:
        found = False
        for mc in merge_chunk:
            if mc["chunk_id"] == c["chunk_id"]:
                found = True
                mc["keyword"] = c["keyword"]
        if not found:
            merge_chunk.append(c)

    # 각 청크의 rrf 점수 추가
    for c in merge_chunk:
        dense_rank = c.get("dense")
        c["score"] = 1 / (60 + dense_rank) if dense_rank is not None else 0

        keyword_rank = c.get("keyword")
        c["score"] += 1 / (60 + keyword_rank) if keyword_rank is not None else 0

    # score만 가진 청크 생성
    score_chunk = [{"chunk_id": c["chunk_id"], "text": c["text"], "score": c["score"]} for c in merge_chunk]

    # 정렬 후 반환
    return sorted(score_chunk, key=lambda x: (-x["score"], x["chunk_id"]))[:top_k]


if __name__ == "__main__":
    support.cli(globals())
