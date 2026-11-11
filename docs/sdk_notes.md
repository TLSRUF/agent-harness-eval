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
- **발견 1 (중요)**: `tools` 목록에 우리 8개 외에 **claude.ai 커넥터 MCP 도구 약 60개**(메일, 시세, 문서 등 외부 서비스 연동)가 포함된다. `mcp_servers`에도 `source: claudeai`로 연결되어 있다. `dontAsk`라서 호출은 거부되겠지만 모델에게 노출되고 컨텍스트를 차지한다. 이는 (a) "허용 도구를 명시적으로 제한" 원칙과 CLAUDE.local.md의 "크립토 관련 내용 제외" 방침에 어긋나고 (b) 실행당 약 40k 캐시 생성 토큰의 후보 원인이다(검증 전). 해결 후보: `strict_mcp_config=True`, `disallowed_tools`에 커넥터 접두사 지정 등. **러너는 아직 바꾸지 않았다. 사용자 결정 대기.**
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

## 커넥터 노출 확인 (2026-11-05, Haiku 호출 3회) — 위 "발견 1" 정정 포함
- **정정**: 위 "발견 1"의 "tools 목록에 커넥터 약 60개"는 14회 실행 중 **첫 실행 1회**의 init 메시지에서만 나타났다(68개 도구, 서버 10개). 나머지 13회는 init에 우리 8개(커스텀 3 + 내장 5)와 서버 `t` 1개만 보였다. init의 `tools`는 에이전트가 보는 도구의 신뢰할 수 있는 목록이 아니다(문서: 캐시된 도구 목록을 가진 원격 서버는 첫 호출 때 연결되고 init에는 빠질 수 있음, tool search 기본 켜짐).
- **접근성 확인**: init에 커넥터가 없던 실행에서 에이전트에게 읽기 전용 커넥터 도구 1개(`mcp__claude_ai_<서비스>__<도구>` 형식)의 호출을 시켰더니 "unavailable"이 아니라 `Permission ... has been denied because Claude Code is running in don't ask mode`(is_error=True)로 거부됐다. 즉 커넥터 도구는 CLI에 등록되어 호출 시도까지 가능하고, `dontAsk`가 실행을 막고 있다. 호출이 실행된 적은 없다(검증 범위: 이 도구 1개).
- **차단 방법(공식 문서 확인)**: 환경변수 `ENABLE_CLAUDEAI_MCP_SERVERS=false` ("has the same effect for the current shell session") 또는 설정 `disableClaudeAiConnectors: true`. SDK에서는 `ClaudeAgentOptions(env={"ENABLE_CLAUDEAI_MCP_SERVERS": "false"})`로 시험했다. 레포 설정에는 아직 적용하지 않았다(사용자 확인 대기).
- **차단 효과(같은 데모 과제)**: 차단 전 13회는 캐시 생성 합계 약 41k 또는 약 75k(두 블록), 비용 $0.0085~$0.0165. 차단 후 2회는 합계 1,044/1,059 토큰, 비용 $0.0008/$0.0008, 요청별 create는 130~380 수준이며 큰 블록이 사라졌다. 따라서 **약 40k 블록과 그 중복 생성은 커넥터 노출 때문**이라는 가설이 강하게 지지된다(블록 내용을 직접 열어 확인한 것은 아님: 가설).
- 위 "아직 미확인 1번"(큰 블록의 정체)은 가설 수준으로 좁혀졌다. 차단은 비용을 약 10~20배 줄이므로 Day 8 베이스라인 예상 비용과 한도 계획에 직접 영향이 있다.
- 부수 관찰(표본 작음): 데모 과제의 ERROR 검색 도구 선택은 차단 전 11회 모두 Grep(11/11), 차단 후 2회는 search_text 1회·Grep 1회였다. 차단이 선택에 영향을 주는지는 이 표본(N=1개 과제, 2회)으로는 알 수 없다.

## 베이스라인 도구 정의 v1 (2026-11-05 확정)

