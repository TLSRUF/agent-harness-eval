# Claude Agent SDK (Python) 노트

출처(2026-11-03 확인):
- https://code.claude.com/docs/en/agent-sdk/python
- https://code.claude.com/docs/en/agent-sdk/permissions

패키지: `claude-agent-sdk` (import: `claude_agent_sdk`). Claude Code CLI(현재 2.1.316)를 내부에서 사용한다.
아래 내용은 문서에서 확인한 것만 적었다. "미확인" 표시는 설치 후 실제 확인해야 한다.

## 진입점
- `query(prompt=..., options=ClaudeAgentOptions(...))` : 호출마다 새 세션. `async for message in query(...)`.
- `ClaudeSDKClient` : 한 세션에서 여러 번 교환. `client.query(...)`, `client.receive_response()`, `interrupt()`, `set_permission_mode()`.
- 단발 `query()`가 오류 결과(예: 턴 제한)로 끝나면 `ResultError`가 발생한다고 문서에 있음 (필드는 미확인).

## ClaudeAgentOptions (snake_case)
| 필드 | 설명 |
| - | - |
| `allowed_tools: list[str]` | 자동 승인 목록. **사용 가능 도구를 제한하지 않는다.** 목록 밖 도구도 존재하며 권한 모드로 넘어간다 |
| `disallowed_tools: list[str]` | 베어 이름(`"Bash"`)은 도구 정의 자체를 제거. `"Bash(rm *)"`은 패턴 거부. `"*"`는 전체 제거, `"mcp__*"`는 전체 MCP 도구 제거 |
| `system_prompt` | `str` 또는 `{"type":"preset","preset":"claude_code","append":"..."}` 등 |
| `max_turns: int` | 최대 에이전트 턴 |
| `max_budget_usd: float` | 클라이언트 측 비용 추정이 이 값에 도달하면 중단 (`error_max_budget_usd`) |
| `model: str` | 별칭 또는 전체 모델명 |
| `cwd: str \| Path` | 작업 디렉터리 |
| `permission_mode` | `default`, `acceptEdits`, `plan`, `dontAsk`, `bypassPermissions`, `auto` |
| `mcp_servers: dict` | 커스텀 도구 서버 (`create_sdk_mcp_server` 결과) |
| `strict_mcp_config: bool` | True면 `.mcp.json`, 사용자 설정, 플러그인 서버 무시 |
| `setting_sources: list` | `"user"`, `"project"`, `"local"`. `[]`이면 파일시스템 설정 비활성 |
| `env: dict[str,str]` | 상속 환경 위에 병합 |
| `can_use_tool`, `hooks` | 권한 콜백, 훅(PreToolUse 등) |
| `resume`, `continue_conversation` | 세션 이어하기 |
| `include_partial_messages` | StreamEvent 수신 |

## 커스텀 도구
```python
@tool("name", "description", {"a": float})   # (name, description, input_schema, annotations=None)
async def f(args): return {"content": [{"type": "text", "text": "..."}]}
server = create_sdk_mcp_server(name="x", version="1.0.0", tools=[f])
options = ClaudeAgentOptions(mcp_servers={"x": server}, allowed_tools=["mcp__x__name"])
```
- 도구 이름 규칙: `mcp__<서버키>__<도구명>`.
- 입력 스키마: 단순 타입 맵, JSON Schema dict, TypedDict.
- 도구 오류를 모델에 알리는 방법(`is_error` 반환 여부)은 미확인.

