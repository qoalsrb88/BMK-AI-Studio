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


## 0.9.9 로컬 배포 후보 검증

- CPU ZIP: 255,805,689 bytes, 실행 폴더 709,633,287 bytes / 4,976 파일.
- CPU 설치 파일: 223,316,135 bytes. 실제 설치 파일 해시 검증·격리 실행·재설치 거부·제거 후 사용자 파일 보존 통과.
- NVIDIA 설치 파일: 2,031,587,652 bytes. 실행 파일은 격리 진단과 native Windows 시작·정상 종료를 통과했습니다.
- 단위 111개와 Qt 24개가 기존 환경 및 독립 CPU 환경에서 통과했습니다. 실제 CPU WD 모델에서 합성 이미지로 10,861개 점수 반환 확인. CPU 모델 검사는 소스 환경에서 수행했습니다.
- 로컬 CPU/NVIDIA 후보의 build-info.json은 56ad875153c6b5a15465a0abeba7b2fc156965e9를 가리킵니다. 이후 f7c246e는 라이선스의 줄바꿈만 정규화한 커밋입니다. 첫 깨끗한 CI 체크아웃의 dirty 감지를 재현하고 문구 변경 없이 수정했습니다.
- 0.9.9 소스는 비공개 저장소에 반영했습니다. 설치 파일/CPU ZIP은 아직 GitHub Release에 게시하지 않았습니다. 기존 Standalone 바로가기와 0.9.8은 유지합니다.