**규칙: 베이스라인(Day 8) 이후에는 아래 도구 정의(이름, 설명, 입력 스키마)를 바꾸지 않는다.** 실험 A에서 바꾸는 것은 `DESCRIPTIONS`의 별도 설명 버전(config의 `tool_desc_version`)뿐이며, 이름과 스키마는 고정이다. 이번 수정은 베이스라인 전에만 허용되는 정의 오류 수정이었다: `check_result`의 `contains`, `min_lines`와 `search_text`의 `path`가 설명과 달리 required였던 것을 선택 항목으로 바꿨다(구현은 이미 기본값을 처리했다).

| 이름(SDK 부여 이름) | 설명 (tool_desc_version=default) | 입력 스키마 (JSON Schema) |
|---|---|---|
| `mcp__t__search_text` | Search for a text string in files under a folder. Returns matching lines as path:line:text. | properties: query:string, path:string / **required: [query]** (path 생략 시 ".") |
| `mcp__t__file_stats` | Return line count, word count and byte size of a text file. | properties: path:string / **required: [path]** |
| `mcp__t__check_result` | Check that a file exists and optionally contains a string or has a minimum line count. Returns PASS or FAIL with reasons. | properties: path:string, contains:string, min_lines:integer / **required: [path]** |

- 코드 위치: `src/agent/tools.py`의 `DESCRIPTIONS`, `SCHEMAS`. `tests/test_tool_definitions.py`가 서버의 `tools/list` 결과가 이 정의와 일치하는지, 선택 항목을 생략한 호출이 되는지 검사한다.
- 내장 도구(Read, Write, Edit, Glob, Grep)의 설명 전문과 스키마는 확인 불가(설정 가능한 값도 아님).
- **에이전트 환경 (v1의 일부, 베이스라인 이후 변경 금지)**: 커넥터 차단 `env={"ENABLE_CLAUDEAI_MCP_SERVERS": "false"}` (`runner_agent.HARNESS_ENV`, 모든 실행에 적용).
- **런타임 가드 (v1의 일부)**: (1) 매 실행 init 메시지의 도구 이름이 허용 목록(커스텀 3 + 내장 5 = 8개)에 없는 이름을 포함하면 실행을 중단하고 `ToolGuardError`를 낸다(`src/agent/guard.py`, `run_task`). 각 jsonl 첫 줄(`config`)에 허용 목록의 정렬 sha256과 개수, 이어서 `tool_guard` 이벤트에 관찰된 목록의 sha256/개수/통과 여부를 기록한다. (2) **init 목록만으로는 커넥터 노출을 못 잡는다**(차단 전에도 14회 중 13회 init이 8개였다). 그래서 배치 시작 전 `preflight_check()`가 `get_mcp_status()`로 서버가 `t`뿐인지 확인하고 `get_context_usage()`의 "MCP tools" 토큰을 기록한다(모델 호출 없음). preflight는 Day 7 러너에서 배치 시작 시 호출하도록 연결해야 한다(현재는 함수와 수동 실행만 있음).
- 위 설정과 가드는 베이스라인(Day 8) 이후 바꾸지 않는다. 바꾸면 모든 실험의 기준이 달라진다.

## 도구 이름 형식과 종류 판정
- jsonl에는 SDK가 부여한 이름을 그대로 저장한다. 실제 로그에서 확인한 형식: 커스텀 `mcp__t__<도구명>` (서버 키가 `t`), 내장은 `Read`, `Write`, `Edit`, `Glob`, `Grep` 그대로, 커넥터는 `mcp__claude_ai_<서비스>__<도구명>`.
- 종류 판정은 `src/agent/tools.py`의 `classify_tool(name)` 한 곳만 쓴다: 접두사 `mcp__t__`이면 `custom`, 내장 5개 이름이면 `builtin`, 그 외는 `other`. `report.py`도 이 함수를 쓴다.