## 권한 평가 순서 (permissions 문서)
1. hooks → 2. deny 규칙(`disallowed_tools`) → 3. ask 규칙 → 4. permission mode → 5. allow 규칙(`allowed_tools`) → 6. `can_use_tool`
- deny는 `bypassPermissions`에서도 유효하다. hook의 allow도 deny를 뚫지 못한다.
- `allowed_tools`는 `bypassPermissions`를 제한하지 못한다. 목록 밖 도구도 전부 승인된다.
- 잠금 구성: `allowed_tools=[...]` + `permission_mode="dontAsk"` → 목록 밖 호출은 거부. 단 cwd 안의 읽기, 읽기 전용 Bash 등 기본 승인 호출은 목록과 무관하게 실행된다.
- 내장 도구를 모델에게서 완전히 숨기려면 `disallowed_tools`에 베어 이름으로 넣는다.
- `acceptEdits` 자동 승인은 cwd/additionalDirectories 안에서만 적용.
- 하네스 설계 시사점: 내장 도구는 `disallowed_tools`로 숨기고, 커스텀 도구만 `allowed_tools`에 두고, `dontAsk`를 쓴다. cwd 밖 접근은 PreToolUse hook으로 추가 차단하는 방안을 Day 2에 검증한다.

## 메시지 타입
- `UserMessage`: `content`, `uuid`, `parent_tool_use_id`, `tool_use_result`, `origin`
- `AssistantMessage`: `content`(블록 리스트), `model`, `parent_tool_use_id`, `error`, `usage`, `message_id`, `stop_reason`, `session_id`, `uuid`
- 블록: `TextBlock(text)`, `ThinkingBlock(thinking, signature)`, `ToolUseBlock(id, name, input)`, `ToolResultBlock(tool_use_id, content, is_error)`, `ServerToolUseBlock`, `ServerToolResultBlock`
- 도구 오류율 계산: `ToolResultBlock.is_error`가 True인 비율 (UserMessage.content 안에 나타나는지는 실행으로 확인).

## ResultMessage (사용량/비용)
| 필드 | 설명 |
| - | - |
| `subtype` | `success`, `error_during_execution`, `error_max_turns`, `error_max_budget_usd`, `error_max_structured_output_retries` |
| `is_error` | error_* 에서 True. success여도 refusal 등에서 True 가능 |
| `num_turns` | 턴 수 |
| `duration_ms`, `duration_api_ms` | 전체/ API 시간 |
| `total_cost_usd` | 클라이언트 측 **추정치** (청구서 아님) |
| `usage` | dict: `input_tokens`, `output_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens` (메인 루프만) |
| `model_usage` | 모델별 dict, camelCase 키: `inputTokens`, `outputTokens`, `costUSD` 등 |
| `result` | 최종 텍스트 |
| `errors`, `api_error_status`, `stop_reason`, `terminal_reason` | 종료 원인 (`completed`, `max_turns`, `api_error` 등) |
| `session_id`, `permission_denials`, `uuid` | |

- 턴 제한 실패율(실험 C): `subtype == "error_max_turns"` 또는 `terminal_reason == "max_turns"`.
- 구독 로그인 환경에서 `total_cost_usd`가 채워지는지는 미확인. 비어 있으면 토큰 수와 단가표로 직접 추정한다 (Day 1에 확인).

## 인증
- 코드에서 다루지 않는다. 환경의 `claude login` 또는 `ANTHROPIC_API_KEY` 중 하나만 사용. 이 PC는 구독 로그인(`claude login`)이며 API 키는 설정하지 않는다.

## Day 1 실행으로 확인한 사항 (claude-agent-sdk 0.2.176, Python 3.12.10)
- `ClaudeAgentOptions.tools`가 있다: 기본 내장 도구 집합 지정. `tools=[]`로 내장 도구 전부 비활성 확인(스모크 통과). 그 외 `add_dirs`, `sandbox`, `fallback_model`, `max_thinking_tokens`, `effort`도 존재.
- 구독 로그인(`claude auth status`: authMethod=claude.ai)에서도 `total_cost_usd`(예: 0.0064)와 `usage`, `model_usage`가 채워진다. `model_usage[...]["costBasis"] == "list"` (정가 기준 추정).
- `usage`에는 위 4종 외에 `output_tokens_details`, `cache_creation`, `iterations` 등이 더 있다. 4종 필드 기준으로 기록하고 원본 dict도 jsonl에 저장한다.
- 커스텀 도구 결과는 `ToolResultBlock`으로 오며 성공 시 `is_error=None`(False 아님). 오류율 계산 시 `is_error is True`로 판정.
- 도구 결과 블록은 AssistantMessage가 아니라 그다음 메시지(UserMessage)의 content에 온다.
- `ResultError`는 `ProcessError`의 하위 클래스. `is_error` 결과 후 CLI가 비정상 종료할 때 `query()`가 던진다. 러너에서 try/except로 받아 기록해야 한다.
- **비용 주의**: `tools=[]`, `setting_sources=[]`인데도 1회 실행에 cache_creation 31,329 토큰이 발생했다(고정 시스템 프롬프트 오버헤드로 추정). 구독 한도 계획에 반영한다. 캐시가 재사용되는지는 Day 3 이후 반복 실행에서 확인.

