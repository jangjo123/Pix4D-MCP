# PIX4Dmatic MCP 서버 기획서

작성일: 2026-04-17

## 1. 목표

이 프로젝트의 목표는 Codex 같은 CLI 기반 에이전트가 PIX4Dmatic을 직접 제어할 수 있도록 하는 MCP(Model Context Protocol) 서버를 만드는 것이다.

PIX4Dmatic은 현재 일반적인 데스크톱 GUI 프로그램이며, PIX4Dmapper/PIX4Dengine처럼 완전한 배치 처리용 CLI가 충분히 공개되어 있지 않다. 따라서 첫 구현은 PIX4Dmatic 내부 API를 직접 호출하는 방식이 아니라, Windows GUI 자동화 계층을 통해 PIX4Dmatic을 조작하는 방식으로 설계한다.

최종적으로는 사용자가 다음과 같이 요청하면 에이전트가 직접 PIX4Dmatic을 실행하고 처리 상태를 감시할 수 있게 하는 것이 목표다.

```text
이 이미지 폴더로 PIX4Dmatic 프로젝트를 만들고, nadir 템플릿으로 처리 시작해줘.
처리가 끝나면 품질 리포트와 orthomosaic 결과가 있는지 확인해줘.
```

## 2. 핵심 방향

전체 구조는 다음과 같다.

```text
Codex / Claude / 기타 MCP 클라이언트
  -> Pix4D MCP Server
    -> PIX4Dmatic Controller
      -> Windows UI Automation / pywinauto / AutoHotkey / PowerShell
        -> PIX4Dmatic.exe
```

MCP 서버는 에이전트가 호출할 수 있는 도구를 제공한다. 실제 PIX4Dmatic 조작은 별도의 Controller 계층이 담당한다.

처음부터 모든 PIX4Dmatic 기능을 자동화하려고 하지 않는다. 먼저 실행, 프로젝트 열기, 메뉴/단축키 조작, 스크린샷, 로그 읽기, 처리 상태 감시처럼 안정적인 저수준 도구를 만들고, 그 위에 프로젝트 생성과 배치 처리 같은 고수준 워크플로우를 올린다.

## 3. 현실적인 제약

PIX4Dmatic 자동화는 공식 API 기반이 아니므로 다음 제약이 있다.

- PIX4Dmatic UI 구조가 버전 업데이트로 바뀌면 자동화 스크립트가 깨질 수 있다.
- Windows GUI 세션이 필요하다. 완전 headless 환경에서는 안정적으로 동작하지 않을 수 있다.
- 원격 데스크톱이 잠기거나 화면 세션이 비활성화되면 클릭/키 입력 기반 자동화가 실패할 수 있다.
- UI 언어가 한국어/영어인지에 따라 버튼 텍스트 탐색이 달라진다.
- 라이선스 팝업, 업데이트 팝업, 좌표계 선택 팝업, 저장 확인 팝업 같은 예외 상황을 별도로 처리해야 한다.
- 처리 성공 여부를 UI 표시만으로 판단하면 위험하다. 로그 파일과 출력 파일 존재 여부를 함께 확인해야 한다.

따라서 운영 기준은 다음처럼 둔다.

- PIX4Dmatic UI 언어는 가능하면 English로 고정한다.
- 프로젝트와 입력 데이터 폴더 구조를 표준화한다.
- 세밀한 처리 옵션은 PIX4Dmatic 내부 processing template 또는 기존 프로젝트 복제 방식으로 관리한다.
- MCP 서버는 조작, 상태 감시, 로그 수집, 결과 검증에 집중한다.

## 4. 기술 스택 후보

### 4.1 Python MCP + pywinauto

가장 추천하는 방식이다.

장점:

- Windows GUI 자동화에 강하다.
- UI Automation, Win32 backend를 모두 사용할 수 있다.
- 창 탐색, 버튼 클릭, 키 입력, 대기, 프로세스 감시가 쉽다.
- 스크린샷과 로그 분석을 붙이기 좋다.
- PIX4Dmatic 전용 Controller 클래스를 만들기 쉽다.

단점:

- PIX4Dmatic UI 요소에 접근성 이름이 없으면 좌표 클릭이나 이미지 인식 fallback이 필요하다.
- Python 환경과 패키지 설치가 필요하다.