## report.py 지표 정의 (구현: src/eval/report.py)
- 커스텀 도구 선택률 = (overlap_with가 있는 과제에서, 그 과제의 overlap 쌍에 적힌 커스텀 도구를 한 번이라도 호출한 실행 수) / (그 과제들의 전체 실행 수). 쌍별 값(예: search_text 대 Grep)도 따로 계산하고 "커스텀만/내장만/둘 다/둘 다 아님" 건수를 병기한다. 쌍에 없는 커스텀 도구(예: check_result)의 사용은 선택률에 넣지 않는다.
- 성공률 = 채점 통과 실행 수(success+통과, error_max_turns+통과) / 채점된 실행 수. 선택률과 별도 줄에 보고하고 합치지 않는다.
- 성패 분류: (subtype, 채점) 5범주 + 채점이 없는 실행용 "채점 없음". 표본 크기 문구 `N=…, 과제당 M회 / 총 K건`은 `sample_label()`이 데이터에서 세어 만든다. 선택률 계산 실행이 30건 미만이면 "표본이 작아 해석에 주의"가 붙는다. 그래프 제목용은 `chart_title()`.
- 과제 정의의 overlap_with는 `{"과제id": ["search_text|Grep", ...]}` 형식으로 `--overlap`에 전달한다(Day 4에서 과제 로더가 연결).

## 커넥터 노출 측정 (2026-11-05, `get_mcp_status` / `get_context_usage`, 모델 호출 없음)
| | 연결된 서버 | MCP 도구 토큰 | 합계 컨텍스트 |
|---|---|---|---|
| 차단 안 함 | claude.ai 커넥터 9개(연결됨 5, needs-auth 4) + `t` | 44,688 | 49,357 |
| 차단함(HARNESS_ENV) | `t` 1개 | 122 | 3,338 |
- 확인됨: 차단하지 않으면 커넥터 도구 정의가 약 44.7k 토큰을 차지하고, 차단하면 사라진다. 일부 도구는 `isLoaded: false`(지연 로딩)로 표시된다.
- 가능성 높음(직접 확인은 아님): 매 실행 새로 만들어지던 약 40k 캐시 블록이 이 커넥터 도구 정의다(크기가 근접하고 차단 시 사라짐).
- 확인 불가: 큰 블록이 어떤 실행에서 두 번 만들어졌던 메커니즘. 차단 후 5회에서는 0회 나타났다.

## 아직 미확인
1. 매 실행 새로 생성되는 약 40k 캐시 블록의 정체와 재사용 불가 원인 (커넥터 도구 노출이 후보)
2. utilization 노이즈의 원인, 그리고 utilization이 실제로 무엇의 비율인지 (토큰? 요청? 가중치?)

## RateLimitEvent status 값과 한도 신호 (Day 7, 2026-11-10)
- 출처: 설치된 SDK 0.2.176 소스(`claude_agent_sdk/types.py`)의 `RateLimitStatus = Literal["allowed", "allowed_warning", "rejected"]`와 docstring(allowed=한도 내, allowed_warning=한도에 가까움, rejected=한도 도달). 공식 문서 웹페이지에서 값 목록을 따로 확인하지는 못했다(문서 확인 불가). 근거는 타입 정의뿐이며 이 목록이 전부라는 보장은 없다. `rate_limit_type`은 five_hour, seven_day, seven_day_opus, seven_day_sonnet, overage. docstring은 utilization을 "0.0~1.0 비율"이라고 하지만, 이 계정에서는 최상위 utilization이 항상 None이었고 값은 `raw.unifiedWindows`에 있었으며 단위는 **미확인**이다. 지금까지 관찰된 status는 "allowed"뿐이다.
- 값별 처리(배치 러너 `src/eval/batch.py`의 현재 가설): `allowed` 계속. `allowed_warning`, `rejected`, 그 밖의 모든 문자열 값은 그 실행을 마친 뒤 다음 실행 전에 멈추고 이어하기 방법을 출력한다. status가 없는(None) 이벤트는 판단하지 않는다. five_hour 임계값은 별개로, 설정했을 때만 적용한다(기본 없음).
- 제안(미구현): `allowed_warning`은 임계값 정책과 분리해, 사용자가 "경고에서도 계속" 옵션으로 정하게 할 수 있다. `rejected`는 실행이 결과 없이 끝나면 "중단된 실행"이 되어 재시작 때 다시 실행된다. `resets_at`(유닉스 시각, 의미는 가설)은 멈출 때 출력만 한다.
- 모델 호출 없이 five_hour를 읽는 방법: **찾지 못했다(확인 불가).** `ClaudeSDKClient`의 `get_server_info`, `get_context_usage`, `get_mcp_status`에는 한도 필드가 없다. `get_server_info`에는 `claude_code_version`과 계정 정보(이메일 포함)가 있어 로그에 저장하지 않는다. CLI 슬래시 명령 `/usage`("Show session cost, plan usage, and what's contributing to your limits")가 있으나 사람이 화면으로 보는 용도이고, 그 숫자가 `unifiedWindows.utilization`과 같은 값인지는 확인되지 않았다. 그래서 배치 시작/끝 값은 1턴 탐침 호출(기본 켜짐)이나 수동 인자(`--start-five-hour`, `--start-seven-day`)로 얻는다.
- CLI 버전: SDK는 번들 CLI를 쓴다. `get_server_info()["claude_code_version"]`과 init 메시지가 둘 다 2.1.316이고, PATH의 `claude`는 2.1.322로 다르다. 재현성 필드 `repro.cli_version`에는 번들 CLI의 `--version`을 기록한다.
- 탐침 호출(`probe_*` 파일): Haiku 5.5, 도구 없음(`tools=[]`, `allowed_tools=[]`), max_turns 1, HARNESS_ENV 적용, 설정 파일 불러오기 없음. 베이스라인 결과와 이어하기 감지에 섞이지 않는 별도 이름이다.


