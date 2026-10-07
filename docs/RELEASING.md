# 공개 소스와 무료 ZIP 배포

소스 저장소: [qoalsrb88/BMK-AI-Studio](https://github.com/qoalsrb88/BMK-AI-Studio). 0.9.12부터 개인·지인에게 무료로 공유하는 공개 유틸리티를 기준으로 합니다. 기본 산출물은 CPU/NVIDIA ZIP이며 유료 서명, GitHub 로그인과 자동 설치는 필수 작업이 아닙니다.

## 배포 순서

1. `python scripts/check_repository.py`와 `python scripts/validate.py`를 실행합니다. 공개 전 Git 이력도 점검하고 개인 설정·인증정보·데이터가 추적되지 않는지 확인합니다.
2. 소스 변경을 검토해 깨끗한 커밋을 만듭니다. 태그와 build-info.json의 source_commit을 일치시킵니다.
3. CPU 환경과 NVIDIA 환경에서 각각 새 출력 폴더로 빌드합니다. 기존 패키지를 덮어쓰지 않습니다.

```powershell
$env:BMK_BUILD_FOLDER='package-0.9.12-cpu'
$env:BMK_RELEASE_BUILD='1'
# CPU torch를 설치한 독립 환경의 Python을 사용합니다.
python build_windows.py
python scripts/package_release.py package-0.9.12-cpu/BMK-AI-Studio release-0.9.12/BMK-AI-Studio-0.9.12-Windows-x64-CPU.zip
```

NVIDIA판은 CUDA torch 환경에서 별도 BMK_BUILD_FOLDER를 지정하고 파일명 끝을 NVIDIA.zip으로 합니다. ZIP에는 EXE와 _internal 전체, 라이선스·사용 안내를 포함합니다. 모델은 포함하지 않습니다.

4. ZIP을 새 폴더에 풀고 manifest의 모든 SHA256을 비교합니다. 격리 데이터와 OS PATH에서 frozen 진단, native 창 실행·정상 종료를 확인합니다. CPU/NVIDIA 실제 모델 진단과 Schannel TLS 확인 결과도 기록합니다.
5. 런타임과 맞는 라이선스 고지 및 Qt/PySide 소스 아카이브를 준비합니다. 공개용 검증 요약에서 개인 경로·로그를 제외합니다.
6. GitHub 소스와 검증된 태그를 반영하고 draft prerelease에 ZIP 2종, manifest, SHA256SUMS.txt, RELEASE_VALIDATION.json, 라이브러리 소스를 첨부합니다. 업로드 크기와 SHA256이 로컬 파일과 같은지 확인합니다.
7. 사용자 합의에 따라 저장소를 공개하고 prerelease를 게시합니다. 비로그인 상태의 소스·Release 접근 및 앱의 공개 업데이트 조회를 확인합니다. 새 릴리스에서 실제 확인한 범위와 남은 실기기 검증을 명시합니다.

## 데이터와 이전 버전 보존

프로젝트 폴더 전체를 압축하거나 업로드하지 않습니다. local-settings.json, 사용자 데이터·이미지·노트·DB·캐시·모델과 검증 로그는 공개 대상이 아닙니다. Git 추적 소스와 검증된 Release 산출물만 게시합니다. 새 ZIP은 별도 폴더에서 사용하며 사용자 데이터는 앱 폴더 밖에 유지합니다.

서명 없는 베타임을 명시하고 공식 Release와 SHA256 확인 방법을 안내합니다. 유료 코드 서명이 없다는 이유로 앱 내부에서 서명 검증을 우회해 설치 파일을 실행하지 않습니다. 기본 배포 방식 자체가 수동 ZIP 실행입니다.

## 이전 개발 코드

0.9.11까지의 비공개 로그인·서명 설치 흐름과 설치/서명 빌더는 개발 참고용으로 보존합니다. legacy_update_dialog.py와 관련 검사에서만 이전 화면을 사용하며, 공개 앱은 이 화면과 설치 작업자를 호출하지 않습니다. 이 코드가 남아 있다는 사실은 실제 서명·자동 설치 검증 완료를 뜻하지 않습니다. 기록은 DISTRIBUTION_PROGRESS.md와 UPDATE_LOGIN_SETUP.md에 있습니다.

Qt 가상 키보드·PDF 플러그인과 ONNX Runtime 예제 모델은 빌드 hook에서 제외합니다. 외부 라이브러리는 자체 라이선스를 유지합니다. DEPENDENCY_SOURCES.md의 런타임 버전과 소스 해시를 실제 빌드와 맞추세요.
