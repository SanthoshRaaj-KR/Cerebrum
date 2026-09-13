<#
    Build the Cerebrum desktop launcher.

        .\tools\launcher\build.ps1              build, then put a shortcut on the desktop
        .\tools\launcher\build.ps1 -NoShortcut  build only

    Produces dist\Cerebrum.exe - a real Windows binary, not a .bat in a
    costume - plus the icon it carries.

    There is no SDK to install. Windows ships the .NET Framework C# compiler
    at %WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe, and that is
    what this uses; the cost is that Launcher.cs has to stay inside C# 5.
#>

param([switch]$NoShortcut)

$ErrorActionPreference = 'Stop'

Add-Type -AssemblyName System.Drawing

$here = $PSScriptRoot
$root = (Resolve-Path (Join-Path $here '..\..')).Path
$dist = Join-Path $root 'dist'
$obj = Join-Path $here 'obj'
$exe = Join-Path $dist 'Cerebrum.exe'
$ico = Join-Path $dist 'cerebrum.ico'

New-Item -ItemType Directory -Force -Path $dist, $obj | Out-Null

function Say($text, $colour = 'Gray') { Write-Host "  $text" -ForegroundColor $colour }

# ------------------------------------------------------------------ icon

# Drawn here rather than shipped as a binary blob, so the mark is defined
# by the same two hex values as the rest of the product and can't drift
# from them silently. Accent gradient, white C - high contrast is what
# survives being scaled down to 16px on a taskbar.

function New-Tile([int]$size) {
    $bmp = New-Object System.Drawing.Bitmap($size, $size)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    try {
        $g.SmoothingMode = 'AntiAlias'
        $g.TextRenderingHint = 'AntiAliasGridFit'
        $g.InterpolationMode = 'HighQualityBicubic'
        $g.Clear([System.Drawing.Color]::Transparent)

        $pad = [Math]::Max(1, [int]($size * 0.05))
        $side = $size - 2 * $pad
        $radius = [Math]::Max(2, [int]($size * 0.22))
        $d = $radius * 2

        $path = New-Object System.Drawing.Drawing2D.GraphicsPath
        $path.AddArc($pad, $pad, $d, $d, 180, 90)
        $path.AddArc($pad + $side - $d, $pad, $d, $d, 270, 90)
        $path.AddArc($pad + $side - $d, $pad + $side - $d, $d, $d, 0, 90)
        $path.AddArc($pad, $pad + $side - $d, $d, $d, 90, 90)
        $path.CloseFigure()

        $rect = New-Object System.Drawing.Rectangle($pad, $pad, $side, $side)
        $from = [System.Drawing.ColorTranslator]::FromHtml('#c084fc')   # vibranium-400
        $to = [System.Drawing.ColorTranslator]::FromHtml('#6d28d9')     # vibranium-800
        $brush = New-Object System.Drawing.Drawing2D.LinearGradientBrush($rect, $from, $to, 55.0)
        $g.FillPath($brush, $path)

        # A gold hairline just inside the tile, the same chrome the console
        # uses. Skipped at 16 and 32px: at that size it lands on the same
        # pixel as the edge and only muddies it.
        if ($size -ge 48) {
            $inset = [Math]::Max(2, [int]($size * 0.085))
            $ir = $radius - [int]($inset * 0.6)
            if ($ir -lt 2) { $ir = 2 }
            $id = $ir * 2
            $x = $pad + $inset
            $y = $pad + $inset
            $w = $side - 2 * $inset
            $inner = New-Object System.Drawing.Drawing2D.GraphicsPath
            $inner.AddArc($x, $y, $id, $id, 180, 90)
            $inner.AddArc($x + $w - $id, $y, $id, $id, 270, 90)
            $inner.AddArc($x + $w - $id, $y + $w - $id, $id, $id, 0, 90)
            $inner.AddArc($x, $y + $w - $id, $id, $id, 90, 90)
            $inner.CloseFigure()
            $goldPen = New-Object System.Drawing.Pen(
                [System.Drawing.Color]::FromArgb(150, 232, 198, 126),
                [Math]::Max(1.0, $size * 0.012))
            $g.DrawPath($goldPen, $inner)
            $goldPen.Dispose(); $inner.Dispose()
        }

        $fontSize = $size * 0.56
        $font = New-Object System.Drawing.Font('Segoe UI', $fontSize, [System.Drawing.FontStyle]::Bold,
                                               [System.Drawing.GraphicsUnit]::Pixel)
        $fmt = New-Object System.Drawing.StringFormat
        $fmt.Alignment = 'Center'
        $fmt.LineAlignment = 'Center'
        $box = New-Object System.Drawing.RectangleF($pad, ($pad - $size * 0.02), $side, $side)
        $g.DrawString('C', $font, [System.Drawing.Brushes]::White, $box, $fmt)

        $font.Dispose(); $fmt.Dispose(); $brush.Dispose(); $path.Dispose()
    } finally { $g.Dispose() }

    $ms = New-Object System.IO.MemoryStream
    $bmp.Save($ms, [System.Drawing.Imaging.ImageFormat]::Png)
    $bmp.Dispose()
    return , $ms.ToArray()
}