주요 패키지 후보:

```text
mcp
pywinauto
psutil
pillow
pydantic
rich
```

### 4.2 TypeScript MCP + PowerShell/.NET UIAutomation

MCP 서버 자체는 TypeScript로 작성하고, Windows 조작은 PowerShell 또는 .NET UIAutomation을 호출하는 방식이다.

장점:

- MCP 서버 코드 구조가 깔끔하다.
- Node.js 기반 배포와 설정이 쉽다.
- JSON 입출력 처리와 에이전트 연동이 편하다.

단점:

- GUI 자동화의 실전 편의성은 Python/pywinauto보다 떨어질 수 있다.
- 복잡한 UI 대기와 예외 처리 구현이 번거로울 수 있다.

### 4.3 AutoHotkey 보조 방식

핵심 Controller는 Python이나 TypeScript로 두고, 특정 반복 조작만 AutoHotkey 스크립트로 분리할 수 있다.

장점:

- 단축키, 메뉴 클릭, 파일 선택 창 조작이 빠르게 구현된다.
- 간단한 UI 매크로에 강하다.

단점:

- 상태 확인, 로그 분석, 구조적 오류 처리는 약하다.
- 유지보수성이 떨어질 수 있다.

권장 결론:

```text
1순위: Python MCP + pywinauto
2순위: Python MCP + pywinauto + AutoHotkey fallback
3순위: TypeScript MCP + PowerShell/.NET UIAutomation
```

## 5. 프로젝트 폴더 구조 제안

```text
Pix4D-MCP/
  README.md
  PIX4D_MCP_기획서.md
  pyproject.toml
  src/
    pix4dmatic_mcp/
      __init__.py
      server.py
      controller.py
      selectors.py
      workflows.py
      logs.py
      screenshots.py
      config.py
      errors.py
  scripts/
    inspect_ui.py
    run_server.ps1
    test_launch.py
  examples/
    job.example.json
    mcp_config.example.json
  docs/
    ui_selectors.md
    troubleshooting.md
```

각 파일 역할:

- `server.py`: MCP 도구 정의.
- `controller.py`: PIX4Dmatic 실행, 창 포커스, 클릭, 키 입력 등 실제 제어.
- `selectors.py`: 버튼, 메뉴, 창 제목, 팝업 텍스트 같은 UI selector 관리.
- `workflows.py`: 프로젝트 생성, 프로젝트 처리, 결과 확인 같은 고수준 작업.
- `logs.py`: PIX4Dmatic 로그 위치 탐색, 최근 로그 읽기, 에러/경고 분석.
- `screenshots.py`: 현재 PIX4Dmatic 창 스크린샷 저장.
- `config.py`: 실행 파일 경로, 기본 언어, timeout, 로그 경로 설정.
- `errors.py`: 자동화 실패, timeout, 팝업 감지, 처리 실패 예외 정의.

## 6. MCP 도구 설계

### 6.1 앱 실행과 세션 관리

```text
pix4d_launch(exe_path?: string) -> LaunchResult
pix4d_focus() -> FocusResult
pix4d_close(save?: boolean) -> CloseResult
pix4d_get_status() -> StatusResult
pix4d_screenshot() -> ScreenshotResult
```

역할:

- PIX4Dmatic 실행
- 이미 실행 중이면 기존 창에 연결
- 메인 창 포커스
- 현재 창 제목, 프로세스 ID, 실행 여부 확인
- 현재 화면 캡처

### 6.2 저수준 GUI 조작

```text
pix4d_send_hotkey(keys: string) -> ActionResult
pix4d_click_text(text: string, timeout_sec?: int) -> ActionResult
pix4d_click_menu(path: string[]) -> ActionResult
pix4d_wait_for_text(text: string, timeout_sec?: int) -> WaitResult
pix4d_type_text(text: string) -> ActionResult
```

역할:

- 단축키 입력
- UI 텍스트 기반 클릭
- 메뉴 경로 클릭
- 특정 텍스트가 나타날 때까지 대기
- 파일 경로 또는 설정값 입력

주의:

- 텍스트 기반 탐색이 실패하면 좌표 기반 fallback이 필요할 수 있다.
- 좌표 기반 fallback은 화면 해상도와 UI 배율에 민감하므로 마지막 수단으로만 사용한다.

