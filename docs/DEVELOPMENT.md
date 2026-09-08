# 개발과 검증

Windows x64 / Python 3.12 기준입니다. README의 CPU 설치 명령을 먼저 실행하세요. 런타임 기본 의존성은 requirements.txt, AI 의존성은 requirements-ai.txt, 패키징 의존성은 requirements-build.txt에 있습니다.

`requirements-lock.txt`는 기존 CUDA 개발 환경의 전체 기록입니다. 일반 설치/CPU CI에 그대로 적용하지 마세요. GPU 구성이 필요하면 기존 CPU torch/torchvision을 제거한 별도 가상환경에서 호환되는 두 패키지를 함께 설치하세요. 로컬 검증 환경은 torch 2.14.0+cu130 / torchvision 0.29.0+cu130이었으며 드라이버와 GPU 호환성은 별도로 확인해야 합니다. 공식 선택기: https://pytorch.org/get-started/locally/

```powershell
.\.venv\Scripts\python.exe scripts/check_repository.py
.\.venv\Scripts\python.exe scripts/validate.py
```

validate.py는 unit 및 23개 Qt smoke를 실행합니다. 합성 이미지와 임시 데이터 폴더를 사용합니다. 태깅 변경 시에는 tests의 선택적 로컬 모델/GPU smoke도 실행하고 모델·GPU·정밀도를 기록하세요. 자동 모델 다운로드나 실제 사용자 데이터 업로드를 CI에 추가하지 마세요.

GitHub Actions는 Windows + CPU 의존성을 설치합니다. 외부 action은 확인한 전체 commit SHA로 고정했고, 권한은 contents: read입니다. fork PR에서 비밀값이나 배포 권한을 사용하는 작업은 없습니다. 초기 GitHub 실행은 저장소 생성 후 확인해야 합니다.

## 저장소 경계

.gitignore는 루트 허용 목록과 데이터/바이너리 제외 규칙을 함께 사용합니다. 새 루트 파일/폴더는 명시적으로 허용해야 합니다. 원본 이미지·모델·노트·DB·개인 설정·바로가기·빌드 및 검증 산출물은 제외됩니다. 기존 로컬 감사 문서도 공개 소스에 포함하지 않습니다.

check_repository.py는 후보 또는 `--staged` Git index를 검사합니다. 경로/텍스트 형식/크기 및 일부 토큰·개인 경로 패턴을 검사하며 내용 대신 위치만 보고합니다. 모든 비밀정보를 찾아내는 도구는 아니므로 최초 게시 전에 staged diff를 직접 확인하세요. 이미 커밋한 파일은 .gitignore 추가만으로 제거되지 않습니다.

## 빌드

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
$env:BMK_BUILD_FOLDER='package-release'
.\.venv\Scripts\python.exe build_windows.py
```

패키지는 개발 환경의 의존성을 포함합니다. CUDA 환경에서 빌드하면 용량이 커집니다. 다른 환경에서 빌드한 패키지는 별도로 검증해야 합니다. 모델과 사용자 데이터는 포함하지 마세요. 출시 전 단계는 RELEASING.md를 참고하세요.
