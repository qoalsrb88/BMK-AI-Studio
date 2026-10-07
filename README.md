# BMK AI Studio

Windows용 독립 이미지·프롬프트 작업실. 현재 소스 버전 **0.9.11** (자동 업데이트 개발판), Windows 베타입니다. 별도로 검증한 로컬 설치 후보는 **0.9.10**입니다. ComfyUI 서버 없이 실행하며 사용자 원본 이미지를 덮어쓰지 않습니다.

## 기능

- **파일 탐색:** 주소창·폴더 트리·썸네일, 원본 미리보기와 메타데이터 확인.
- **이미지 라이브러리:** 등록 이미지 검색·필터·컬렉션·태깅, 프롬프트 관리와 크롭/편집.
- **노트:** 독립 프롬프트 작성·폴더·다중 문서·이력, 이미지에서 저장 위치를 골라 명시적으로 가져오기.
- 원본 프롬프트·추정 태그·작업 텍스트 구분, 로컬 WD 태깅과 다국어 텍스트 의미 검색.
- 사용자 데이터 폴더 지정, 편집 작업 보관/복구와 원본 재연결.

[사용 안내](docs/USAGE.md) · [개발/검증](docs/DEVELOPMENT.md) · [배포 준비](docs/RELEASING.md)

## 소스에서 실행

Windows x64, Python 3.12 기준입니다. PowerShell에서 프로젝트 폴더를 열고 실행하세요.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-ai.txt
.\.venv\Scripts\python.exe -m pip install torch==2.14.0 torchvision==0.29.0 --index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python.exe -m bmk_studio.app
```

위 명령은 CPU 구성이며 GPU가 없어도 사용할 수 있습니다. CUDA 구성은 [개발 안내](docs/DEVELOPMENT.md)를 참고하세요. 설치 후 `Start.cmd` 또는 콘솔 없는 `Start.vbs`로도 실행할 수 있습니다. 다른 PC의 가상환경을 그대로 복사하지 마세요.

실행 파일은 [v0.9.8 Release](https://github.com/qoalsrb88/BMK-AI-Studio/releases/tag/v0.9.8)의 `BMK-AI-Studio-0.9.8-Windows-x64-NVIDIA.zip`을 사용하세요. 소스 ZIP에는 EXE와 모델이 없습니다. 압축을 모두 풀고 EXE와 `_internal`을 포함한 폴더 전체를 유지하세요. [실행·업데이트 안내](docs/BINARY_README.md)를 참고하세요.

## 데이터와 모델

기본 데이터 위치는 `%LOCALAPPDATA%/BMK-AI-Studio`입니다. 설정에서 별도 폴더를 선택하거나 `--user-directory` 실행 옵션을 사용할 수 있습니다. 업데이트/백업 시 사용자 데이터 폴더와 외부 원본/모델을 따로 보존하세요.

모델 가중치는 저장소에 포함하지 않습니다. 앱에서 지원 모델을 다운로드하거나 기존 로컬 모델을 선택합니다. 모델 설치에는 네트워크가 필요하지만 로컬 추론을 위해 이미지·프롬프트를 업로드하지 않습니다. 모델별 이용 조건은 별도입니다.

## 검증과 제한

현재 소스 검사는 폴더 복사·업로드 제외 정책·배포 패키지 검사를 포함해 단위 테스트 130개, Qt 검사 27개입니다. 실행 파일의 GPU·압축 해제 검증 범위는 각 Release 안내에 기록합니다. [GitHub Actions 검사 결과](https://github.com/qoalsrb88/BMK-AI-Studio/actions/workflows/windows-tests.yml)는 각 커밋에서 확인할 수 있습니다. CI는 CPU·합성 데이터를 사용하며 실제 GPU/로컬 모델 검사는 별도입니다. 검증 결과가 모든 PC에서의 호환성을 보장하지는 않습니다.

설정에 GitHub 브라우저 로그인과 수동 업데이트 확인을 제공합니다. [권한 설정 안내](docs/UPDATE_LOGIN_SETUP.md)를 참고하세요. 사용자가 실제 로그인과 비공개 배포 목록 조회를 확인했습니다. Qt의 Windows HTTPS는 Schannel을 사용해 다른 프로그램의 OpenSSL DLL과 충돌하지 않도록 합니다. 0.9.11 소스에는 CPU/NVIDIA 설치 파일 다운로드·취소·SHA256 검증과, 서명 확인 후 앱 종료·데이터 백업·새 폴더 설치·실패 복구 흐름을 추가했습니다. 실제 인증서가 없어 자동 설치는 비활성 상태이며, 서명된 배포본 간 전체 업데이트는 미검증입니다. PixAI 연동은 보류합니다. 자세한 단계와 검증 범위는 [배포 개선 기록](docs/DISTRIBUTION_PROGRESS.md)을 참고하세요. 의미 검색은 프롬프트/태그 텍스트 대상이며 이미지 픽셀 CLIP 검색이 아닙니다. 파일 탐색에는 원본 삭제·이동 기능이 없습니다. 기록되지 않은 생성 프롬프트나 실제 실행 분기를 추측하지 않습니다.

## 라이선스

[MIT](LICENSE), copyright 2026 qoalsrb88. 외부 코드·라이브러리·모델에는 각각의 조건이 적용됩니다. [Third-party notices](THIRD_PARTY_NOTICES.md)를 참고하세요.
