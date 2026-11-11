# 공개 소스와 무료 ZIP 배포

소스 저장소: [qoalsrb88/BMK-AI-Studio](https://github.com/qoalsrb88/BMK-AI-Studio). 0.9.12부터 개인·지인에게 무료로 공유하는 공개 유틸리티를 기준으로 합니다. 기본 산출물은 CPU/NVIDIA ZIP이며 유료 서명, GitHub 로그인과 자동 설치는 필수 작업이 아닙니다.

## 배포 순서

1. `python scripts/check_repository.py`와 `python scripts/validate.py`를 실행합니다. 공개 전 Git 이력도 점검하고 개인 설정·인증정보·데이터가 추적되지 않는지 확인합니다.
2. 소스 변경을 검토해 깨끗한 커밋을 만듭니다. 태그와 build-info.json의 source_commit을 일치시킵니다.
3. CPU 환경과 NVIDIA 환경에서 각각 새 출력 폴더로 빌드합니다. 기존 패키지를 덮어쓰지 않습니다.

```powershell
$env:BMK_BUILD_FOLDER='package-0.9.18-cpu'
$env:BMK_RELEASE_BUILD='1'
# CPU torch를 설치한 독립 환경의 Python을 사용합니다.
python build_windows.py
python scripts/package_release.py package-0.9.18-cpu/BMK-AI-Studio release-0.9.18/BMK-AI-Studio-0.9.18-Windows-x64-CPU.zip
```

NVIDIA판은 CUDA torch 환경에서 별도 BMK_BUILD_FOLDER를 지정하고 파일명 끝을 NVIDIA.zip으로 합니다. ZIP에는 EXE와 _internal 전체, 라이선스·사용 안내를 포함합니다. 모델은 포함하지 않습니다.

4. ZIP을 새 폴더에 풀고 manifest의 모든 SHA256을 비교합니다. 격리 데이터와 OS PATH에서 frozen 진단, native 창 실행·정상 종료를 확인합니다. CPU/NVIDIA 실제 모델 진단과 Schannel TLS 확인 결과도 기록합니다.
5. 런타임과 맞는 라이선스 고지 및 Qt/PySide 소스 아카이브를 준비합니다. 공개용 검증 요약에서 개인 경로·로그를 제외합니다.
6. GitHub 소스와 검증된 태그를 반영하고 draft prerelease에 ZIP 2종, manifest, SHA256SUMS.txt, RELEASE_VALIDATION.json, 라이브러리 소스를 첨부합니다. 업로드 크기와 SHA256이 로컬 파일과 같은지 확인합니다.
7. 사용자 합의에 따라 저장소를 공개하고 prerelease를 게시합니다. 비로그인 상태의 소스·Release 접근 및 앱의 공개 업데이트 조회를 확인합니다. 새 릴리스에서 실제 확인한 범위와 남은 실기기 검증을 명시합니다.
8. 게시와 공개 확인이 끝나면 아래 **배포 뒤 이전 버전 로컬 산출물 정리**에 따라 개발 PC의 이전 버전 폴더를 삭제대기 폴더로 옮깁니다.

## 배포 뒤 이전 버전 로컬 산출물 정리

새 버전을 게시하고 비로그인 공개 확인까지 통과하면, 개발 PC에 남은 이전 버전의 로컬 산출물을 **지우지 않고 삭제대기 폴더로 옮깁니다.** 배포 절차의 마지막 단계이며, 따로 묻지 않고 진행한 뒤 옮긴 목록과 위치를 보고합니다(2026-11-11 사용자 결정).

- **조건:** 새 Release가 게시되어 자산 해시와 비로그인 접근 확인을 통과했고, 새 `release-<버전>/`에 Qt/PySide 소스 아카이브가, 새 `validation-<버전>/`에 배포 스크립트가 있으며, 옮길 폴더의 EXE로 실행 중인 앱이 없어야 합니다. 배포가 중단됐거나 검증에 실패했으면 아무것도 옮기지 않습니다.
- **옮기는 것:** 이전 버전의 `portable/BMK-AI-Studio-<이전 버전>-*`, `release-<이전 버전>/`, `validation-<이전 버전>/`, 이번 빌드를 포함한 `package-<버전>-*`, `build/windows-*` 작업 폴더.
- **남기는 것:** `.venv`, `build/cpu-env`, 새 버전의 `portable/` 폴더(CPU·NVIDIA), 새 `release-<버전>/`와 `validation-<버전>/`, `.backups/`, 사용자 데이터와 개발 프로필, 그리고 위 목록에 없는 폴더와 파일.
- **바로가기가 가리키는 폴더는 옮기지 않습니다.** 실사용 바로가기(프로젝트 폴더와 작업 표시줄 고정)를 새 EXE로 바꾸는 일은 사용자 확인을 받고 합니다. 바로가기가 아직 이전 EXE를 가리키면 그 `portable` 폴더는 남기고, 전환한 뒤 옮깁니다. 바꾸기 전의 바로가기 파일도 덮어쓰지 않고 삭제대기 폴더에 남깁니다.
- **방법:** 같은 드라이브의 `_삭제대기/<날짜_시각>/` 아래로 원래 경로 구조를 살려 옮기고 이동 기록을 남깁니다(개발 PC의 삭제대기 이동 스크립트 사용). 먼저 모의 실행으로 옮길 위치를 확인합니다. `rm`·`Remove-Item` 같은 영구 삭제는 쓰지 않으며 삭제대기 폴더는 비우지 않습니다. 비우는 것은 사용자가 직접 합니다.
- **범위 밖:** GitHub의 이전 Release와 태그는 그대로 둡니다. 끝난 작업의 worktree와 브랜치 정리는 `AGENTS.md`의 브랜치 기준을 따르는 별도 작업입니다.

## 데이터와 이전 버전 보존

프로젝트 폴더 전체를 압축하거나 업로드하지 않습니다. local-settings.json, 사용자 데이터·이미지·노트·DB·캐시·모델과 검증 로그는 공개 대상이 아닙니다. Git 추적 소스와 검증된 Release 산출물만 게시합니다. 새 ZIP은 별도 폴더에서 사용하며 사용자 데이터는 앱 폴더 밖에 유지합니다.

서명 없는 베타임을 명시하고 공식 Release와 SHA256 확인 방법을 안내합니다. 유료 코드 서명이 없다는 이유로 앱 내부에서 서명 검증을 우회해 설치 파일을 실행하지 않습니다. 기본 배포 방식 자체가 수동 ZIP 실행입니다.

## 이전 개발 코드

0.9.11까지의 비공개 로그인·서명 설치 흐름과 설치/서명 빌더는 개발 참고용으로 보존합니다. legacy_update_dialog.py와 관련 검사에서만 이전 화면을 사용하며, 공개 앱은 이 화면과 설치 작업자를 호출하지 않습니다. 이 코드가 남아 있다는 사실은 실제 서명·자동 설치 검증 완료를 뜻하지 않습니다. 기록은 DISTRIBUTION_PROGRESS.md와 UPDATE_LOGIN_SETUP.md에 있습니다.

Qt 가상 키보드·PDF 플러그인과 ONNX Runtime 예제 모델은 빌드 hook에서 제외합니다. 외부 라이브러리는 자체 라이선스를 유지합니다. DEPENDENCY_SOURCES.md의 런타임 버전과 소스 해시를 실제 빌드와 맞추세요.
