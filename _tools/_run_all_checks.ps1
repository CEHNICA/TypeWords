$ErrorActionPreference = 'Continue'
# 项目根目录 = 本脚本所在 _tools 的上一级（不写死本机绝对路径）
$p = Split-Path -Parent $PSScriptRoot
$py = @(
  @('check_article_quality.py', ''),
  @('check_title_unit.py', ''),
  @('check_dict_data.py', ''),
  @('check_dict_family.py', ''),
  @('check_dict_glue.py', ''),
  @('check_article_broken.py', ''),
  @('check_article_integrity.py', ''),
  @('check_article_sentences.py', ''),
  @('check_textbook_articles.py', '--http'),
  @('check_dict_list.py', '--http'),
  @('check_placement.py', ''),
  @('check_book_review.py', '--http'),
  @('check_article_import.py', '--http'),
  @('check_word_lookup.py', '--http'),
  @('check_test_flow.py', '--http'),
  @('check_custom_import.py', ''),
  @('check_book_wordsheet.py', ''),
  @('check_book_wordsheet.py', '--selftest'),
  @('_check_dict_format.py', ''),
  @('check_textbook_trans.py', ''),
  @('_tb_revert_check.py', '')
)
$bad = 0
foreach ($it in $py) {
  $f = $it[0]; $arg = $it[1]
  if (-not (Test-Path "$p\_tools\$f")) { Write-Output "[SKIP] $f （文件不存在）"; continue }
  if ($arg) { $out = python "$p\_tools\$f" $arg 2>&1 } else { $out = python "$p\_tools\$f" 2>&1 }
  $code = $LASTEXITCODE
  $tail = ($out | Select-Object -Last 3) -join ' | '
  $tag = if ($code -eq 0) { 'PASS' } else { 'FAIL'; $bad++ }
  Write-Output "[$tag] $f $arg -> $tail"
}
$node = @('_check_read_aloud.js', '_check_placement_ui.js', '_check_lookup_ui.js', '_check_custom_import_ui.js')
foreach ($f in $node) {
  if (-not (Test-Path "$p\_tools\$f")) { Write-Output "[SKIP] $f"; continue }
  $out = node "$p\_tools\$f" 2>&1
  $code = $LASTEXITCODE
  if ($code -ne 0 -and (($out | Out-String) -match 'Assertion failed')) {
    # node 收尾崩溃（libuv UV_HANDLE_CLOSING）：尺子本身可能是绿的，重跑一次
    Write-Output "       (崩溃重试) $f"
    $out = node "$p\_tools\$f" 2>&1
    $code = $LASTEXITCODE
  }
  $tail = ($out | Select-Object -Last 2) -join ' | '
  $tag = if ($code -eq 0) { 'PASS' } else { 'FAIL'; $bad++ }
  Write-Output "[$tag] $f -> $tail"
}
# .mjs 尺子（Node 24 直接跑 TS 源码的解析层单测）
$mjs = @('check_import_parser.mjs')
foreach ($f in $mjs) {
  if (-not (Test-Path "$p\_tools\$f")) { Write-Output "[SKIP] $f"; continue }
  $out = node "$p\_tools\$f" 2>&1
  $code = $LASTEXITCODE
  $tail = ($out | Select-Object -Last 2) -join ' | '
  $tag = if ($code -eq 0) { 'PASS' } else { 'FAIL'; $bad++ }
  Write-Output "[$tag] $f -> $tail"
}
Write-Output ""
Write-Output "失败项合计: $bad"
