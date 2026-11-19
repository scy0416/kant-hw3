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
        #rewritten = todo("현재 문자열에서 alias를 formal_name으로 바꾸세요.")
        rewritten = rewritten.replace(alias, formal_name)
    return rewritten


def answer_question(question, rows, generate):
    if not rows:
        return {"answer": "확인할 문서가 없습니다.", "citations": [], "needs_human": True}
    #context = todo("각 검색 결과를 [chunk_id] 본문으로 묶고 빈 줄로 연결하세요.")
    context = "\n".join([f"[{row['chunk_id']}] {row['text']}" for row in rows])
    reply = support.validate_shape(generate(question, context))
    allowed = {row["chunk_id"] for row in rows}
    #if todo("검색 결과에 없는 출처가 하나라도 있는지 검사하세요."):
    if set(reply["citations"]) - set(row["chunk_id"] for row in rows):
        raise ValueError("검색하지 않은 출처가 있습니다.")
    if reply["needs_human"] == bool(reply["citations"]):
        raise ValueError("답변에는 출처가 필요하며 담당자 확인에는 출처를 비웁니다.")
    return reply


def make_golden():
    #return todo("답이 있는 사례와 자료가 없는 사례를 하나씩 작성하세요.")
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
    #recall = todo("필요한 문서 중 찾은 비율을 계산하세요. 필요한 문서가 없으면 None입니다.")
    recall = len(found) / len(expected) if len(expected) > 0 else None
    answer_ok = (all(term in reply["answer"] for term in case["required_terms"])
                 and not reply["needs_human"]) if expected else reply["needs_human"]
    failure = "없음"
    if expected and recall < 1:
        failure = "검색 누락"
    elif not answer_ok:
        failure = "답변 확인 필요" if expected else "보류 실패"
    # 관측: 실제 evaluate 결과에서 개선, 악화 질문과 답변 본문을 확인해 기록합니다.
    return {"document_recall": recall, "answer_check": bool(answer_ok), "failure": failure}


# 선택 심화 1. 두 검색 순위를 합쳐 근거를 모으기
def fuse_rankings(rankings, top_k=2):
    # 선택 심화: 문제의 RRF 규칙에 맞춰 직접 작성하세요.
    #return todo("검색 순위 목록을 RRF 점수로 합치세요.")
    if not (1 <= top_k <= 5) or type(top_k) is bool:
        raise ValueError
    dense, keyword = rankings

    id_catalog = {**{chunk["chunk_id"]: chunk["text"] for chunk in dense}, **{chunk["chunk_id"]: chunk["text"] for chunk in keyword}}
    #print(id_catalog)

    seen = []
    proc_dense = []
    for d in dense:
        if d not in seen:
            seen.append(d)
            proc_dense.append(d["chunk_id"])

    seen = []
    proc_keyword = []
    for k in keyword:
        if k not in seen:
            seen.append(k)
            proc_keyword.append(k["chunk_id"])

    chunk_ids = set(proc_dense + proc_keyword)

    scores = {}
    for chunk_id in chunk_ids:
        scores[chunk_id] = {
            "dense": proc_dense.index(chunk_id)+1 if chunk_id in proc_dense else None,
            "keyword": proc_keyword.index(chunk_id)+1 if chunk_id in proc_keyword else None,
        }
        scores[chunk_id]["rrf"] = 0
        scores[chunk_id]["rrf"] += 1 / (60 + scores[chunk_id]["dense"]) if scores[chunk_id]["dense"] else 0
        scores[chunk_id]["rrf"] += 1 / (60 + scores[chunk_id]["keyword"]) if scores[chunk_id]["keyword"] else 0
        #scores[chunk_id]["id"] = chunk_id

    #print(scores)
    #print(sorted(scores, key=lambda item: (-item["rrf"], item["id"])))
    #print(scores.values().sort(key=lambda x: (-x["rrf"], x["id"])))
    # print(list(scores.items()))
    # print(list(scores.items()).sort(key=lambda x: (-x["rrf"], x["id"])))
    scores_list = list(scores.items())
    scores_list.sort(key=lambda x: (-x[1]["rrf"], x[0]))
    #print(scores_list)
    #print([item[0] for item in scores_list][:top_k])
    print(scores_list)
    selected_item = [(item[0], item[1]["rrf"]) for item in scores_list][:top_k]
    revoke = [{"chunk_id": item, "text": id_catalog[item], "score": score} for item, score in selected_item]
    print(revoke)
    return revoke


if __name__ == "__main__":
    support.cli(globals())