function Write-Icon([string]$path) {
    # ICO is a directory of images. Every entry here is a PNG, which
    # Windows has accepted at any size since Vista and which keeps the
    # alpha edge clean without hand-rolling an AND mask.
    $sizes = @(256, 128, 64, 48, 32, 16)
    $frames = @()
    foreach ($s in $sizes) { $frames += , (New-Tile $s) }

    $fs = [System.IO.File]::Create($path)
    $bw = New-Object System.IO.BinaryWriter($fs)
    try {
        $bw.Write([uint16]0)                 # reserved
        $bw.Write([uint16]1)                 # type: icon
        $bw.Write([uint16]$sizes.Count)

        $offset = 6 + 16 * $sizes.Count
        for ($i = 0; $i -lt $sizes.Count; $i++) {
            $s = $sizes[$i]
            $bytes = $frames[$i]
            $dim = if ($s -ge 256) { 0 } else { $s }   # 0 means 256 in this header
            $bw.Write([byte]$dim)
            $bw.Write([byte]$dim)
            $bw.Write([byte]0)               # palette size: none, it's true colour
            $bw.Write([byte]0)               # reserved
            $bw.Write([uint16]1)             # colour planes
            $bw.Write([uint16]32)            # bits per pixel
            $bw.Write([uint32]$bytes.Length)
            $bw.Write([uint32]$offset)
            $offset += $bytes.Length
        }
        foreach ($bytes in $frames) { $bw.Write($bytes) }
    } finally { $bw.Dispose(); $fs.Dispose() }
}

Say "Drawing the icon..." Cyan
Write-Icon $ico

# -------------------------------------------------------------- build info

# Where the launcher looks if it can't find the project by walking up from
# itself - which is what makes a copy of the .exe on the desktop work.
$buildInfo = Join-Path $obj 'BuildInfo.cs'
@"
// Generated by tools/launcher/build.ps1 - do not edit, and do not commit:
// the path below is specific to the machine that built the binary.
namespace Cerebrum
{
    static class BuildInfo
    {
        public const string RepoRoot = @"$root";
    }
}
"@ | Set-Content -Path $buildInfo -Encoding UTF8

# ---------------------------------------------------------------- compile

$csc = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if (-not (Test-Path $csc)) {
    $csc = Join-Path $env:WINDIR 'Microsoft.NET\Framework\v4.0.30319\csc.exe'
}
if (-not (Test-Path $csc)) {
    Say "No C# compiler found under %WINDIR%\Microsoft.NET." Yellow
    Say "Install the .NET Framework 4.x, or run .\start.ps1 instead."
    exit 1
}

Say "Compiling..." Cyan
& $csc /nologo /target:winexe /platform:anycpu /optimize+ `
    /out:"$exe" /win32icon:"$ico" `
    /r:System.dll /r:System.Core.dll /r:System.Drawing.dll /r:System.Windows.Forms.dll `
    (Join-Path $here 'Launcher.cs') $buildInfo

if ($LASTEXITCODE -ne 0) { Say "Compile failed." Yellow; exit 1 }

Say "Built $exe" Green

# --------------------------------------------------------------- shortcut

if ($NoShortcut) { exit 0 }

# GetFolderPath rather than "$HOME\Desktop": on a machine with OneDrive
# backup turned on, the real desktop is inside OneDrive and the literal
# path is an empty folder nobody looks at.
$desktop = [Environment]::GetFolderPath('Desktop')
$link = Join-Path $desktop 'Cerebrum.lnk'

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($link)
$shortcut.TargetPath = $exe
$shortcut.WorkingDirectory = $dist
$shortcut.IconLocation = "$exe,0"
$shortcut.Description = 'Start Cerebrum - mock technical interviews, run locally'
$shortcut.Save()

Say "Shortcut on your desktop: Cerebrum" Green
Say ""
Say "Double-click it. It brings up the bridge and the console, opens the tab,"
Say "and closing its window puts both back down."
