param(
    [string]$PublicRemote = "public",
    [string]$PrivateRemote = "private",
    [string]$PublicBranch = "main",
    [string]$PrivateBranch = "private-main",
    [string]$PublicRepoUrl = "https://github.com/ScottZt/jin-ce-zhi-suan.git",
    [string]$PrivateRepoUrl = "https://gitee.com/SeniorAgentTeam/jin-ce-zhi-suan.git",
    [string]$PublicCommitMessage = "feat: update public code",
    [string]$PrivateCommitMessage = "chore: update private config",
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
    } else {
        Invoke-Git -Args @("remote", "add", $Name, $Url) | Out-Null
        Invoke-Git -Args @("remote", "set-url", $Name, $Url) | Out-Null
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

$repoRoot = (Invoke-Git -Args @("rev-parse", "--show-toplevel") -ReadOnly).Output[0].Trim()
Set-Location $repoRoot
$startBranch = (Invoke-Git -Args @("rev-parse", "--abbrev-ref", "HEAD") -ReadOnly).Output[0].Trim()

try {
    Ensure-Remote -Name $PublicRemote -Url $PublicRepoUrl
    Ensure-Remote -Name $PrivateRemote -Url $PrivateRepoUrl
    Ensure-LocalBranch -BranchName $PrivateBranch -FromBranch $PublicBranch

    Invoke-Git -Args @("checkout", $PublicBranch) | Out-Null
    Invoke-Git -Args @("add", "-A") | Out-Null
    Invoke-Git -Args @("rm", "--cached", "--ignore-unmatch", "config.private.json") -AllowFailure | Out-Null
    if (Has-WorkingChanges) {
        Invoke-Git -Args @("commit", "-m", $PublicCommitMessage) | Out-Null
    } else {
        Write-Host "公共分支无可提交改动，跳过 commit。"
    }
    Invoke-Git -Args @("push", $PublicRemote, $PublicBranch) | Out-Null

    Invoke-Git -Args @("checkout", $PrivateBranch) | Out-Null
    Invoke-Git -Args @("merge", $PublicBranch, "--no-edit") | Out-Null
    if (Test-Path (Join-Path $repoRoot "config.private.json")) {
        Invoke-Git -Args @("add", "-f", "config.private.json") | Out-Null
    }
    if (Has-WorkingChanges) {
        Invoke-Git -Args @("commit", "-m", $PrivateCommitMessage) | Out-Null
    } else {
        Write-Host "私有分支无可提交改动，跳过 commit。"
    }
    Invoke-Git -Args @("push", $PrivateRemote, $PrivateBranch) | Out-Null
    Write-Host "双仓库推送完成。"
}
finally {
    if (-not $DryRun) {
        $currentBranch = (Invoke-Git -Args @("rev-parse", "--abbrev-ref", "HEAD") -ReadOnly).Output[0].Trim()
        if ($currentBranch -ne $startBranch) {
            Invoke-Git -Args @("checkout", $startBranch) -AllowFailure | Out-Null
        }
    }
}
