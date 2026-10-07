# GitHub 게시와 실행 파일 배포

소스 저장소: [qoalsrb88/BMK-AI-Studio](https://github.com/qoalsrb88/BMK-AI-Studio). 첫 게시 시 비공개(private)로 설정했습니다.

## 처음 게시하기

1. 공개(public)/비공개(private)를 결정하고 빈 저장소를 만듭니다. 로컬 소스가 이미 있으므로 웹에서 README/.gitignore/LICENSE를 따로 생성하지 않습니다.
2. 로컬 origin 주소, 작성자 이름/비공개 이메일, staged diff를 확인합니다. 계정 비밀번호나 토큰을 소스/remote URL에 넣지 마세요.
3. `python scripts/check_repository.py --staged`와 `python scripts/validate.py`를 실행합니다.
4. 첫 로컬 커밋을 확인하고, 게시가 결정되면 `git push -u origin main`을 실행합니다. GitHub 로그인은 Git Credential Manager 또는 사용자가 설정한 인증 방식으로 합니다.
5. 첫 Actions 실행 결과를 확인합니다. Settings에서 main의 force push/삭제 제한, 변경 검토와 상태 검사, 보안 취약점 비공개 신고를 필요에 맞게 설정합니다. 실제 제공 옵션은 계정/저장소 유형에 따라 확인하세요.

공개 저장소는 다른 사용자가 복제/포크할 수 있습니다. MIT 적용 범위와 외부 코드 권한을 확인한 뒤 공개하세요.

## 실행 파일은 별도 Release

소스 커밋에 package/portable 또는 모델을 넣지 않습니다. GitHub의 일반 Git 파일 한도는 100 MiB이며 Release 첨부 파일은 각각 2 GiB 미만이어야 합니다. 현재 CUDA 실행 폴더는 약 3GB이므로 실제 압축 크기를 측정한 뒤 배포 형식을 결정하세요. 필요하면 검증된 CPU 패키지 또는 분할 압축을 별도로 준비하고 명확한 복원 안내를 제공합니다. 0.9.8 배포 절차는 아래와 같습니다.

릴리스 전 확인:

- 게시할 소스 commit/tag와 실행 파일 빌드의 대응 확인. 태그는 검증된 깨끗한 커밋에 붙이고, build-info.json의 source_commit과 일치해야 합니다.
- 새 출력 폴더에 빌드하고 EXE + `_internal` 전체를 유지.
- 실제 포함된 모든 의존성/모델의 재배포 조건, 저작권 고지 및 필요한 소스 제공 요구 검토. 수집된 라이선스 목록만으로 검토 완료를 선언하지 않음.
- 개인 설정, 이미지, 노트, DB, 모델 가중치가 없는지 패키지 전체 점검.
- 격리된 경로에서 `BMK-AI-Studio.exe --self-test REPORT.json` 실행 및 실제 Windows 실행/정상 종료 확인. GPU 변경 시 해당 모델 테스트도 별도 실행.
- 최종 압축본 SHA256 기록, 압축 해제 검증, 버전/지원 환경/알려진 제한/데이터 백업 방법 포함.
- 서명되지 않은 베타임을 명시. 서명/자동 업데이트는 아직 미완료.

공식 참고: [일반 파일 한도](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github), [Release 한도](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases), [라이선스](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository).

## 0.9.8 배포 재현

1. docs/licenses의 고지와 DEPENDENCY_SOURCES.md가 실제 런타임 버전과 일치하는지 확인합니다.
2. 소스 검사·단위·Qt 검사를 실행하고 변경을 커밋합니다.
3. PowerShell에서 아래처럼 새 폴더에 빌드합니다. 기존 패키지는 덮어쓰지 않습니다.

```powershell
$env:BMK_BUILD_FOLDER='package-0.9.8'
$env:BMK_RELEASE_BUILD='1'
.\.venv\Scripts\python.exe build_windows.py
.\.venv\Scripts\python.exe scripts/package_release.py package-0.9.8/BMK-AI-Studio release-0.9.8/BMK-AI-Studio-0.9.8-Windows-x64-NVIDIA.zip
```

4. ZIP을 새 폴더에 풀고 manifest의 모든 SHA256을 비교합니다. 격리된 사용자 데이터로 --self-test, 실제 모델 GPU 진단, native 창 시작·정상 종료를 실행합니다.
5. 공식 해시가 일치하는 Qt/PySide 소스 아카이브를 같은 Release의 별도 첨부로 제공합니다. 앱 실행에는 필요하지 않습니다.
6. 검증된 커밋의 태그로 draft prerelease를 만들고 ZIP, manifest, SHA256SUMS.txt, 라이브러리 소스와 검증 요약을 첨부합니다. 업로드된 asset 크기·SHA256 확인 후 prerelease로 게시합니다. 저장소 공개 여부는 변경하지 않습니다.

실제 코드 서명과 서명된 버전 간 자동 업데이트 검증은 미완료입니다. 0.9.11의 자동 업데이트 소스와 모의 검증 범위는 DISTRIBUTION_PROGRESS.md에 기록합니다. Qt 가상 키보드·PDF 플러그인과 ONNX Runtime 예제 모델은 빌드 hook에서 제외합니다.

## 개인 명의 코드 서명 준비

GitHub 로그인과 별도 절차입니다. 사용자가 선택한 방향은 개인 명의 서명이며, 신청·결제·본인 확인은 사용자가 진행합니다.

1. 기존 신청 여부 확인: 발급 업체 계정이나 이메일에서 Code Signing / 코드 서명 주문·본인 확인·발급 완료 내역을 확인합니다. 이 PC의 Windows 인증서 저장소에 없더라도 클라우드 서비스나 외부 토큰에 발급되어 있을 수 있습니다.
2. 미신청이면 개인 명의 및 거주 국가 발급을 지원하는 상품인지 업체에 확인한 뒤 신청합니다. 법인 전용 상품은 개인 명의 선택과 맞지 않습니다. 발급·키 보관 방식과 SignTool 연동 방법을 확인하세요.
3. 발급 안내에 따라 본인 확인과 토큰/서명 클라이언트 설정을 완료합니다. 개인키·PIN·계정 비밀번호를 저장소나 채팅에 넣지 않습니다. 업체명과 발급 상태만 공유하면 연결 작업을 이어갈 수 있습니다.
4. 개발자는 서명 수단을 연결하고 앱·설치 파일·제거 도구를 서명한 뒤 게시자와 타임스탬프, 최종 파일 해시를 검증합니다. 현재 scripts/sign_release.py는 Windows 사용자 인증서 저장소 + SignTool 방식을 지원합니다. 클라우드 전용 방식이면 해당 서비스 연결이 추가로 필요합니다.
5. bmk_studio/update_config.py의 SIGNING_THUMBPRINT를 실제 발급된 인증서 지문으로 설정하고 새 빌드를 만듭니다. 고정된 게시자 지문이 없는 기존 미서명 빌드에서는 자동 설치를 허용하지 않습니다. 최초 전환은 수동 설치가 필요합니다.

서명 설정 JSON에는 signtool 실행 파일 경로, certificate_thumbprint, HTTPS timestamp_url만 기록합니다. 비밀키를 포함하지 않습니다. 서명은 원본 번들의 새 복사본에 적용하며, 기존 미서명 파일도 보존합니다. 실제 개인키 사용이 필요한 단계는 발급 수단 준비 후 진행합니다.

공식 참고: [Microsoft SignTool 서명·검증·타임스탬프](https://learn.microsoft.com/en-us/windows-hardware/drivers/devtest/signtool).
