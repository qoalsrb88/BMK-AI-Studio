# BMK AI Studio 0.9.8 베타 — Windows x64 / NVIDIA

## 실행

1. BMK-AI-Studio-0.9.8-Windows-x64-NVIDIA.zip을 다운로드합니다.
2. ZIP 전체를 새 폴더에 압축 해제합니다. 이전 버전 폴더에 덮어쓰지 마세요.
3. 폴더 안의 BMK-AI-Studio.exe를 실행합니다. _internal과 함께 두어야 합니다.

Python이나 ComfyUI를 별도로 설치할 필요가 없습니다. 이 패키지는 NVIDIA CUDA 13.0 런타임을 포함합니다. GPU 가속에는 호환되는 NVIDIA 드라이버가 필요하며, 이번 검증 장비는 Windows x64 / RTX 4090입니다. 태깅 설정에서 CPU를 선택할 수도 있습니다. 다른 GPU·드라이버 조합은 별도로 확인해야 합니다.

서명되지 않은 베타 실행 파일입니다. 실행 전 게시된 SHA256과 파일을 비교할 수 있습니다. 자동 업데이트와 서명된 설치 프로그램은 아직 제공하지 않습니다.

## 사용자 데이터와 모델

기존 앱을 정상 종료한 뒤 새 버전을 실행하세요. 기본 데이터는 %LOCALAPPDATA%/BMK-AI-Studio에 보관됩니다. 설정에서 선택한 사용자 데이터 폴더나 BMK_STUDIO_DATA, --user-directory 지정은 계속 적용됩니다. 앱 폴더 업데이트는 사용자 데이터와 외부 원본 이미지를 교체하지 않습니다.

백업할 때에는 실제 사용자 데이터 폴더, 원본 이미지 폴더, 외부 모델을 각각 보존하세요. 사용자 데이터 폴더를 별도 지정했다면 %LOCALAPPDATA%/BMK-AI-Studio-config/data-location.json도 함께 보존하면 위치 설정을 복원할 수 있습니다.

태깅·텍스트 검색 모델은 포함되지 않습니다. 앱에서 지원 모델을 내려받거나 기존 모델 폴더를 선택하세요. 모델 다운로드에 네트워크가 필요합니다. 이미지와 프롬프트는 로컬에서 처리합니다.

## 주요 기능과 변경

파일 탐색 / 이미지 라이브러리 / 노트의 독립 작업 탭, 프롬프트·태그 저장 위치 선택, 크롭과 편집 작업 보관을 제공합니다. 0.9.8은 첫 GitHub 배포 준비와 함께, Windows 축약 경로가 섞인 사용자 데이터 복사 시 작업 경로가 새 폴더로 연결되도록 수정했습니다.

PixAI, 서명된 설치 프로그램, 자동 업데이트는 미완료입니다. 의미 검색은 프롬프트·태그 텍스트 대상입니다. 파일 탐색은 원본 삭제·이동을 제공하지 않습니다.

## 라이선스와 소스

앱 소스는 MIT입니다. Qt/PySide6는 LGPLv3로 사용하며 NVIDIA 런타임과 각 외부 라이브러리에는 별도 조건이 적용됩니다. LICENSE, THIRD_PARTY_NOTICES.md, DEPENDENCY_SOURCES.md, licenses/, _internal/third_party_licenses/를 참고하세요. Qt 라이브러리를 수정하고 호환되는 DLL로 교체할 권리 및 이를 위한 역공학을 제한하지 않습니다. NVIDIA 조건은 NVIDIA 구성요소에 적용되며 Qt의 LGPL 권리를 제한하지 않습니다.

소스 및 사용 안내: https://github.com/qoalsrb88/BMK-AI-Studio
