# BMK AI Studio 0.9.12 베타 — Windows x64

## 실행

1. https://github.com/qoalsrb88/BMK-AI-Studio/releases 에서 CPU 또는 NVIDIA ZIP을 받습니다.
2. ZIP 전체를 새 폴더에 압축 해제합니다. 기존 버전 폴더에 덮어쓰지 마세요.
3. BMK-AI-Studio.exe를 실행합니다. _internal을 포함한 폴더 전체를 함께 두세요.

Python·ComfyUI 설치와 GitHub 로그인이 필요하지 않습니다. Source code (zip)은 개발용 소스입니다. CPU판은 CPU에서 태깅하며 FP32를 사용합니다. NVIDIA판은 CUDA 런타임을 포함하며 GPU 가속에는 호환되는 NVIDIA 드라이버가 필요합니다. GPU 검증 장비는 RTX 4090이며 다른 GPU·드라이버 조합의 성능은 별도로 확인해야 합니다.

개인 개발자가 무료로 공유하는 서명 없는 배포본입니다. Windows에서 게시자 확인/보안 경고가 표시될 수 있습니다. 공식 배포 페이지에서 받은 파일인지 확인하고 SHA256SUMS.txt와 파일의 SHA256을 비교하세요. 해시는 파일 일치 확인용이며 코드 서명을 대신하지 않습니다.

## 업데이트

설정 → 업데이트 → 새 버전 확인을 누릅니다. 로그인 없이 공개 GitHub Release 목록을 조회하며 이미지·노트를 전송하지 않습니다. 새 버전이 있으면 GitHub 배포 페이지 열기를 눌러 CPU/NVIDIA ZIP을 받습니다.

기존 앱을 정상 종료하고 사용자 데이터를 백업한 뒤, 새 ZIP을 새 폴더에 풀어 실행하세요. 바로가기를 사용하면 새 EXE를 가리키도록 바꿉니다. 자동 다운로드·설치·기존 폴더 교체는 하지 않습니다. 구버전은 확인이 끝날 때까지 보관하세요.

## 사용자 데이터와 모델

기본 데이터는 %LOCALAPPDATA%/BMK-AI-Studio에 있습니다. 설정에서 선택한 사용자 데이터 폴더나 BMK_STUDIO_DATA, --user-directory 지정은 계속 적용됩니다. 무설치 실행 방식이지만 모든 데이터가 EXE 옆에 저장되는 USB 포터블 방식은 아닙니다.

백업할 때에는 실제 사용자 데이터 폴더, 외부 원본 이미지, 외부 모델을 각각 보존하세요. 사용자 데이터 위치를 변경했다면 %LOCALAPPDATA%/BMK-AI-Studio-config/data-location.json도 보존하면 위치 설정을 복원할 수 있습니다. 제거는 앱을 종료하고 압축 해제한 프로그램 폴더를 지우는 방식입니다. 사용자 데이터와 원본은 별도로 관리합니다.

태깅·텍스트 검색 모델은 포함되지 않습니다. 앱에서 지원 모델을 내려받거나 기존 모델 폴더를 선택하세요. 모델 다운로드에 네트워크가 필요합니다. 이미지와 프롬프트는 로컬에서 처리합니다.

## 기능과 제한

파일 탐색 / 이미지 라이브러리 / 노트, 프롬프트·태그 저장 위치 선택, 크롭·내보내기와 편집 작업 보관을 제공합니다. 의미 검색은 프롬프트·태그 텍스트 대상입니다. 파일 탐색은 원본 삭제·이동을 제공하지 않습니다. PixAI 연동은 보류합니다.

0.9.12는 공개 ZIP과 수동 업데이트에 맞춰 배포 화면을 단순화했습니다. 과거 비공개 로그인과 서명 기반 자동 설치는 현재 앱의 기능이 아닙니다. 정확한 검증 환경과 결과는 각 Release의 안내를 참고하세요.

## 라이선스와 소스

앱 소스는 MIT입니다. Qt/PySide6는 LGPLv3이며 NVIDIA 런타임과 외부 라이브러리는 별도 조건이 적용됩니다. LICENSE, THIRD_PARTY_NOTICES.md, DEPENDENCY_SOURCES.md, licenses/, _internal/third_party_licenses/를 참고하세요. Qt 라이브러리 수정·교체 권리와 이를 위한 역공학을 제한하지 않습니다. NVIDIA 조건은 NVIDIA 구성요소에 적용되며 Qt의 LGPL 권리를 제한하지 않습니다.

소스 및 사용 안내: https://github.com/qoalsrb88/BMK-AI-Studio
