import sys
from adb_shell.adb_device import AdbDeviceTcp
from adb_shell.auth.sign_cryptography import CryptographySigner

host = sys.argv[1] if len(sys.argv) > 1 else "192.168.0.60"
port = int(sys.argv[2]) if len(sys.argv) > 2 else 5555
cmd = sys.argv[3] if len(sys.argv) > 3 else "echo hello"

dev = AdbDeviceTcp(host, port, default_transport_timeout_s=10.0)
signer = CryptographySigner("/root/.android/adbkey")
dev.connect(rsa_keys=[signer], auth_timeout_s=10.0)
print(dev.shell(cmd, timeout_s=30))
