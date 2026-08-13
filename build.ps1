# 배포용 exe를 만든다.  실행:  .\build.ps1
#
# 브라우저(크로미움 ~200MB)는 **넣지 않는다** — 설치된 Chrome/Edge를 쓴다(browser.py).
# 그래도 Playwright의 Node 드라이버(node.exe 약 86MB)는 반드시 함께 들어간다.

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# 실행파일 이름. 바꾸면 update.json의 url 파일명도 같이 확인할 것.
$AppName = "웰루트 발주도우미"
$ExePath = "dist\$AppName.exe"

$version = (Select-String -Path version.py -Pattern 'VERSION = "([^"]+)"').Matches[0].Groups[1].Value
Write-Host "빌드 버전: $version" -ForegroundColor Cyan

python -m pip install --quiet --upgrade pyinstaller

# 실행 중인 앱이 exe를 잠그면 PyInstaller가 조용히 실패한다.
# onefile은 부모/자식 두 프로세스로 뜨므로 이름으로 싹 정리한다.
$running = @(Get-Process -Name $AppName -ErrorAction SilentlyContinue)
if ($running.Count) {
    Write-Host "실행 중인 $AppName $($running.Count)개를 종료합니다." -ForegroundColor Yellow
    $running | Stop-Process -Force
    Start-Sleep -Seconds 2
}

Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
if (Test-Path $ExePath) {
    throw "$ExePath 를 지우지 못했습니다(잠김). 실행 중인 프로그램을 닫고 다시 시도하세요."
}

# 실행파일 이름(한글). 자기 교체는 PowerShell 스크립트라 한글 경로도 안전하다.
# 배포 URL의 파일명은 별개로 ASCII를 유지한다(updater가 임시폴더에 ASCII로 받는다).
# 안 쓰는 무거운 패키지는 뺀다. PyInstaller가 설치된 것들을 넉넉히 긁어오기 때문에
# 빼주지 않으면 numpy 같은 게 그냥 딸려 들어간다(우리 코드는 쓰지 않는다).
$excludes = @(
    "numpy", "pandas", "matplotlib", "scipy", "PIL", "PyQt5", "PyQt6", "PySide2", "PySide6",
    "IPython", "notebook", "pytest", "setuptools._vendor", "lxml", "tkinter.test"
)
$excludeArgs = $excludes | ForEach-Object { "--exclude-module", $_ }

# assets/ 안의 그림들을 동봉한다. 파일이 없어도 앱은 그냥 그림 없이 뜬다.
# 실행에 실제로 쓰이는 것만 넣는다.
# assets 폴더를 통째로 넣으면 원본 로고(6MB)·생성 스크립트까지 딸려 들어간다.
$assetArgs = @()
foreach ($a in @("app.ico", "footer.png")) {
    if (Test-Path "assets\$a") { $assetArgs += @("--add-data", "assets\$a;assets") }
}
$iconArgs = @()
if (Test-Path "assets\app.ico") { $iconArgs = @("--icon", "assets\app.ico") }
else { Write-Host "assets\app.ico 가 없어 기본 아이콘으로 빌드합니다." -ForegroundColor DarkGray }

python -m PyInstaller `
    --noconfirm --clean --onefile --windowed `
    --name $AppName `
    --collect-all playwright `
    @excludeArgs @assetArgs @iconArgs `
    app.py

# $ErrorActionPreference 는 외부 명령의 종료코드를 잡아주지 않는다 — 직접 확인해야
# 빌드가 실패했는데 이전 exe를 두고 "완료"라고 보고하는 사고를 막는다.
if ($LASTEXITCODE -ne 0) { throw "PyInstaller 실패 (종료코드 $LASTEXITCODE). 위 로그를 확인하세요." }

$exe = $ExePath
if (-not (Test-Path $exe)) { throw "빌드 실패: $exe 없음" }

# ── 코드서명 (인증서가 있을 때만) ────────────────────────────────────────────
# 서명하면 "알 수 없는 게시자" 경고가 회사 이름으로 바뀌고 백신 오탐이 크게 준다.
# 인증서가 없으면 그냥 건너뛴다 — 서명 없이도 앱은 동작한다.
#
# 쓰는 법: 인증서를 윈도우 인증서 저장소에 설치한 뒤 지문(thumbprint)을 환경변수로 준다.
#   $env:WELLROOT_SIGN_THUMBPRINT = "aabbcc..."   (인증서 속성 → 자세히 → 지문)
$thumb = $env:WELLROOT_SIGN_THUMBPRINT
if ($thumb) {
    $signtool = Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin" -Recurse -Filter signtool.exe -ErrorAction SilentlyContinue |
                Where-Object { $_.FullName -match 'x64' } | Select-Object -Last 1
    if (-not $signtool) {
        Write-Host "signtool.exe 를 찾지 못해 서명을 건너뜁니다 (Windows SDK 필요)." -ForegroundColor Yellow
    } else {
        Write-Host "코드서명 중..." -ForegroundColor Cyan
        # /fd sha256: 파일 다이제스트, /tr: 타임스탬프(인증서 만료 후에도 서명이 유효하게)
        & $signtool.FullName sign /sha1 $thumb /fd sha256 `
            /tr http://timestamp.digicert.com /td sha256 /q $exe
        if ($LASTEXITCODE -ne 0) { throw "코드서명 실패 (종료코드 $LASTEXITCODE)" }
        & $signtool.FullName verify /pa /q $exe
        if ($LASTEXITCODE -ne 0) { throw "서명 검증 실패" }
        Write-Host "서명 완료 ✓" -ForegroundColor Green
    }
} else {
    Write-Host "서명 안 함 (WELLROOT_SIGN_THUMBPRINT 미설정)" -ForegroundColor DarkGray
}

# ⚠ sha256은 반드시 **서명 후에** 계산해야 한다. 서명하면 파일이 바뀌므로
#   먼저 계산하면 자동 업데이트의 체크섬 검증이 항상 실패한다.
$sizeMB = [math]::Round((Get-Item $exe).Length / 1MB, 1)
$sha = (Get-FileHash $exe -Algorithm SHA256).Hash.ToLower()

# 자동 업데이트용 매니페스트. url은 실제 배포처 주소로 바꿔서 함께 올린다.
@{
    version = $version
    url     = "https://github.com/사용자명/저장소명/releases/download/v$version/WellrootOrder.exe"  # 배포 파일명은 ASCII 권장
    sha256  = $sha
    notes   = "변경 내용을 여기에 적으세요"
} | ConvertTo-Json | Set-Content "dist\update.json" -Encoding UTF8

Write-Host ""
Write-Host "완료: $exe  ($sizeMB MB)" -ForegroundColor Green
Write-Host "sha256: $sha"
Write-Host ""
Write-Host "배포 순서:" -ForegroundColor Yellow
Write-Host "  1. dist\update.json 의 url 을 실제 배포 주소로 수정"
Write-Host "  2. exe(배포 시 ASCII 이름 권장)와 update.json 을 릴리스에 함께 업로드"
Write-Host "  3. 사장님들 앱은 다음 실행 때 update.json 을 보고 스스로 갱신"
