$adapter="以太网"
$dns=netsh interface ipv6 show dnsservers $adapter
$hasBadDns = $dns -match "fe80::1"
if ($hasBadDns) {
  $p=Get-Process -Name "*clash*","*verge*","*mihomo*" -ErrorAction SilentlyContinue
  if (-not $p) {
    netsh interface ipv6 delete dnsservers $adapter all
    netsh interface ipv6 add dnsservers $adapter address="2001:4860:4860::8888" index=1
  }
}