## num_turns의 의미와 max_turns 20 (2026-11-11, 모델 호출 없음, 기존 로그 분석)

### 관찰 (day7check 5건, 로그에서 직접 센 값)
| 실행 | 고유 message_id 수 | tool_use 블록 수 | 도구 결과(UserMessage) 수 | 보고된 num_turns | 한 AssistantMessage 안 tool_use 2개 이상 | 한 message_id 아래 tool_use 분포(id 수) |
|---|---|---|---|---|---|---|
| H01 | 5 | 13 | 13 | 14 | 0건 | 0개 1, 1개 3, 10개 1 |
| H02 | 7 | 17 | 17 | 18 | 0건 | 0개 1, 1개 5, 12개 1 |
| H04 | 8 | 16 | 16 | 17 | 0건 | 0개 1, 1개 6, 10개 1 |
| H05 | 6 | 15 | 15 | 16 | 0건 | 0개 1, 1개 3, 6개 2 |
| H07 | 8 | 9 | 9 | 10 | 0건 | 0개 1, 1개 5, 2개 2 |
- 5건 모두 **num_turns = tool_use 블록 수 + 1**(5/5). 고유 message_id 수 + 1과는 한 건도 맞지 않는다(0/5).
- SDK는 한 API 응답(같은 message_id)의 블록을 블록마다 별도 AssistantMessage로 쪼개 기록한다. 그래서 "한 AssistantMessage 안에 tool_use가 2개 이상"은 0건이지만, **같은 message_id 아래 병렬 호출은 5건 모두에 있었다**(한 응답에 최대 12개: H02). 병렬 호출이 있던 응답 수: H01 1, H02 1, H04 1, H05 2, H07 2.
- 도구 호출 수와 도구 결과 수가 모든 실행에서 같아서, "tool_use 블록 수 + 1"과 "도구 결과 메시지 수 + 1"은 이 데이터로 구분되지 않는다.

### 가설 (확정 아님)
- H1: num_turns = 모델 응답(고유 message_id) 수 (+1은 한계 도달 때만). **day7check로 기각**(H01: 응답 5, num_turns 14).
- H2: num_turns = 도구 호출(tool_use 블록) 수 + 1. day7check 5건과 아래 Day 3 로그 전부와 모순 없음.
- H3: num_turns = 도구 결과 메시지 수 + 1 (H2와 데이터상 구분 불가).
- 확인 불가: SDK/CLI 내부에서 "턴"을 세는 규칙(번들 CLI 소스를 읽지 않았고 문서에서 정의를 찾지 못함).

