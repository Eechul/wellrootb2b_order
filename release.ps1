# dist\ 산출물을 GitHub 릴리스로 올린다.  실행:  .\build.ps1  →  .\release.ps1
#
# 토큰은 git 자격증명 저장소에서 꺼내 쓴다(이미 push가 되는 상태면 따로 준비할 게 없다).
# `releases/latest/download/update.json` 이 항상 최신 릴리스를 가리키므로,
# 새 버전을 올리기만 하면 사장님들 앱이 알아서 찾아온다.

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$Repo = "Eechul/wellrootb2b_order"
$AssetName = "WellrootOrder.exe"

$version = (Select-String -Path version.py -Pattern 'VERSION = "([^"]+)"').Matches[0].Groups[1].Value
$tag = "v$version"

foreach ($f in @("dist\$AssetName", "dist\update.json")) {
    if (-not (Test-Path $f)) { throw "$f 가 없습니다. 먼저 .\build.ps1 을 실행하세요." }
}

# update.json의 버전이 version.py와 어긋나면 배포 사고다 — 먼저 막는다
$manifest = Get-Content "dist\update.json" -Raw | ConvertFrom-Json
if ($manifest.version -ne $version) {
    throw "update.json 버전($($manifest.version))이 version.py($version)와 다릅니다. 다시 빌드하세요."
}
$actual = (Get-FileHash "dist\$AssetName" -Algorithm SHA256).Hash.ToLower()
if ($manifest.sha256 -ne $actual) {
    throw "update.json의 sha256이 실제 파일과 다릅니다. 다시 빌드하세요."
}

# git 자격증명에서 토큰 꺼내기
$out = "protocol=https`nhost=github.com`n`n" | git credential fill 2>$null
$token = ($out | Select-String -Pattern '^password=(.+)$').Matches.Groups[1].Value
if (-not $token) { throw "GitHub 자격증명을 찾지 못했습니다. 한 번 git push 해서 로그인해두세요." }
$headers = @{ Authorization = "Bearer $token"; "User-Agent" = "wellroot-release"; Accept = "application/vnd.github+json" }

Write-Host "릴리스 $tag 준비 중..." -ForegroundColor Cyan

# 같은 태그의 릴리스가 있으면 지우고 다시 만든다(자산 교체가 더 번거롭다)
try {
    $existing = Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo/releases/tags/$tag" -Headers $headers
    Write-Host "  기존 릴리스 $tag 를 지우고 다시 만듭니다." -ForegroundColor Yellow
    Invoke-RestMethod -Method Delete -Uri "https://api.github.com/repos/$Repo/releases/$($existing.id)" -Headers $headers | Out-Null
} catch {}

$body = @{
    tag_name = $tag
    name     = "$tag"
    body     = if ($manifest.notes) { $manifest.notes } else { "웰루트 발주 도우미 $version" }
    draft    = $false
    prerelease = $false
} | ConvertTo-Json

$release = Invoke-RestMethod -Method Post -Uri "https://api.github.com/repos/$Repo/releases" -Headers $headers -Body $body -ContentType "application/json"
Write-Host "  릴리스 생성됨: $($release.html_url)"

foreach ($file in @("dist\$AssetName", "dist\update.json")) {
    $name = Split-Path $file -Leaf
    $type = if ($name -like "*.json") { "application/json" } else { "application/octet-stream" }
    $uploadUrl = $release.upload_url -replace '\{\?name,label\}', "?name=$name"
    Write-Host "  올리는 중: $name ..."
    Invoke-RestMethod -Method Post -Uri $uploadUrl -Headers $headers `
        -InFile $file -ContentType $type | Out-Null
}

Write-Host ""
Write-Host "완료: $($release.html_url)" -ForegroundColor Green
Write-Host "매니페스트: https://github.com/$Repo/releases/latest/download/update.json"
