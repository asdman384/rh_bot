$root = (npm root -g) + "\@devicefarmer\minicap-prebuilt\prebuilt"
$abi  = (adb shell getprop ro.product.cpu.abi).Trim()
$sdk  = (adb shell getprop ro.build.version.sdk).Trim()

adb push "$root\$abi\bin\minicap"                     /data/local/tmp/
adb push "$root\$abi\lib\android-$sdk\minicap.so"     /data/local/tmp/
adb shell chmod 755 /data/local/tmp/minicap