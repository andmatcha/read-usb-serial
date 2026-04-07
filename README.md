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

### Write serial data continuously

```bash
python3 write_usb_serial.py --port /dev/cu.usbmodem12301 --baudrate 115200 --message "ping" --append-newline --interval 1
```

`--count 10` のように指定すると回数を制限できます。省略時は `Ctrl+C` まで送り続けます。

### Send uplink dummy Arm/Rover data

```bash
python3 send_uplink_dummy_data.py --list
python3 send_uplink_dummy_data.py \
  --arm-port /dev/cu.usbserial-ARM \
  --rover-port /dev/cu.usbserial-ROVER
python3 send_uplink_dummy_data.py \
  --send-mode alternate \
  --arm-port /dev/cu.usbserial-ARM \
  --rover-port /dev/cu.usbserial-ROVER
```

`--arm-port` は `uplink` の `PacketAC_v6` に合う 39 バイトのバイナリフレームを送り、`--rover-port` は `0x120,1234\r\n` のような Rover 行データを送り続けます。片方だけ指定して単独送信もできます。既定の `--send-mode parallel` は Arm/Rover を並列送信し、`--send-mode alternate` を指定すると `Arm -> Rover -> Arm -> Rover` の順で交互に送ります。既定は `115200 8N1` で、周期は `--arm-interval` / `--rover-interval`、Rover の CAN ID は `--rover-can-ids 0x120 0x121 ...` で調整できます。

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

### Write serial data continuously

```powershell
python write_usb_serial.py --port COM3 --baudrate 115200 --message "ping" --append-newline --interval 1
```

`--count 10` のように指定すると回数を制限できます。省略時は `Ctrl+C` まで送り続けます。

### Send uplink dummy Arm/Rover data

```powershell
python send_uplink_dummy_data.py --list
python send_uplink_dummy_data.py --arm-port COM3 --rover-port COM4
python send_uplink_dummy_data.py --send-mode alternate --arm-port COM3 --rover-port COM4
```

`--arm-port` は `uplink` の `PacketAC_v6` に合う 39 バイトのバイナリフレームを送り、`--rover-port` は `0x120,1234\r\n` のような Rover 行データを送り続けます。片方だけ指定して単独送信もできます。既定の `--send-mode parallel` は Arm/Rover を並列送信し、`--send-mode alternate` を指定すると `Arm -> Rover -> Arm -> Rover` の順で交互に送ります。既定は `115200 8N1` で、周期は `--arm-interval` / `--rover-interval`、Rover の CAN ID は `--rover-can-ids 0x120 0x121 ...` で調整できます。
