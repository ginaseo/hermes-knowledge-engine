# Vault 동기화 (Syncthing)

`HermesVault/`는 [Syncthing](https://syncthing.net)으로 여러 기기(예: 로컬
워크스테이션과 원격 배포 호스트) 간에 미러링할 수 있습니다 — 어느 쪽에서
파이프라인을 돌렸든 위키 수정사항과 새로 수집된 노트가 서로 동기화됩니다.

## 설정

1. `HermesVault/`의 복사본을 가질 각 기기에 Syncthing 설치
2. Linux에서는 `systemd --user` 서비스(`syncthing.service`)로 실행하고
   `loginctl enable-linger <user>`를 설정해 대화형 로그인 없이도 시작되게 함
3. 기기 간 device ID 교환 (Syncthing GUI 또는 CLI의 `syncthing --device-id`),
   서로를 신뢰 기기로 등록
4. 양쪽 다 같은 folder ID(예: `hermesvault`)로 각자의 로컬
   `HermesVault/` 경로를 가리키는 폴더 공유 설정

## 주의사항

- 각 쪽 `HermesVault/` **내부**에 `.stfolder` 마커 파일이 있어야 함
  (repo 루트 아님) — 마커 없으면 Syncthing이 스캔을 거부하고, 폴더 경로가
  잘못 설정된 경우 엉뚱한 위치에 마커를 만들어버림
- Windows는 대소문자 구분 안 하고 Linux는 함. 대소문자만 다른
  엔티티/위키 페이지(`Architecture.md` vs `architecture.md`)는 Windows
  쪽에서 충돌납니다. `EntityProcessor`가 stub 생성 시 대소문자 무시로
  중복 체크해서 *새* 중복은 막지만, 기존에 이미 생긴 중복은 수동으로
  정리해야 함 — 실제 내용 있는 파일 남기고 스텁 삭제
- 접속 정보(호스트, 포트, 인증정보)는 환경마다 다르므로 소스 관리에
  넣지 말고 배포별로 설정하세요