## Day 2 실검증 결과 (샌드박스)
- 구성: `tools=["Read","Write","Edit","Glob","Grep"]`(Bash 등은 존재하지 않음) + `allowed_tools`(내장+커스텀) + `permission_mode="dontAsk"` + `setting_sources=[]` + PreToolUse 훅(`sandbox_hooks`).
- 훅은 `HookMatcher(matcher="Read|Write|Edit|Glob|Grep", hooks=[cb])`로 등록하고, cb는 `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": ...}}`를 반환해 거부한다. 거부되면 모델에게 `ToolResultBlock(is_error=True)`로 전달된다.
- Haiku로 3개 시나리오 실행: 내장 Read가 밖 파일을 읽기, 내장 Write가 밖에 쓰기, 커스텀 도구가 `../`로 접근하기. 모두 차단됐고 비밀 문자열 유출과 밖 파일 생성은 없었다.
- 이 검증은 훅+도구 내부 검사의 조합을 검증한 것이다. `dontAsk` 단독으로 cwd 밖 접근을 막는지는 따로 검증하지 않았다(훅이 항상 켜져 있으므로 필수 아님). 내장 도구의 경로 키는 `file_path`/`path`/`notebook_path`와 Glob의 `pattern`만 검사한다. SDK 업그레이드 시 `tests/test_sandbox_tools.py`와 `python -m src.agent.sandbox_live`를 다시 돌린다.
- 한계: 내장 `Grep`의 `glob` 인자 등 다른 키는 검사하지 않는다. Bash는 켜지 않는다.

## Day 3 실행으로 확인한 사항 (러너/로깅)
- **max_turns 도달**: `max_turns=1`에서 `ResultMessage(subtype="error_max_turns", terminal_reason="max_turns", is_error=True)`가 먼저 오고, 그 뒤 `query()`가 `ResultError`("Reached maximum number of turns (1)", exit code 1)를 던진다. 두 가지가 모두 발생하므로 러너는 ResultMessage를 기록한 뒤 예외를 잡아 `exception`으로 남긴다. 분석 시 `subtype == "error_max_turns"`로 턴 제한 실패를 센다. `exception`만으로 크래시로 분류하면 안 된다.
- **num_turns 계산**: `max_turns=1`인데 `num_turns=2`로 보고됐다(마지막 거부된 턴 포함으로 추정). 실험 C에서 턴 수 통계는 이 값을 그대로 쓰되 한계로 명시한다.
- **메시지 종류**: 스트림에는 `RateLimitEvent`, `SystemMessage`(init), `AssistantMessage`, `UserMessage`(도구 결과), `ResultMessage`가 온다. 로그에는 전부 `_type`과 함께 저장한다.
- **한도 감지(Day 7용)**: `RateLimitEvent.rate_limit_info`에 `status`("allowed" 등), `rate_limit_type`("five_hour"), `resets_at`, 그리고 `raw.unifiedWindows.five_hour.utilization` / `seven_day.utilization`(0~1)이 있다. 러너는 utilization이 임계값(예: 0.8)을 넘거나 status가 "allowed"가 아니면 멈추는 방식으로 설계할 수 있다.
- **캐시**: 한 실행 안에서는 캐시가 재사용된다(5턴 실행: cache_create 약 43k, cache_read 약 171k). 실행 간 재사용은 관찰되지 않았다(같은 과제를 2회 연속 실행했는데 둘째도 cache_create 약 42k). 과제별 임시 폴더 경로가 프롬프트 앞부분에 들어가 접두사가 달라지는 것이 원인으로 의심되나 검증하지 않았다.
- **비용 감**: 5턴 과제 1회 약 $0.010~0.011(정가 기준 추정). 40개 x 3회 베이스라인은 단순 곱으로 약 $1.3이나, 이것은 정가 환산이며 구독 한도 소모와는 다르다.

