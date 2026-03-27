param(
    [string]$PublicRemote = "public",
    [string]$PrivateRemote = "private",
    [string]$PublicBranch = "main",
    [string]$PrivateBranch = "private-main",
    [string]$PublicRepoUrl = "https://github.com/ScottZt/jin-ce-zhi-suan.git",
    [string]$PrivateRepoUrl = "https://gitee.com/SeniorAgentTeam/jin-ce-zhi-suan.git",
    [string]$PublicCommitMessage = "feat: update public code",
    [string]$PrivateCommitMessage = "chore: update private config",
    [switch]$UseLocalCommits,
    [switch]$SkipPublicPush,
    [switch]$StrictPublicPush,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

function Invoke-Git {
    param(
        [Parameter(Mandatory = $true)][string[]]$Args,
        [switch]$AllowFailure,
        [switch]$ReadOnly
    )
    $display = $Args -join " "
    if ($DryRun -and -not $ReadOnly) {
        Write-Host "[DRY-RUN] git $display"
        return @{
            ExitCode = 0
            Output = @()
        }
    }
    $originalErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $output = & git @Args 2>&1
    }
    finally {
        $ErrorActionPreference = $originalErrorActionPreference
    }
    $exitCode = $LASTEXITCODE
    if (-not $AllowFailure -and $exitCode -ne 0) {
        throw "git $display 执行失败：`n$($output -join "`n")"
    }
    return @{
        ExitCode = $exitCode
        Output = @($output)
    }
}

function Ensure-Remote {
    param(
        [string]$Name,
        [string]$Url
    )
    $remoteOutput = Invoke-Git -Args @("remote") -ReadOnly
    $remoteSet = @($remoteOutput.Output | ForEach-Object { "$_".Trim() }) -contains $Name
    if ($remoteSet) {
        Invoke-Git -Args @("remote", "set-url", $Name, $Url) | Out-Null
        Invoke-Git -Args @("remote", "set-url", "--push", $Name, $Url) | Out-Null
    } else {
        Invoke-Git -Args @("remote", "add", $Name, $Url) | Out-Null
        Invoke-Git -Args @("remote", "set-url", $Name, $Url) | Out-Null
        Invoke-Git -Args @("remote", "set-url", "--push", $Name, $Url) | Out-Null
    }
}

function Ensure-LocalBranch {
    param(
        [string]$BranchName,
        [string]$FromBranch
    )
    $verify = Invoke-Git -Args @("rev-parse", "--verify", $BranchName) -AllowFailure -ReadOnly
    if ($verify.ExitCode -ne 0) {
        Invoke-Git -Args @("checkout", $FromBranch) | Out-Null
        Invoke-Git -Args @("branch", $BranchName, $FromBranch) | Out-Null
    }
}

function Has-WorkingChanges {
    $status = Invoke-Git -Args @("status", "--porcelain") -ReadOnly
    return ($status.Output | Measure-Object).Count -gt 0
}

function Find-StashRefByMessage {
    param([string]$Message)
    $list = Invoke-Git -Args @("stash", "list") -ReadOnly
    foreach ($line in $list.Output) {
        $text = "$line"
        if ($text -match "^(stash@\{\d+\}):" -and $text.Contains($Message)) {
            return $Matches[1]
        }
    }
    return ""
}

function Resolve-RepoRoot {
    $candidate = Split-Path -Parent $PSCommandPath
    while (-not [string]::IsNullOrWhiteSpace($candidate)) {
        if (Test-Path (Join-Path $candidate ".git")) {
            return $candidate
        }
        $parent = Split-Path -Parent $candidate
        if ($parent -eq $candidate) {
            break
        }
        $candidate = $parent
    }
    throw "未找到 .git 仓库目录。请确认当前项目仍是 Git 仓库（.git 未被删除），或先在项目根目录执行 git init 并配置远端。"
}

$repoRoot = Resolve-RepoRoot
Set-Location $repoRoot
$startBranch = (Invoke-Git -Args @("rev-parse", "--abbrev-ref", "HEAD") -ReadOnly).Output[0].Trim()
$privateStashCreated = $false
$entryStashCreated = $false
$entryStashTag = "dual-repo-entry-temp-" + [DateTime]::Now.ToString("yyyyMMddHHmmssfff")
$publicPushFailed = $false

try {
    $publicDenyList = @(
        "config.private.json",
        "data/strategies/custom_strategies.private.json",
        ".env",
        ".env.*",
        "双仓库推送指南.md",
        "数据接口系统的操作手册.md",
        "server.log",
        "USER_GUIDE.md"
    )
    Ensure-Remote -Name $PublicRemote -Url $PublicRepoUrl
    Ensure-Remote -Name $PrivateRemote -Url $PrivateRepoUrl
    Ensure-LocalBranch -BranchName $PrivateBranch -FromBranch $PublicBranch

    $entryBefore = @((Invoke-Git -Args @("stash", "list") -ReadOnly).Output).Count
    Invoke-Git -Args @("stash", "push", "--include-untracked", "-m", $entryStashTag) -AllowFailure | Out-Null
    $entryAfter = @((Invoke-Git -Args @("stash", "list") -ReadOnly).Output).Count
    $entryStashCreated = $entryAfter -gt $entryBefore

    Invoke-Git -Args @("checkout", $PublicBranch) | Out-Null
    Invoke-Git -Args @("add", "-A") | Out-Null
    foreach ($path in $publicDenyList) {
        Invoke-Git -Args @("rm", "--cached", "--ignore-unmatch", $path) -AllowFailure | Out-Null
    }
    if (Has-WorkingChanges) {
        Invoke-Git -Args @("commit", "-m", $PublicCommitMessage) | Out-Null
    } else {
        Write-Host "公共分支无可提交改动，跳过 commit。"
    }
    if ($SkipPublicPush) {
        Write-Host "已指定 SkipPublicPush，跳过 public push。"
    } else {
        $publicPushResult = Invoke-Git -Args @("push", $PublicRemote, $PublicBranch) -AllowFailure
        if ($publicPushResult.ExitCode -ne 0) {
            $publicPushFailed = $true
            if ($StrictPublicPush) {
                throw "public push 失败，已按 StrictPublicPush 中止：`n$($publicPushResult.Output -join "`n")"
            }
            Write-Host "警告：public push 失败，继续执行 private push。"
            Write-Host ($publicPushResult.Output -join "`n")
        }
    }

    $stashBeforeCount = @((Invoke-Git -Args @("stash", "list") -ReadOnly).Output).Count
    Invoke-Git -Args @("stash", "push", "--include-untracked", "-m", "dual-repo-temp-private") -AllowFailure | Out-Null
    $stashAfterCount = @((Invoke-Git -Args @("stash", "list") -ReadOnly).Output).Count
    $privateStashCreated = $stashAfterCount -gt $stashBeforeCount

    Invoke-Git -Args @("checkout", $PrivateBranch) | Out-Null
    Invoke-Git -Args @("merge", $PublicBranch, "--no-edit") | Out-Null
    if ($privateStashCreated) {
        Invoke-Git -Args @("stash", "apply", "stash@{0}") | Out-Null
        Invoke-Git -Args @("stash", "drop", "stash@{0}") | Out-Null
        $privateStashCreated = $false
    }
    foreach ($path in $publicDenyList) {
        if (Test-Path (Join-Path $repoRoot $path)) {
            Invoke-Git -Args @("add", "-f", $path) -AllowFailure | Out-Null
        }
    }
    if (Has-WorkingChanges) {
        Invoke-Git -Args @("commit", "-m", $PrivateCommitMessage) | Out-Null
    } else {
        Write-Host "私有分支无可提交改动，跳过 commit。"
    }
    Invoke-Git -Args @("push", $PrivateRemote, $PrivateBranch) | Out-Null
    if ($publicPushFailed) {
        Write-Host "private push 已完成，但 public push 失败（见上方警告）。"
    } else {
        Write-Host "双仓库推送完成。"
    }
}
finally {
    if (-not $DryRun) {
        $currentBranch = (Invoke-Git -Args @("rev-parse", "--abbrev-ref", "HEAD") -ReadOnly).Output[0].Trim()
        if ($currentBranch -ne $startBranch) {
            Invoke-Git -Args @("checkout", $startBranch) -AllowFailure | Out-Null
        }
        if ($entryStashCreated) {
            $entryRef = Find-StashRefByMessage -Message $entryStashTag
            if (-not [string]::IsNullOrWhiteSpace($entryRef)) {
                Invoke-Git -Args @("stash", "apply", $entryRef) -AllowFailure | Out-Null
                Invoke-Git -Args @("stash", "drop", $entryRef) -AllowFailure | Out-Null
            } else {
                Write-Host "检测到入口临时 stash 未自动恢复，请手动执行：git stash list"
            }
        }
        if ($privateStashCreated) {
            Write-Host "检测到未恢复的临时 stash，请手动执行：git stash list / git stash apply stash@{0}"
        }
    }
}
