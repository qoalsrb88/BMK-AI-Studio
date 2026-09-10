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

소스 커밋에 package/portable 또는 모델을 넣지 않습니다. GitHub의 일반 Git 파일 한도는 100 MiB이며 Release 첨부 파일은 각각 2 GiB 미만이어야 합니다. 현재 CUDA 실행 폴더는 약 3GB이므로 실제 압축 크기를 측정한 뒤 배포 형식을 결정하세요. 필요하면 검증된 CPU 패키지 또는 분할 압축을 별도로 준비하고 명확한 복원 안내를 제공합니다. 아직 압축/공개 업로드는 하지 않았습니다.

릴리스 전 확인:

- 게시할 소스 commit/tag와 실행 파일 빌드의 대응 확인. 이번 GitHub 준비는 앱 0.9.7 이후 문서/개발 설정 변경이며 자동으로 0.9.7 태그를 만들지 않습니다.
- 새 출력 폴더에 빌드하고 EXE + `_internal` 전체를 유지.
- 실제 포함된 모든 의존성/모델의 재배포 조건, 저작권 고지 및 필요한 소스 제공 요구 검토. 수집된 라이선스 목록만으로 검토 완료를 선언하지 않음.
- 개인 설정, 이미지, 노트, DB, 모델 가중치가 없는지 패키지 전체 점검.
- 격리된 경로에서 `BMK-AI-Studio.exe --self-test REPORT.json` 실행 및 실제 Windows 실행/정상 종료 확인. GPU 변경 시 해당 모델 테스트도 별도 실행.
- 최종 압축본 SHA256 기록, 압축 해제 검증, 버전/지원 환경/알려진 제한/데이터 백업 방법 포함.
- 서명되지 않은 베타임을 명시. 서명/자동 업데이트는 아직 미완료.

공식 참고: [일반 파일 한도](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github), [Release 한도](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases), [라이선스](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository).
