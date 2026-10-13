$asm=[Reflection.Assembly]::LoadFile((Join-Path $PSScriptRoot 'ExportTreeModels.exe'))
$decode=$asm.GetType('Ohana3DS_Rebirth.Ohana.TextureCodec').GetMethod('decode')
$fmtType=$asm.GetType('Ohana3DS_Rebirth.Ohana.RenderBase+OTextureFormat')
foreach($style in @(0,2,3)) { foreach($season in @(0,9)) {
$name='fobj_bridge_{0:00}_n_s_season{1:00}' -f $style,$season
$path=Join-Path $PSScriptRoot ('bridge_source/'+$name+'.bcres')
$b=[IO.File]::ReadAllBytes($path)
$t=[Text.Encoding]::ASCII.GetString($b).IndexOf('TXOB')
$w=[BitConverter]::ToInt32($b,$t+24);$h=[BitConverter]::ToInt32($b,$t+20)
$fmt=[Enum]::ToObject($fmtType,[BitConverter]::ToInt32($b,$t+48))
$len=[BitConverter]::ToInt32($b,$t+64);$off=$t+68+[BitConverter]::ToInt32($b,$t+68)
$data=New-Object byte[] $len;[Array]::Copy($b,$off,$data,0,$len)
$im=$decode.Invoke($null,([object[]]@([byte[]]$data,[int]$w,[int]$h,$fmt)))
$dest=Join-Path $PSScriptRoot ('bridge_source/'+$name+'/tex_bridge.png')
$im.Save($dest,[Drawing.Imaging.ImageFormat]::Png);$im.Dispose()
Write-Output "$name ${w}x${h} $fmt"
}}