## Day 3 후속 검증 (2026-11-05, Haiku 호출 8회)

### 에이전트가 실제로 보는 도구 목록
- 출처: 초기화 `SystemMessage.data["tools"]`는 도구 **이름만** 제공한다. 설명과 입력 스키마는 이 메시지에 없다.
- **커스텀 도구**의 설명·스키마는 MCP `tools/list`로 확인했다 (아래 표). 내장 도구(Read, Grep 등)의 설명 전문과 스키마는 로그, SDK 패키지(`claude.exe` 번들), 확인한 문서 페이지에서 볼 수 없었다. 로그로 확인한 것은 호출 시 쓰인 인자 이름뿐이다 (Grep: `pattern`, `path`, `output_mode` / Write: `file_path`, `content`).
- **발견 1 (중요)**: `tools` 목록에 우리 8개 외에 **claude.ai 커넥터 MCP 도구 약 60개**(Gmail, CoinGecko, Crypto.com, Claude Docs 등)가 포함된다. `mcp_servers`에도 `source: claudeai`로 연결되어 있다. `dontAsk`라서 호출은 거부되겠지만 모델에게 노출되고 컨텍스트를 차지한다. 이는 (a) "허용 도구를 명시적으로 제한" 원칙과 CLAUDE.local.md의 "크립토 관련 내용 제외" 방침에 어긋나고 (b) 실행당 약 40k 캐시 생성 토큰의 후보 원인이다(검증 전). 해결 후보: `strict_mcp_config=True`, `disallowed_tools`에 커넥터 접두사 지정 등. **러너는 아직 바꾸지 않았다. 사용자 결정 대기.**
- **발견 2**: `{"query": str, "path": str}` 형태의 간단 스키마는 모든 항목을 `required`로 만든다. 설명은 "optionally"인데 `check_result`의 `contains`, `min_lines`, `search_text`의 `path`가 필수로 노출된다. 실제 로그에서 에이전트가 `min_lines: 1`을 채워 넣었다. 선택 항목을 쓰려면 JSON Schema dict로 `required`를 직접 지정해야 한다. 베이스라인 동결 전에 결정할 문제다.

| 구분 | 이름 | 설명(현재 default) | 입력(JSON Schema, required) |
|---|---|---|---|
| 커스텀 | search_text | Search for a text string in files under a folder. Returns matching lines as path:line:text. | query:string, path:string (둘 다 required) |
| 커스텀 | file_stats | Return line count, word count and byte size of a text file. | path:string (required) |
| 커스텀 | check_result | Check that a file exists and optionally contains a string or has a minimum line count. Returns PASS or FAIL with reasons. | path:string, contains:string, min_lines:integer (모두 required) |
| 내장 | Read, Grep, Glob, Write, Edit | 확인 불가 | 확인 불가 (Grep/Write의 관찰된 인자명만 위에 기재) |

### 캐시 원인 실험 (호출 4회, 같은 과제, 연속 실행)
- `ResultMessage.usage`는 응답 단위로 중복 제거된 합계다. `AssistantMessage.usage`는 같은 API 응답의 블록마다 값이 반복되므로 메시지별로 합하면 이중 계산된다 (같은 `message_id`로 중복 제거 필요).
- 각 실행에는 첫 요청(약 4.3k 토큰)과 두 번째 요청(약 44k 토큰 컨텍스트, 캐시 생성 약 33~41k)이 있다. 이후 턴은 약 44k를 캐시에서 읽는다.
- 첫 요청: 고정 cwd 2번째 실행은 create=0, read=4313(전부 재사용). 임시 폴더는 두 번 모두 create=379, read=3889 (cwd 경로가 들어간 약 380 토큰만 재사용 안 됨).
- 두 번째 요청(큰 블록): 고정 cwd든 임시 폴더든 매 실행 새로 생성됐다 (고정 cwd 2번째 실행도 create 33.5k + 41.1k). **임시 폴더 경로는 큰 비용의 원인이 아니다.** 큰 블록이 왜 재사용되지 않는지는 미확인이다.

