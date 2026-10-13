# Raw TextureCodec decode of single-texture house/shop bcres files; keeps RGB under zero alpha
# (Ohana's bitmap path erases it). Writes <file>_raw.png beside each source.
param([string]$Root = (Join-Path $PSScriptRoot 'house_source'))
$asm=[Reflection.Assembly]::LoadFile((Join-Path $PSScriptRoot 'ExportTreeModels.exe'))
$decode=$asm.GetType('Ohana3DS_Rebirth.Ohana.TextureCodec').GetMethod('decode')
$fmtType=$asm.GetType('Ohana3DS_Rebirth.Ohana.RenderBase+OTextureFormat')
Get-ChildItem -Path $Root -Recurse -Filter *.bcres | Where-Object { $_.FullName -like '*\Textures\*' } | ForEach-Object {
  $b=[IO.File]::ReadAllBytes($_.FullName)
  $t=[Text.Encoding]::ASCII.GetString($b).IndexOf('TXOB')
  if ($t -lt 0) { return }
  $w=[BitConverter]::ToInt32($b,$t+24);$h=[BitConverter]::ToInt32($b,$t+20)
  $fmt=[Enum]::ToObject($fmtType,[BitConverter]::ToInt32($b,$t+48))
  $len=[BitConverter]::ToInt32($b,$t+64);$off=$t+68+[BitConverter]::ToInt32($b,$t+68)
  $data=New-Object byte[] $len;[Array]::Copy($b,$off,$data,0,$len)
  $im=$decode.Invoke($null,([object[]]@([byte[]]$data,[int]$w,[int]$h,$fmt)))
  $im.Save(($_.FullName -replace '\.bcres$','_raw.png'),[Drawing.Imaging.ImageFormat]::Png);$im.Dispose()
}