### Day 3 max_turns 실험과의 모순 검토 (maxturns_* 4건 + day3demo/day4check/day7smoke 로그 7건, 같은 방법으로 다시 셈)
| 설정 max_turns | 보고 num_turns | subtype | 고유 message_id 수 | tool_use 수 |
|---|---|---|---|---|
| 1 | 2 | error_max_turns | 1 | 1 |
| 2 | 3 | error_max_turns | 2 | 2 |
| 3 | 4 | error_max_turns | 3 | 3 |
| 5 | 5 | success | 5 | 4 |
- 이 실험의 모든 응답에는 tool_use가 1개뿐이라(병렬 호출 없음) 응답 수와 호출 수가 같거나 1 차이였다. 그래서 **Day 3 데이터만으로는 H1과 H2를 구분할 수 없었다**. H1을 쓰려면 "한계에 걸리면 응답 수+1, 성공이면 응답 수"라는 예외 규칙이 필요하다. H2는 규칙 하나(호출 수 + 1)로 4건 모두와 day7check 5건, 나머지 로그 7건(E01 3+1, E11 1+1, E13 2+1, 데모 4+1 등)을 설명한다. 따라서 Day 3과 모순되지 않는다. 기존 문장 "한계에 걸리면 num_turns = max_turns + 1"은 H2에서는 "호출 수가 max_turns에 도달했으니 호출 수 + 1 = max_turns + 1"이라는 같은 현상의 한 경우다.
- 한계 판정 규칙(관찰, 가설): max_turns=5에서 호출 4번 뒤 최종 답변이 나와 success(num_turns 5)였고, max_turns=3에서 호출 3번째에 error_max_turns(num_turns 4)였다. 즉 "num_turns가 max_turns를 넘으면 중단"으로 읽힌다(호출 수 + 1 > max_turns). 이 읽기는 설정 4개, 호출이 한 개씩인 경우의 관찰뿐이다.

### max_turns 20의 의미와 H02, H04에 주는 영향
- H2가 맞다면 max_turns 20은 "모델 응답 20번"이 아니라 **도구 호출 약 19번(호출 수 + 1 <= 20)**까지 허용하는 값이다. 병렬 호출은 응답이 아니라 호출마다 센다. 같은 한도에서 한 응답에 도구를 10개 내는 실행은 한 번에 10을 쓴다.
- 관찰된 호출 수: H02 17(num_turns 18), H04 16(17), H05 15(16), H01 13(14), H07 9(10). H02는 한도까지 호출 2~3번, H04는 3~4번 남았다. 호출 수/min_steps 비는 1.15~1.33이었다. min_steps가 11~13인 과제는 6개(히스토그램: 11이 3개, 12가 1개, 13이 2개)이고, 이 비가 1.5 가까이 되면 19호출 근처가 된다(단순 곱, 가설). 따라서 **error_max_turns가 나올 가능성이 있는 과제는 min_steps 11 이상의 과제들**이다. 실제로 나올지는 베이스라인 전에는 확인 불가.
- 확인 불가: 병렬 호출 한 응답이 한도를 한 번에 넘길 때 CLI가 어디서 중단하는지(응답 단위 검사인지 호출 단위 검사인지). 관찰된 병렬 응답은 모두 한도에서 멀었다(최대 18).
- 영향 정리: ① 베이스라인은 max_turns 20을 바꾸지 않는다(config 기본값). ② error_max_turns가 나오면 `maxturns_fail`/`maxturns_pass`로 따로 집계된다. ③ Day 13(최대 턴 5/20)을 해석할 때 5는 "응답 5번"이 아니라 "도구 호출 약 4번"일 수 있다는 점을 명시한다. ④ 한도 판정 단위를 확인하려면 모델 호출이 필요하다(예: 병렬 호출이 많은 H02에 낮은 max_turns를 주고 중단 지점을 보는 시험). 사용자 승인 없이 하지 않았고 계획에만 둔다.

### 한계 (한 줄 요약)
- num_turns와 max_turns는 모델 응답 수가 아니라 도구 호출 수 기준으로 보이며(가설, day7check 5건과 Day 3 실험에서 num_turns = 도구 호출 수 + 1), max_turns=20은 도구 호출 약 19번까지를 뜻한다. 한 응답 안의 병렬 호출은 호출마다 센다.
