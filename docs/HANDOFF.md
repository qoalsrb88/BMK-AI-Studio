# BMK AI Studio 유지보수와 개선 개발 핸드오프

기준일: 2026-10-07. BMK AI Studio는 **0.9.12를 1차 실사용 가능한 공개 베타로 배포**했습니다. 이후에는 개선 스펙이나 버그가 생길 때마다 별도 세션에서 한 가지 작업을 진행합니다. 새 세션은 이 문서를 출발점으로 삼되 실제 Git 상태와 사용자의 최신 요청을 먼저 확인하세요.

## 현재 제품 방향과 완료 상태

- Windows용 독립 이미지·프롬프트 유틸리티입니다. ComfyUI 서버를 실행하거나 앱에서 가져오지 않습니다.
- [공개 저장소](https://github.com/qoalsrb88/BMK-AI-Studio)와 [0.9.12 Release](https://github.com/qoalsrb88/BMK-AI-Studio/releases/tag/v0.9.12)에 소스와 무료 CPU/NVIDIA ZIP을 제공합니다.
- 기본 사용 방식은 ZIP 전체 압축 해제 후 EXE 실행입니다. 모델 가중치는 별도 설치합니다.
- 업데이트는 로그인 없는 버전 확인 → GitHub 배포 페이지 → 새 ZIP을 새 폴더에 풀어 실행하는 방식입니다.
- **유료 코드 서명, GitHub App 로그인, 자동 다운로드·설치는 현재 필수 개발 과제가 아닙니다.** 이전 관련 소스는 참고용이며 공개 앱에서 호출하지 않습니다. 과거 문서의 미완료 서명 계획을 현재 할 일로 되살리지 마세요.
- 파일 탐색, 이미지 라이브러리, 노트 작성·저장, 크롭·내보내기, 로컬 태깅과 데이터 위치 지정이 구현되어 있습니다. 현재 기능과 제한은 [README](../README.md)를 기준으로 확인합니다.
- PixAI 연동은 보류입니다. 의미 검색은 프롬프트·태그 텍스트 대상이며 이미지 픽셀 CLIP 검색은 구현 범위가 아닙니다. 원본 파일 삭제·이동도 현재 탐색 기능에 없습니다.

배포 0.9.12의 소스 기준은 `bab0945`입니다. 이후 `5fbb589`에서 개발 실행기와 유지보수 안내를 추가했습니다. 이 문서 및 유지보수 변경이 main에 반영되어도 이미 배포된 EXE와 태그가 자동으로 바뀌지는 않습니다. 최신 작업 위치는 고정 커밋 대신 `git status`, `git log`, 원격 main으로 확인하세요.

## 개발과 실사용의 구분

현재 개발 PC는 기존 `H:\BMK-AI-Studio`를 유지합니다. 같은 PC에서 개발을 이어가기 위해 다시 clone할 필요는 없습니다. 다른 PC에서 처음 시작할 때는 clone 후 [개발 안내](DEVELOPMENT.md)에 따라 Python 환경을 별도로 설치합니다.

| 용도 | 실행 대상 | 데이터 |
| --- | --- | --- |
| 일상 사용 | 검증된 Release ZIP의 `BMK-AI-Studio.exe` | 사용자가 설정한 기존 데이터 폴더 |
| 개발 테스트 | `.venv/Scripts/pythonw.exe` + `scripts/launch_dev.pyw` | `%LOCALAPPDATA%/BMK-AI-Studio-dev` |
| 자동 회귀 검사 | `scripts/validate.py` | 각 검사의 합성 데이터·임시 폴더 |

현재 PC의 `BMK AI Studio.lnk`와 `BMK AI Studio (Standalone).lnk`는 `portable/BMK-AI-Studio-0.9.12-NVIDIA/BMK-AI-Studio.exe`를 가리킵니다. `BMK AI Studio (개발 테스트).lnk`는 개발 실행기를 가리킵니다. 로컬 바로가기, portable 폴더, 이전 바로가기 백업은 Git에 포함하지 않으므로 다른 PC에는 자동 생성되지 않습니다.

개발 실행 명령:

```powershell
.\.venv\Scripts\python.exe scripts/launch_dev.pyw
```

개발 프로필은 처음에 비어 있으며 이후 계속 유지됩니다. 실사용 노트·설정·이미지는 복사하지 않습니다. 모델이 필요하면 개발 앱에서 기존 로컬 모델 폴더를 선택합니다. 일반 `Start.cmd`, `Start.vbs`, `launch.pyw`는 실사용 데이터 설정을 사용하는 소스 실행기이므로 개발 테스트에는 전용 실행기를 사용하세요.

실사용 데이터 위치는 기본적으로 `%LOCALAPPDATA%/BMK-AI-Studio`이며, 별도 위치 설정은 `%LOCALAPPDATA%/BMK-AI-Studio-config/data-location.json`에 있습니다. `--user-directory`와 `BMK_STUDIO_DATA`도 위치를 지정할 수 있습니다. 개인 데이터의 실제 절대 경로를 공개 문서에 옮기지 말고 필요한 경우 해당 PC에서 확인합니다. **소스를 다른 폴더에 clone하는 것만으로 데이터가 분리되지는 않습니다.**

## 새 세션에서 시작하는 순서

1. `AGENTS.md`, 이 문서, 요청 기능에 관련된 코드·문서만 읽습니다. 사용자에게 이미 확인한 요구를 반복해서 묻지 않습니다.
2. `git status --short --branch`, `git branch -vv`, `git worktree list`로 기존 변경과 다른 작업을 확인합니다. 다른 세션의 변경을 덮어쓰거나 임의로 정리하지 않습니다.
3. 작업 트리가 깨끗하고 같은 체크아웃에서 다른 세션이 작업하지 않을 때 main을 갱신하고 작업별 브랜치를 만듭니다.

```powershell
git switch main
git pull --ff-only origin main
git switch -c codex/short-task-name
```

`short-task-name`은 실제 작업 이름으로 바꿉니다. `--ff-only`가 실패하면 분기된 변경부터 확인하며 강제 reset/push로 해결하지 않습니다. 기존 작업을 이어가는 요청이면 새 브랜치를 무조건 만들지 말고 해당 작업 브랜치를 확인합니다.

4. 요청한 한 가지 스펙을 구현하고 개발 전용 데이터로 확인합니다. 관련 없는 리팩터링·의존성 변경·기능 확대는 섞지 않습니다.
5. 필요한 검증을 마치고 변경 내용·결과·미완료 사항을 보고합니다. 소스 커밋·원격 반영과 EXE 빌드·배포는 별도 단계로 구분합니다.

**한 작업 세션이 끝난 뒤 다음 세션을 시작하는 순차 작업을 기본으로 합니다.** 여러 세션을 동시에 진행해야 한다면 같은 폴더에서 브랜치를 바꾸며 작업하지 말고 별도 worktree와 각각의 테스트 데이터·실행 환경을 사용합니다. 단순히 세션만 나누어도 파일은 같은 폴더를 공유할 수 있습니다.

## 변경 중 유지할 원칙

- 원본 이미지를 덮어쓰지 않고 원본 메타데이터·추정 태그·작업 프롬프트를 구분합니다. 없는 원본 프롬프트를 만들어내지 않습니다.
- 사용자 노트의 알 수 없는 필드, 기존 데이터·설정과 이전 배포본을 보존합니다. 데이터 이전 작업은 별도 범위와 검증이 필요합니다.
- 모델 추론·이미지 처리는 UI를 막지 않도록 처리하며, 선택 이미지가 바뀐 뒤 오래된 결과가 적용되지 않게 합니다.
- 모델·노트·이미지·DB·캐시·로그·인증정보·`local-settings.json`은 GitHub에 업로드하지 않습니다. `.gitignore`가 이미 추적 중인 파일까지 자동으로 제거해주지는 않습니다.
- Windows HTTPS는 Schannel을 사용합니다. 과거 OpenSSL DLL 충돌 문제를 피하도록 한 초기화 경로를 유지합니다.
- 기존 구조와 의존성을 유지하는 가장 작은 충분한 변경을 우선하고 `AGENTS.md`의 검증 규칙을 따릅니다.

## 검증과 완료 기준

```powershell
.\.venv\Scripts\python.exe scripts/check_repository.py
.\.venv\Scripts\python.exe scripts/validate.py
git diff --check
```

이 시점의 회귀 검사는 단위 130개와 Qt 27개이며 모두 통과했습니다. 개발 실행기는 실제 pythonw 환경에서 창 표시·정상 종료, 개발 프로필 선택, 기존 데이터 위치 설정 보존을 확인했습니다. 검사 수는 후속 변경으로 달라질 수 있으므로 실제 출력이 기준입니다.

태깅을 변경하면 관련 단위 검사와 선택적 로컬 모델/GPU 검사도 실행합니다. 모델·장치·정밀도를 기록하고 동일 이미지의 캐시 응답을 새 추론 속도로 기록하지 않습니다. `tests/smoke_gpu.py`는 합성 테스트 이미지와 로컬 모델 경로를 인자로 받습니다. 기존 검증이 이미 변경을 검출할 수 있으면 같은 내용을 반복하는 테스트를 추가하지 않습니다.

EXE를 새로 배포할 때는 소스 검사만으로 완료하지 않습니다. 새 폴더 빌드, 데이터 제외 검사, ZIP 압축 해제 후 해시, 격리 실행·정상 종료, 필요한 실제 모델 검증을 진행합니다. `build-info.json`과 배포 태그의 소스가 일치해야 합니다. [배포 절차](RELEASING.md)와 [의존성 소스 제공](DEPENDENCY_SOURCES.md)을 따르며 기존 0.9.12 Release를 다른 내용으로 덮어쓰지 않습니다.

## 실사용 검증과 성능 참고

개발 PC RTX 4090에서 0.9.12 CPU/NVIDIA 실행 파일의 실제 WD EVA02 Large v3 태깅을 확인했습니다. 각각 `cpu`와 `cuda`에서 10,861개 점수를 반환했습니다. 공개 버전 조회와 ZIP 다운로드는 비로그인 상태에서도 확인했습니다.

사용자는 별도 노트북(Core i7-1165G7, RAM 8GB, GTX 1650 Ti 4GB)에서 설치·실행·종료·열기·탐색·노트 작성/저장·크롭·내보내기·태깅이 정상이라고 보고했습니다. 후속 NVIDIA판 실사용에서 약 1MP 이미지(832×1216, 1024×1024)에 대해 다음 시간을 보고했습니다.

| 조건 | 사용자 실측 |
| --- | --- |
| 완전 최초 로딩·태깅 | 20~30초 |
| 이후 태깅 | 1초 근소 미만 |
| 메모리 해제 후 첫 로딩·태깅 | 약 5초 |
| 이후 태깅 | 동일하게 1초 근소 미만 |

이는 사용자 관찰이며 통제된 벤치마크나 노트북 장치 로그 수집 결과는 아닙니다. FP32 최초 로딩이 BF16보다 약간 느리게 느껴졌다는 보고도 있지만 실행 순서·파일 캐시를 통제하지 않았습니다. 현재 모델은 FP32로 로드하고 추론 시 혼합 정밀도를 적용하므로 이 차이만으로 BF16 로딩 우위를 단정하지 않습니다. 새 이미지 추론과 캐시 응답, 최초 로딩과 반복 추론을 구분하세요. 이 기록을 이유로 별도의 성능 최적화를 자동 착수하지 않습니다.

## 관련 코드와 자료

| 작업 분야 | 먼저 확인할 위치 |
| --- | --- |
| 메인 UI와 작업 탭 | `bmk_studio/app.py`, `main_tabs.py`, 관련 Qt smoke |
| 파일 탐색과 라이브러리 | `disk_browser.py`, `library.py`, `library_disk.py`, `library_view.py` |
| 노트와 데이터 저장 | `core.py`, `note_fields.py`, `note_transfer.py`, `workspace.py` |
| 크롭과 편집 복원 | `crop_ui.py`, `sessions.py`, `relink.py`, `data_location.py` |
| 태깅과 모델 | `tagger.py`, `batch.py`, `background.py`, `model_download.py` |
| 공개 업데이트 확인 | `updates.py`, `update_dialog.py`, `update_network.py` |
| 패키징과 배포 | `build_windows.py`, `scripts/package_release.py`, `scripts/probe_bundle.py` |

위 파일명은 별도 표시가 없으면 `bmk_studio/` 기준입니다. `legacy_update_dialog.py`와 이전 서명·설치 모듈은 현재 공개 업데이트 화면으로 연결하지 않습니다.

상세 사용법은 [USAGE](USAGE.md), 환경·실행은 [DEVELOPMENT](DEVELOPMENT.md), 변경 이력은 [DISTRIBUTION_PROGRESS](DISTRIBUTION_PROGRESS.md)를 참고합니다. 로컬의 `validation-0.9.12/`, `validation-maintenance/`, `.backups/`에는 당시 검사·바로가기 백업이 있으나 Git 복제본에는 포함되지 않습니다. 공개 검증 요약은 Release의 `RELEASE_VALIDATION.json`에 있으며 게시 당시 결과입니다. 이 세션에서 수집한 개인 경로 포함 로그를 통째로 공개하지 마세요.

## 새 세션 시작용 요청문

```text
BMK AI Studio 유지보수 작업입니다.
프로젝트의 AGENTS.md와 docs/HANDOFF.md를 먼저 확인해 주세요.
현재 Git 상태와 기존 변경을 확인하고, 이번 스펙 한 가지를 작업별 브랜치에서 진행해 주세요.
개발 전용 실행기를 사용하고 원본 이미지와 실사용 데이터를 보존해 주세요.

이번 작업:
- 현재 문제 또는 개선 목적:
- 원하는 동작:
- 완료 기준:
- 재현 절차 또는 참고 자료:
- 이번에 원하는 범위: 소스 수정 / GitHub 반영 / 새 EXE 배포

요청 범위 안에서 구현과 필요한 검증을 진행하고,
완료한 변경, 검증 결과, 커밋·업로드 상태와 남은 작업을 알려주세요.
```

실제 변경 후에는 영향을 받은 안내와 이 문서의 현재 상태만 갱신합니다. 대화 전체를 새 문서로 계속 복제하거나 이미 완료한 배포 준비를 반복하지 않습니다.
