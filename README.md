# USB Serial Reader

USB シリアル変換器や USB CDC デバイスのデータをターミナルへ出力するための Python スクリプトです。

このスクリプトは `pyserial` を使っているため、macOS と Windows の両方で利用できます。

## macOS

前提:
- USB シリアル変換器や USB CDC デバイスが `/dev/cu.*` または `/dev/tty.*` として認識されている必要があります。

### Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Port list

```bash
python3 read_usb_serial.py --list
```

### Read serial data

```bash
python3 read_usb_serial.py --port /dev/cu.usbmodem12301 --baudrate 115200
```

ポートが 1 つだけ見えている場合は `--port` を省略できます。

生バイト列を 16 進表示したい場合:

```bash
python3 read_usb_serial.py --port /dev/cu.usbmodem12301 --baudrate 115200 --raw
```

## Windows

前提:
- USB シリアル変換器や USB CDC デバイスが `COM3` のような COM ポートとして認識されている必要があります。
- デバイスに応じて USB シリアルドライバのインストールが必要な場合があります。

### Setup

```powershell
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### Port list

```powershell
python read_usb_serial.py --list
```

### Read serial data

```powershell
python read_usb_serial.py --port COM3 --baudrate 115200
```

ポートが 1 つだけ見えている場合は `--port` を省略できます。

生バイト列を 16 進表示したい場合:

```powershell
python read_usb_serial.py --port COM3 --baudrate 115200 --raw
```
