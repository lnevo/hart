# The Windows reader of jython_scripts.txt, the list of the jython the hosts install (tools/hosts/pi in the repo,
# cats/scripts/pi in the package). Dot-sourced by apply_hart_package_local.ps1:
# . (Join-Path $hart 'cats\scripts\windows\jython_list.ps1')

# The roles a row may have (tools/hosts/pi/jython_list.sh reads the same ones), and the ones Windows installs: the
# macpi and pi rows are Start Up scripts of the Mac and the Pi.
$JythonRoles = @('startup', 'macpi', 'pi', 'sibling', 'part')
$JythonWindowsRoles = @('startup', 'sibling', 'part')

# Get-JythonSources LIST PACKAGE: the full path in PACKAGE of each row of LIST that Windows installs, in file order.
# Comment lines (# in the first column) and blank lines are skipped. Throws, naming LIST, when it is missing or names
# no script Windows installs, when a line is not a known ROLE and one relative .py PATH with no '.' or '..'
# segment, or when PACKAGE lacks a script Windows installs (all such scripts named at once).
function Get-JythonSources {
  param([Parameter(Mandatory = $true)][string]$List, [Parameter(Mandatory = $true)][string]$Package)
  if (-not (Test-Path -LiteralPath $List -PathType Leaf)) {
    throw ("jython list missing: {0}" -f $List)
  }
  $sources = New-Object System.Collections.Generic.List[string]
  $missing = New-Object System.Collections.Generic.List[string]
  $n = 0
  foreach ($line in [System.IO.File]::ReadAllLines($List)) {
    $n++
    if (-not $line.Trim() -or $line.StartsWith('#')) { continue }
    $fields = @($line.Trim() -split '\s+')
    if ($JythonRoles -cnotcontains $fields[0]) {
      throw ("{0}:{1}: unknown role '{2}' ({3})" -f $List, $n, $fields[0], ($JythonRoles -join ', '))
    }
    $rel = if ($fields.Count -eq 2) { $fields[1] } else { '' }
    if (-not $rel -or $rel -match '^[/\\]|:' -or $rel -notlike '*.py' -or ('/' + $rel + '/') -match '[/\\]\.\.?[/\\]') {
      throw ("{0}:{1}: expected '{2} PATH', one relative .py path with no '.' or '..' segment: {3}" -f $List, $n, $fields[0], $line)
    }
    if ($JythonWindowsRoles -cnotcontains $fields[0]) { continue }
    $src = Join-Path $Package ($rel.Replace('/', [System.IO.Path]::DirectorySeparatorChar))
    if (Test-Path -LiteralPath $src -PathType Leaf) { [void]$sources.Add($src) } else { [void]$missing.Add($rel) }
  }
  if ($missing.Count -gt 0) {
    throw ("The package lacks jython Windows installs ({0}): {1}" -f $List, ($missing -join ' '))
  }
  if ($sources.Count -eq 0) {
    throw ("jython list names no script Windows installs: {0}" -f $List)
  }
  return , $sources.ToArray()
}
