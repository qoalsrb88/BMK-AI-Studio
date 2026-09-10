# BMK AI Studio

Windows용 독립 이미지·프롬프트 작업실. 현재 소스 버전 **0.9.7**, 로컬 베타입니다. ComfyUI 서버 없이 실행하며 사용자 원본 이미지를 덮어쓰지 않습니다.

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

공개 실행 파일 릴리스는 아직 제공하지 않습니다. 소스 ZIP에 EXE와 모델이 포함되어 있다고 가정하지 마세요. 추후 실행 파일 배포 시에는 EXE와 `_internal`을 포함한 폴더 전체를 함께 사용해야 합니다.

## 데이터와 모델

기본 데이터 위치는 `%LOCALAPPDATA%/BMK-AI-Studio`입니다. 설정에서 별도 폴더를 선택하거나 `--user-directory` 실행 옵션을 사용할 수 있습니다. 업데이트/백업 시 사용자 데이터 폴더와 외부 원본/모델을 따로 보존하세요.

모델 가중치는 저장소에 포함하지 않습니다. 앱에서 지원 모델을 다운로드하거나 기존 로컬 모델을 선택합니다. 모델 설치에는 네트워크가 필요하지만 로컬 추론을 위해 이미지·프롬프트를 업로드하지 않습니다. 모델별 이용 조건은 별도입니다.

## 검증과 제한

0.9.7 앱은 로컬 Windows 환경에서 단위 테스트 104개, Qt 검사 23개 및 패키지 실행을 검증했습니다. 현재 소스 검사는 폴더 복사 회귀 검사와 업로드 제외 정책 검사를 포함해 단위 테스트 107개, Qt 검사 23개입니다. [GitHub Actions 검사 결과](https://github.com/qoalsrb88/BMK-AI-Studio/actions/workflows/windows-tests.yml)는 각 커밋에서 확인할 수 있습니다. CI는 CPU·합성 데이터를 사용하며 실제 GPU/로컬 모델 검사는 별도입니다. 검증 결과가 모든 PC에서의 호환성을 보장하지는 않습니다.

PixAI 연동, 서명된 설치 프로그램 및 자동 업데이트는 미완료입니다. 의미 검색은 프롬프트/태그 텍스트 대상이며 이미지 픽셀 CLIP 검색이 아닙니다. 파일 탐색에는 원본 삭제·이동 기능이 없습니다. 기록되지 않은 생성 프롬프트나 실제 실행 분기를 추측하지 않습니다.

## 라이선스

[MIT](LICENSE), copyright 2026 qoalsrb88. 외부 코드·라이브러리·모델에는 각각의 조건이 적용됩니다. [Third-party notices](THIRD_PARTY_NOTICES.md)를 참고하세요.
