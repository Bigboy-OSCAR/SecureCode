### 8.6 같은 질문에서 좋아진 사례와 나빠진 사례

아래는 **1회차의 실제 응답**이다. H만 R0보다 맞힌 경우와, R0만 H보다 맞힌 경우를 각각 질문 ID 순서상 첫 사례로 골랐다. 전체 평균을 대표하는 예시는 아니며, 같은 자료를 적게 보낸다고 정답이 자동으로 유지되지는 않는다는 점을 보여 준다.

| 실제 질문 | 기준 답 | B의 답 / 총 입력 | R0의 답 / 총 입력 | H의 답 / 총 입력 |
|---|---|---|---|---|
| `cache_ttl(-1, False)`의 반환값은? | `0` | `30` 오답 / 478 | `300` 오답 / 1145 | `0` 정답 / 868 |
| `authorize`가 직접 호출하는 프로젝트 함수들을 정렬해서 나열하라 | `role_allows`, `scope_allows`, `session_valid` | 세 함수 모두 정답 / 791 | 세 함수 모두 정답 / 1154 | `session_valid`를 빠뜨림 / 927 |

첫 사례에서 H의 선택용 LLM은 `{"read":[1]}`을 반환했다. 프로그램이 목록 1번 `cache_ttl`의 원문만 읽어 보내자, 답변용 원문은 **87토큰**이었다. R0의 원문은 **1,021토큰**이었다. 하지만 H에는 계산에 참조되는 상수의 **이름만 있고 값은 없었다.** 사전에 지정한 원문 4개 중 함수 1개만 포함해 지표는 25%였다. H가 정답을 출력했다는 사실만으로 필요한 근거를 충분히 확보했다거나, 짧은 입력이 정답의 원인이라고 해석할 수는 없다.

두 번째 사례에서도 H는 목록 1번 `authorize`만 읽었다. 아래 코드는 **실제 H 입력에 들어 있던 내용**으로, 세 함수의 호출이 모두 나타난다.

```python
from policy import ALLOW_REASON, DENY_REASON
from rules import session_valid, role_allows, scope_allows
def authorize(user, owner, role, scopes, action, created_at, now, revoked):
    if not session_valid(created_at, now, revoked):
        return {"allowed": False, "reason": "session"}
    granted = role_allows(role, owner, user) and scope_allows(scopes, action)
    return {"allowed": granted, "reason": ALLOW_REASON if granted else DENY_REASON}
```

H의 원문은 122토큰으로 R0의 1,017토큰보다 짧았고, 이 질문의 기준 원문인 `authorize`도 포함했다. 그런데 답변 LLM은 보이는 `session_valid`를 목록에서 빠뜨렸다. **이 오답을 ‘필요한 원문이 없어서’라고 설명하면 틀린다.** 정답 여부는 최종 답변까지 확인해야 한다. [두 사례의 목록·선택·입력·답변 기록](evidence/hybrid_index_20261027/report_examples.json)에서 대조할 수 있다.

