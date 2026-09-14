# 배포 개선 진행 기록

현재 소스는 0.9.9 준비 버전입니다. GitHub에 게시된 실행 버전은 0.9.8이며, 로컬 검증 산출물을 게시된 파일과 혼동하지 마세요.

## 완료한 준비

- 배포 용량 감사 도구: scripts/audit_bundle.py. 원본 실행 폴더를 읽고 파일·출처·개인 데이터 제외 정책을 검사합니다.
- 0.9.8 NVIDIA 폴더: 3,263,255,541 bytes. PyTorch 2,924,318,485 bytes (89.61%). CUDA DLL을 임의로 제거하지 않습니다.
- 독립 CPU 환경에서 단위·Qt 검사 통과. 다른 물리 PC에서의 검증을 의미하지 않습니다.
- 서명 없는 Inno Setup 설치 빌더: scripts/build_installer.py. 깨끗한 소스 출처를 가진 패키지만 입력합니다.
- 설치 위치는 버전·CPU/NVIDIA별 새 폴더입니다. 기존 비어 있지 않은 폴더는 무인 설치에서도 거부합니다. 기존 포터블 버전과 바로가기는 변경하지 않습니다.
- 관리자 권한을 요구하지 않으며 시작 메뉴 바로가기를 생성합니다. 바탕화면 바로가기는 선택 사항입니다. 설치 화면은 현재 영어입니다.
- 0.9.8 실제 설치 후 5,023개 파일 SHA256 일치, 격리 실행 진단, 덮어쓰기 거부, 제거 후 사용자 추가 파일 보존을 검증했습니다.
- 0.9.9 설정에 수동 업데이트 확인을 추가했습니다. 베타 포함 여부와 새 버전 안내, 배포 페이지 열기를 제공합니다. 10초 네트워크 전송 제한, 응답 크기 제한, 취소를 처리합니다.
- private 저장소는 인증 없이 버전을 조회할 수 없으므로 권한 문제를 알리고 로그인된 브라우저로 안내합니다. 접근 토큰을 내장하거나 수집하지 않습니다. 자동 시작 조회·자동 설치는 없습니다.

## 재현

현재 빌드 도구는 기존 환경을 변경하지 않은 독립 CPU 환경에서도 사용할 수 있습니다. CPU torch를 설치한 뒤 torch.version.cuda가 None인지 확인합니다. 공식 의존성 설치 방법은 DEVELOPMENT.md를 참고하세요.

```powershell
python scripts/audit_bundle.py BUNDLE NEW-AUDIT.json
python scripts/probe_bundle.py BUNDLE NEW-PROBE-DIRECTORY
python scripts/build_installer.py BUNDLE NEW-INSTALLER-DIRECTORY --compiler PATH-TO-ISCC.exe
python scripts/validate_installer.py SETUP.exe BUNDLE NEW-EVIDENCE-DIRECTORY
```

검증 도구는 새로운 테스트 폴더에 실제 설치/제거를 수행합니다. 테스트 설치의 제거 후 사용자 추가 파일을 남깁니다. 기존 설치나 개인 데이터는 테스트 입력으로 지정하지 마세요. 설치 제작 도구 자체는 Inno Setup 공식 배포본과 서명을 확인해 준비하며, 해당 도구의 이용 조건을 따릅니다.

## 다음 단계와 필요한 준비

1. CPU판은 선택 가능한 경량 배포로 준비했습니다. NVIDIA판을 대체하지 않습니다.
2. 다른 물리 Windows PC와 드라이버에서 실제 사용 검증: 테스트 PC가 필요합니다. CPU 환경/격리 PATH 검사는 이를 대신하지 않습니다.
3. 코드 서명: 인증서/서비스, 게시자 신원, 예산과 안전한 서명 수단이 정해져야 실제 서명을 진행할 수 있습니다. 현재 미서명입니다.
4. 자동 다운로드·교체·복구: private 저장소 인증 방식 또는 공개 배포 채널을 결정해야 합니다. 앱 종료·새 폴더 검증·이전 버전 복귀와 데이터 구조 변경 시 복구 정책까지 함께 검증해야 합니다. 현재 구현하지 않았습니다.
5. PixAI: 기존 사용자 결정대로 보류합니다. 재개 시 공식 모델 접근 권한과 당시 이용 조건을 확인합니다.

원본 이미지·모델·노트·캐시·로컬 설정은 GitHub 업로드 대상이 아닙니다. 기존 사용자 데이터 위치는 유지합니다.

