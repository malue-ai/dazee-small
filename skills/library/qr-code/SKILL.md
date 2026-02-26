---
name: qr-code
description: Generate and read QR codes. Supports text, URLs, WiFi credentials, and vCards.
metadata:
  xiaodazi:
    dependency_level: lightweight
    os: [common]
    backend_type: local
    user_facing: true
    python_packages: ["qrcode", "Pillow"]
---

# QR 码生成与识别

生成和识别 QR 码，支持文本、URL、WiFi 凭据、名片（vCard）等格式。

## 使用场景

- 用户说「帮我生成一个二维码」「把这个链接做成二维码」
- 用户说「生成 WiFi 二维码，方便客人连接」
- 用户说「识别这个二维码图片里的内容」

## 执行方式

### 生成 QR 码

```python
import qrcode

# 基本用法
img = qrcode.make("https://example.com")
img.save("/tmp/qr.png")

# 自定义样式
qr = qrcode.QRCode(version=1, box_size=10, border=4)
qr.add_data("https://example.com")
qr.make(fit=True)
img = qr.make_image(fill_color="black", back_color="white")
img.save("/tmp/qr.png")
```

### WiFi QR 码

```python
wifi_data = "WIFI:T:WPA;S:MyNetwork;P:MyPassword;;"
img = qrcode.make(wifi_data)
img.save("/tmp/wifi_qr.png")
```

格式：`WIFI:T:{加密类型};S:{SSID};P:{密码};;`
加密类型：`WPA`、`WEP`、`nopass`

### 名片 QR 码（vCard）

```python
vcard = """BEGIN:VCARD
VERSION:3.0
FN:张三
TEL:+86-138-0000-0000
EMAIL:zhangsan@example.com
END:VCARD"""

img = qrcode.make(vcard)
img.save("/tmp/contact_qr.png")
```

### 识别 QR 码

```python
from PIL import Image
from pyzbar.pyzbar import decode

img = Image.open("qr_image.png")
results = decode(img)
for r in results:
    print(r.data.decode("utf-8"))
```

注意：识别功能需要额外安装 `pyzbar`（`pip install pyzbar`）和系统库 `zbar`。

## 输出规范

- 生成后返回图片文件路径
- WiFi 二维码说明使用方式（手机相机扫描即可连接）
- 不在日志中记录 WiFi 密码
