# 비공개 업데이트의 GitHub 로그인 설정

> 과거 비공개 배포용 설정 기록입니다. **0.9.12 공개 ZIP 배포에는 GitHub 로그인·GitHub App 설정이 필요하지 않습니다.** 아래 절차는 현재 설치 순서가 아닙니다.

이 문서는 qoalsrb88/BMK-AI-Studio의 업데이트를 읽는 GitHub App 설정입니다. 로그인 연동과 Windows Schannel TLS 수정은 0.9.10 소스에 포함됩니다. 기존 0.9.8 배포와 이전 0.9.9 로컬 실행 파일에는 포함되지 않습니다. 2026-10-07 사용자가 실제 로그인과 비공개 배포 목록 조회 성공을 확인했습니다.

## 권한과 저장소 선택

권한은 앱이 할 수 있는 일을 정하고, 저장소 선택은 그 권한을 적용할 위치를 정합니다. 설치 화면에 No permissions와 No repositories가 표시되면 다음 순서로 설정합니다.

1. 설치 화면 위쪽의 App settings를 누릅니다. 다른 경로는 GitHub Settings → Developer settings → GitHub Apps → 해당 앱의 Edit입니다.
2. 왼쪽 Permissions & events → Repository permissions를 펼칩니다.
3. Contents를 Read-only로 설정합니다. Metadata는 기본 필수 읽기 권한으로 자동 설정되어 있으면 그대로 둡니다. 나머지 Repository/Organization/Account 권한은 No access를 유지합니다.
4. 아래쪽 Save changes를 누릅니다.
5. GitHub Settings → Applications → Installed GitHub Apps → 해당 앱의 Configure로 이동합니다. https://github.com/settings/installations 에서도 접근할 수 있습니다.
6. 새 권한 요청 안내가 있으면 요청 내용을 열고 승인합니다. 앱 설정을 저장하는 것과 기존 설치의 새 권한을 승인하는 것은 별도 단계입니다. 화면에서 안내를 찾지 못하면 GitHub가 보낸 권한 변경 알림 이메일의 링크를 확인합니다.
7. Repository access에서 Only select repositories를 고르고, Select repositories에서 BMK-AI-Studio를 선택한 뒤 Save를 누릅니다. 승인 화면에서 저장소를 함께 선택하도록 표시되면 그 화면에서 선택합니다.
8. 최종 설치 화면에 Contents/Metadata 읽기 권한과 BMK-AI-Studio 저장소가 표시되는지 확인합니다.

Contents 읽기 권한은 배포 정보와 저장소 콘텐츠를 읽을 수 있는 권한입니다. 배포만을 위한 더 좁은 전용 권한은 이 Release API에 제공되지 않습니다. 저장소 수정·삭제 권한은 부여하지 않습니다.

## 브라우저 로그인

앱 등록의 General → Identifying and authorizing users에서 Enable Device Flow를 켭니다. Webhook은 비활성 상태를 유지합니다. 이 구현은 공개 Client ID를 사용하며 Client secret 또는 Private key를 배포 프로그램에 넣지 않습니다.

소스 앱에서 설정 → 업데이트 → GitHub 로그인을 열고 연결 코드 받기를 누릅니다. 대화상자가 표시한 코드를 https://github.com/login/device 에 직접 입력한 뒤, 자신이 등록한 앱인지 확인하고 승인합니다. 코드가 만료되면 새 코드를 발급받습니다. 로그인 완료 후 새 버전 확인으로 실제 비공개 저장소 접근을 확인합니다.

선택적인 로그인 보관은 Windows DPAPI로 암호화하며 이 PC의 별도 설정 위치에 저장합니다. 사용자 이미지·노트 데이터 이동 대상에는 포함하지 않습니다. 보관하지 않으면 업데이트 대화상자의 현재 로그인만 사용합니다. 유효 기간 만료 시 다시 로그인하며 자동 갱신용 비밀키는 저장하지 않습니다. 이 PC에서 로그아웃은 로컬 보관 정보를 삭제합니다. GitHub 자체의 앱 승인 취소는 GitHub 계정 설정에서 수행합니다.

## 확인이 안 되는 경우

- 여전히 No repositories만 보임: 앱 등록의 Contents 설정 저장과 기존 설치의 새 권한 승인을 모두 확인하고 페이지를 새로고침합니다.
- 로그인은 성공했으나 비공개 버전 조회가 안 됨: 로그인한 계정 자체의 저장소 접근 권한, 앱의 Contents 읽기 권한, 앱 설치의 저장소 선택을 함께 확인합니다.
- 인증이 만료되거나 취소됨: 앱에서 다시 로그인합니다. 앱은 거부된 보관 인증을 정리합니다.
- 설치 파일 서명 및 자동 설치: 이 로그인 설정과 별도 작업입니다. 0.9.11 소스에 다운로드/설치 화면과 백업·복구 절차를 구현했지만 실제 인증서가 없어 자동 설치는 비활성 상태입니다. 인증서 준비 순서는 [배포 안내](RELEASING.md#개인-명의-코드-서명-준비)를 참고하세요.

참고: [앱 등록 변경](https://docs.github.com/en/apps/maintaining-github-apps/modifying-a-github-app-registration), [설치된 앱의 저장소 선택](https://docs.github.com/en/apps/using-github-apps/reviewing-and-modifying-installed-github-apps), [Release 조회에 필요한 Contents 권한](https://docs.github.com/en/rest/releases/releases#list-releases).
