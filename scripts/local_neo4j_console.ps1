# Run only in the isolated hidden console created by local_neo4j.py.
param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$Neo4jHome
)

$ErrorActionPreference = 'Stop'
$neo4jLauncher = Join-Path $Neo4jHome 'bin\neo4j.ps1'
if (-not (Test-Path -LiteralPath $neo4jLauncher -PathType Leaf)) {
    throw 'The portable Neo4j PowerShell launcher was not found.'
}

Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;

namespace Camzyos.PortableNeo4j {
    public static class ConsoleControl {
        [DllImport("kernel32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        public static extern bool SetConsoleCtrlHandler(
            IntPtr handler, [MarshalAs(UnmanagedType.Bool)] bool add);
    }
}
'@

# CREATE_NEW_CONSOLE isolates signals, but launchers can inherit CTRL_C ignore.
# Clear it in this process before Neo4j's launcher creates either JVM.
# https://learn.microsoft.com/en-us/windows/console/setconsolectrlhandler
if (-not [Camzyos.PortableNeo4j.ConsoleControl]::SetConsoleCtrlHandler([IntPtr]::Zero, $false)) {
    throw [System.ComponentModel.Win32Exception]::new([Runtime.InteropServices.Marshal]::GetLastWin32Error())
}

& $neo4jLauncher console
exit $LASTEXITCODE