참고: [Inno Setup 비관리자 설치](https://jrsoftware.org/ishelp/topic_admininstallmode.htm), [사용자 파일 제거 주의](https://jrsoftware.org/ishelp/topic_uninstalldeletesection.htm), [GitHub Release API](https://docs.github.com/en/rest/releases/releases).


## 0.9.9 최종 로컬 배포 후보 검증

- CPU ZIP: 255,805,885 bytes. 실행 폴더 709,630,921 bytes / 4,976 파일.
- CPU 설치 파일: 223,316,041 bytes. NVIDIA 설치 파일: 2,031,587,676 bytes.
- 양쪽 설치 파일 모두 설치 후 전체 파일 SHA256 일치, 격리 실행, 기존 폴더 덮어쓰기 거부, 제거 후 사용자 추가 파일 보존 통과.
- 단위 111개 / Qt 24개 통과. 실제 CPU WD 모델에서 합성 이미지로 10,861개 점수 반환 확인. 모델 검사는 소스 CPU 환경에서 수행했습니다.
- 최종 후보의 build-info.json은 d811f4a6076aee08e265084ce0e98721498cbf88를 가리킵니다.
- 첫 CI 실패는 라이선스 줄바꿈으로 인한 dirty 체크아웃이었습니다. 문구 변경 없이 정규화했습니다. 두 번째 실패는 진단 도구의 축약 임시 경로 비교였습니다. 진단 경로를 resolve한 최종 소스와 빌드는 통과했습니다.
- [GitHub Windows 소스 검사](https://github.com/qoalsrb88/BMK-AI-Studio/actions/runs/34451520948) 성공.
- [깨끗한 Windows VM의 CPU 빌드·frozen 진단·패키지 검사](https://github.com/qoalsrb88/BMK-AI-Studio/actions/runs/34451546270) 성공. 다른 물리 PC·GPU 드라이버 조합의 실사용 검증은 별도입니다.
- 로컬 증거: validation-distribution/FINAL_VALIDATION.json. 최종 설치 폴더는 release-installer-0.9.9-cpu-verified 및 release-installer-0.9.9-nvidia-verified입니다. CPU ZIP은 release-0.9.9-cpu-verified에 있습니다.
- 소스는 비공개 GitHub에 반영했습니다. 설치 파일/CPU ZIP은 아직 Release에 게시하지 않았습니다. 기존 Standalone 바로가기와 0.9.8은 유지합니다.


## 브라우저 로그인·서명 준비 작업 — 2026-09-10

사용자는 개인 명의 코드 서명과 GitHub App 브라우저 로그인을 선택했습니다. 공개 Client ID는 소스에 설정했으며 비밀키를 내장하지 않습니다. 현재 작업은 기존 0.9.9 로컬 패키지에 포함되지 않은 소스 변경입니다.

- Qt 비동기 Device Flow와 로그인 후 인증된 Release 조회를 추가했습니다. 서버 대기 간격·slow_down·취소·응답 제한을 처리합니다.
- 선택적인 로그인 보관은 Windows DPAPI를 사용하며 이동 가능한 사용자 데이터 폴더와 분리합니다. 만료 또는 거부된 로그인은 다시 승인받습니다.
- 단위 테스트 120개와 Qt 25개 검사를 통과했습니다. 로그인 검사는 로컬 HTTP 서버와 합성 인증을 사용하며 실제 Windows 암호화 저장·다이얼로그 재열기 후 취소된 인증이 복구되지 않는 동작을 확인합니다. 실제 GitHub App의 비공개 조회는 사용자 권한 설정과 승인 대기 중입니다.
- 코드 서명 준비 코드: scripts/sign_release.py와 설치 빌더의 --signing-config 옵션입니다. 원본 번들을 보존한 복사본에 서명하고 서명·게시자·타임스탬프 확인 후 해시를 다시 계산합니다. Windows 인증서 저장소의 인증서를 선택하며 인증서 비밀키를 소스나 설정 JSON에 넣지 않습니다. 실제 인증서가 준비되지 않아 실제 서명 빌드와 서명된 설치·제거는 아직 검증하지 않았습니다.
- 다운로드 검증 기초 코드는 새 파일의 크기·SHA256·취소·기존 파일 보존 및 실행 전 게시자 서명 확인을 제공합니다. 실제 다운로드 화면과 네트워크 연결, 자동 설치·교체·복구는 아직 구현하지 않았습니다.
- GitHub의 No permissions / No repositories 화면에서 진행하는 순서는 [권한 설정 안내](UPDATE_LOGIN_SETUP.md)에 기록했습니다.

기존 실행 파일·바로가기·사용자 데이터와 원본은 이 작업으로 변경하지 않습니다. 실제 서명, 새 패키지 제작과 배포는 후속 검증이 필요합니다.