### 6.3 프로젝트 조작

```text
pix4d_open_project(project_path: string) -> ProjectResult
pix4d_new_project(name: string, project_dir: string) -> ProjectResult
pix4d_import_images(image_dir: string) -> ImportResult
pix4d_import_gcp(gcp_csv_path: string) -> ImportResult
pix4d_import_marks(marks_csv_path: string) -> ImportResult
pix4d_save_project() -> ActionResult
```

역할:

- 기존 `.p4d`, `.p4s`, PIX4Dmatic 프로젝트 열기
- 새 프로젝트 생성
- 이미지 폴더 import
- GCP/marks CSV import
- 프로젝트 저장

초기 MVP에서는 `pix4d_open_project`만 먼저 구현한다. 새 프로젝트 생성과 import는 v2에서 구현한다.

### 6.4 처리 제어

```text
pix4d_set_processing_template(template_name: string) -> ActionResult
pix4d_start_processing() -> ProcessingResult
pix4d_wait_until_idle(timeout_sec: int) -> ProcessingStatus
pix4d_cancel_processing() -> ActionResult
```

역할:

- 처리 템플릿 선택
- 처리 시작
- 처리가 끝날 때까지 대기
- 실패/완료/사용자 개입 필요 상태 판단

처리 상태 판단 기준:

- PIX4Dmatic UI 상태 텍스트
- Status center 내용
- 최근 로그 파일 내용
- CPU/GPU 사용률 변화
- 출력 파일 생성 여부

### 6.5 로그와 결과 검증

```text
pix4d_read_latest_logs(lines?: int) -> LogResult
pix4d_find_log_errors() -> ErrorSummary
pix4d_check_outputs(project_dir: string, expected: string[]) -> OutputCheckResult
pix4d_collect_diagnostics(output_dir: string) -> DiagnosticsResult
```

역할:

- 최근 로그 읽기
- Error/Warning/Processing 메시지 요약
- orthomosaic, DSM, point cloud, quality report 등 결과 파일 확인
- 실패 시 로그와 스크린샷을 진단 폴더에 저장

예상 output 종류:

```text
quality_report
orthomosaic
dsm
dtm
dense_point_cloud
mesh
contour_lines
```

## 7. Job 기반 워크플로우

고수준 자동화를 위해 JSON job 파일을 사용한다.

예시:

```json
{
  "job_id": "site_001",
  "project_name": "site_001",
  "project_dir": "D:\\Pix4DJobs\\site_001",
  "image_dir": "D:\\Datasets\\site_001\\images",
  "gcp_csv": "D:\\Datasets\\site_001\\gcp.csv",
  "marks_csv": "D:\\Datasets\\site_001\\marks.csv",
  "template": "nadir",
  "expected_outputs": [
    "quality_report",
    "orthomosaic",
    "dense_point_cloud"
  ],
  "timeout_sec": 28800
}
```

MCP 도구:

```text
pix4d_run_job(job_path: string) -> JobResult
pix4d_run_job_object(job: object) -> JobResult
```

처리 흐름:

```text
1. job JSON 읽기
2. PIX4Dmatic 실행 또는 기존 세션 연결
3. 새 프로젝트 생성 또는 기존 프로젝트 열기
4. 이미지 import
5. GCP/marks import
6. processing template 적용
7. 프로젝트 저장
8. 처리 시작
9. 로그와 UI 상태 감시
10. 결과 파일 확인
11. 성공/실패 리포트 반환
```

## 8. 단계별 개발 로드맵

### MVP 1: 기본 연결과 관찰

목표:

- MCP 서버 실행
- PIX4Dmatic 실행
- 기존 PIX4Dmatic 창 연결
- 현재 상태 조회
- 스크린샷 저장
- 최근 로그 읽기

구현 도구:

```text
pix4d_launch
pix4d_focus
pix4d_get_status
pix4d_screenshot
pix4d_read_latest_logs
```

완료 기준:

- Codex가 MCP 도구 호출로 PIX4Dmatic을 실행할 수 있다.
- PIX4Dmatic 창이 열려 있는지 확인할 수 있다.
- 현재 화면 스크린샷을 파일로 저장할 수 있다.
- 최근 로그를 읽고 반환할 수 있다.

### MVP 2: 프로젝트 열기와 처리 시작