### max_turns 실험 (호출 4회, 같은 과제, 정상 소요 5턴)
- 설정값 1/2/3 → 보고 `num_turns` 2/3/4, `subtype=error_max_turns`, `terminal_reason=max_turns`, `is_error=True`, 실제 API 응답 수는 1/2/3. 즉 **한계에 걸리면 num_turns = max_turns + 1** 이다. 설정값 5 → `num_turns=5`, `success`, 응답 5개.
- 예외 `ResultError`는 error_max_turns인 3건 모두에서 발생했고 success에서는 없었다.
- **max_turns=3에서 error_max_turns인데 채점은 통과**했다 (최종 답변 전에 파일 작성까지 끝남). subtype만으로 성패를 판단하면 안 된다.

### report.py 설계 메모 (턴 제한 실패 분리 집계)
- 한 실행을 (subtype, 채점 통과 여부) 두 축으로 분류한다: ① success+통과 ② success+실패(오답) ③ error_max_turns+통과(턴 제한에 걸렸지만 결과물은 정답) ④ error_max_turns+실패(턴 제한이 실패 원인) ⑤ 기타 error_* / 예외.
- 성공률은 채점 통과 기준(①+③)으로 계산하고, "턴 제한 실패율"은 ④/전체로 따로 낸다. ③은 별도 보고한다(실험 C의 핵심 신호).
- `exception`(ResultError)만으로 크래시로 분류하지 않는다. `subtype == "error_max_turns"`이면 예외를 무시하고 ③/④로 분류한다.
- 평균 턴 수는 `num_turns`를 쓰되, error_max_turns는 설정값+1로 보고됨을 표에 주석으로 달거나 `min(num_turns, max_turns)`로 보정해 병기한다.

### 구독 한도 사용률(RateLimitEvent) 관찰 (20개 이벤트, 8회+3회 실행)
- 값은 `raw.unifiedWindows.five_hour/seven_day.utilization`에 있다. SDK가 모델링한 최상위 `utilization`은 항상 None이었다.
- 해상도는 0.01 단위(소수 둘째 자리)로만 관찰됐다. 이벤트는 실행당 1~4개 나온다. 첫 실행들에서는 1개였다.
- **단조 증가가 아니다**: 같은 실행 안에서 five_hour가 0.27 → 0.28 → 0.27처럼 수 초 간격으로 오르내렸다 (노이즈 또는 서버 측 근사로 보이나 원인은 미확인).
- 이 세션의 harness 실행 11회(약 $0.1 정가 환산)가 있는 동안 five_hour는 0.19(07:28) → 0.25(07:43) → 0.28(07:45)로 움직였다. 07:28~07:43의 15분 동안 harness 호출은 없었으므로 이 변화(+0.06)는 다른 사용(이 대화 자체 등)에서 왔다. **구독 전체 사용량이라 오염된다는 가정이 관찰로 뒷받침된다.**
- 결론(관찰 범위 내): 과제 1개의 비용(약 $0.01)은 해상도(0.01)와 노이즈(±0.01) 이하라 **과제 단위 델타는 측정 불가**에 가깝다. 의미 있는 값은 수십 회 묶음의 합계 정도다. 러너는 시작/끝 스냅샷과 이벤트 전체를 기록하고(`summary.rate_limit_events`), 델타는 `ratelimit.delta()`로 사후 계산하되 참고값으로만 쓴다.

## 아직 미확인
1. 매 실행 새로 생성되는 약 40k 캐시 블록의 정체와 재사용 불가 원인 (커넥터 도구 노출이 후보)
2. utilization 노이즈의 원인, 그리고 utilization이 실제로 무엇의 비율인지 (토큰? 요청? 가중치?)