목표:

- 기존 프로젝트 파일 열기
- 메뉴/단축키 기반으로 처리 시작
- 처리 완료 여부 감시

구현 도구:

```text
pix4d_open_project
pix4d_send_hotkey
pix4d_click_menu
pix4d_start_processing
pix4d_wait_until_idle
pix4d_check_outputs
```

완료 기준:

- `.p4d` 또는 PIX4Dmatic 프로젝트 파일을 열 수 있다.
- 처리 시작 명령을 실행할 수 있다.
- timeout 전까지 처리 완료/실패를 감지할 수 있다.
- 기대 결과 파일이 생성되었는지 확인할 수 있다.

### MVP 3: 새 프로젝트 생성

목표:

- 이미지 폴더 기반 새 프로젝트 생성
- GCP/marks 파일 import
- 템플릿 선택

구현 도구:

```text
pix4d_new_project
pix4d_import_images
pix4d_import_gcp
pix4d_import_marks
pix4d_set_processing_template
pix4d_save_project
```

완료 기준:

- 표준 폴더 구조의 이미지 데이터를 import할 수 있다.
- GCP/marks CSV를 import할 수 있다.
- 처리 템플릿을 선택할 수 있다.
- 프로젝트를 저장할 수 있다.

### MVP 4: Batch Job

목표:

- 여러 job을 순차 처리
- 실패 시 다음 job으로 넘어갈지 중단할지 정책 선택
- job별 진단 리포트 생성

구현 도구:

```text
pix4d_run_job
pix4d_run_batch
pix4d_collect_diagnostics
```

완료 기준:

- 여러 프로젝트를 JSON job 목록으로 처리할 수 있다.
- 각 job의 성공/실패/경고를 요약한다.
- 실패 시 스크린샷, 로그, 상태 정보를 저장한다.

## 9. 예외 처리 설계

자동화 중 자주 발생할 수 있는 예외:

```text
PIX4Dmatic 실행 파일을 찾을 수 없음
라이선스 로그인 필요
라이선스 좌석 부족
업데이트 팝업 표시
프로젝트 파일 열기 실패
이미지 누락
카메라 모델 경고
좌표계 선택 필요
GCP CSV 형식 오류
처리 중 crash
처리 timeout
디스크 공간 부족
RAM 부족
출력 파일 미생성
```

예외 처리 원칙:

- 자동으로 처리 가능한 팝업은 명시적으로 처리한다.
- 자동 판단이 위험한 선택지는 중단하고 상태를 반환한다.
- 실패 시 반드시 스크린샷과 최근 로그를 저장한다.
- MCP 결과에는 사람이 바로 이해할 수 있는 `message`와 기계가 처리할 수 있는 `code`를 함께 반환한다.

예시:

```json
{
  "ok": false,
  "code": "LICENSE_REQUIRED",
  "message": "PIX4Dmatic license login dialog is visible.",
  "screenshot": "C:\\Users\\User\\Desktop\\Pix4D-MCP\\diagnostics\\license_required.png",
  "log_excerpt": []
}
```

## 10. 로그 탐색 전략

PIX4Dmatic 로그 위치는 버전과 설치 환경에 따라 달라질 수 있다. 우선 다음 위치를 탐색한다.

```text
C:\Users\<User>\AppData\Local\pix4d\PIX4Dmatic
C:\Users\<User>\AppData\Local\Pix4Dmatic
C:\Users\<User>\AppData\Roaming\pix4d
프로젝트 폴더 내부 log 또는 report 폴더
```

로그 parser는 다음 키워드를 우선 감지한다.

```text
[Error]
[Warning]
[Processing]
crash
failed
not enough memory
not enough disk
license
missing image
```

## 11. UI selector 관리

PIX4Dmatic UI가 버전별로 바뀔 수 있으므로 selector를 코드에 직접 박지 않고 별도 파일이나 모듈로 관리한다.

예시:

```python
MAIN_WINDOW_TITLES = [
    "PIX4Dmatic",
    "Pix4Dmatic"
]

MENU_PROCESS = [
    "Process",
    "프로세스"
]

BUTTON_START_PROCESSING = [
    "Start processing",
    "Start",
    "처리 시작"
]
```

가능하면 영어 UI 기준을 우선으로 하고, 한국어 selector는 보조로 둔다.

## 12. 보안과 안전

MCP 서버는 로컬 데스크톱 앱을 조작하므로 안전 장치가 필요하다.

원칙:

- 허용된 PIX4Dmatic 실행 파일만 실행한다.
- 임의 프로그램 실행 도구를 만들지 않는다.
- 파일 삭제 기능은 기본 제공하지 않는다.
- batch job은 명시된 프로젝트 폴더 안에서만 진단 파일을 쓴다.
- 사용자의 Pix4D 계정 비밀번호를 MCP 설정 파일에 평문 저장하지 않는다.
- 로그인 자동화는 기본 범위에서 제외한다. 필요 시 별도 보안 설계 후 추가한다.

## 13. 설정 파일 예시

```json
{
  "pix4dmatic_exe": "C:\\Program Files\\PIX4Dmatic\\PIX4Dmatic.exe",
  "ui_language": "en",
  "default_timeout_sec": 600,
  "processing_timeout_sec": 28800,
  "diagnostics_dir": "C:\\Users\\User\\Desktop\\Pix4D-MCP\\diagnostics",
  "log_search_dirs": [
    "C:\\Users\\User\\AppData\\Local\\pix4d\\PIX4Dmatic"
  ],
  "allow_coordinate_click_fallback": false
}
```

## 14. 개발 순서 상세

1. Python 프로젝트 초기화
2. MCP 서버 기본 실행 확인
3. `pix4d_launch` 구현
4. `pix4d_focus` 구현
5. `pix4d_screenshot` 구현
6. `pix4d_read_latest_logs` 구현
7. `inspect_ui.py`로 PIX4Dmatic UI tree 확인
8. `pix4d_open_project` 구현
9. 메뉴 클릭 또는 단축키 실행 도구 구현
10. 처리 시작 도구 구현
11. 처리 완료 감시 구현
12. output 검증 구현
13. job JSON 기반 workflow 구현
14. README와 사용 예시 작성

## 15. 첫 구현에서 제외할 것

초기 버전에서는 다음 기능을 제외한다.

- Pix4D 계정 로그인 자동화
- 라이선스 구매/전환 자동화
- 모든 처리 옵션의 세부 UI 매핑
- 좌표계 판단 자동 선택
- GCP 마킹 자동화
- 3D viewer 내 수동 tie point 생성 자동화
- 원격/클라우드/headless 서버 운영

이 기능들은 자동화 안정성이 낮거나, 잘못 선택했을 때 프로젝트 품질에 영향을 줄 수 있으므로 별도 단계에서 다룬다.

## 16. 성공 기준

MVP 성공 기준은 다음과 같다.

```text
Codex가 MCP 도구를 통해 PIX4Dmatic을 실행한다.
기존 프로젝트 파일을 연다.
처리 시작 명령을 수행한다.
처리가 끝날 때까지 로그 또는 UI 상태를 감시한다.
처리 결과 파일이 생성되었는지 확인한다.
실패하면 스크린샷과 로그를 남긴다.
```

이 기준을 만족하면 CLI 에이전트가 PIX4Dmatic을 직접 컨트롤한다고 볼 수 있다.

## 17. 장기 확장 방향

장기적으로는 다음 방향으로 확장할 수 있다.

- 여러 job을 처리하는 batch queue
- 작업별 품질 리포트 자동 요약
- 처리 결과를 지정 폴더로 정리
- orthomosaic, point cloud, DSM 산출물 자동 검증
- 실패 유형별 자동 재시도 정책
- PIX4Dmatic 버전별 selector profile
- 공식 API 또는 CLI가 생겼을 때 driver 교체
- 웹 대시보드 또는 로컬 TUI 추가

## 18. 결론

PIX4Dmatic을 CLI 에이전트가 직접 조종하게 만들려면 MCP 서버를 만드는 방식이 적합하다. 다만 PIX4Dmatic의 공식 자동화 API가 제한적이므로, 첫 버전은 Windows GUI 자동화 기반으로 만들어야 한다.

가장 현실적인 구현은 Python MCP 서버와 pywinauto Controller를 결합하는 방식이다. 저수준 GUI 조작 도구부터 만들고, 이후 프로젝트 생성과 batch 처리 같은 고수준 워크플로우를 쌓아가는 것이 안정적이다.

