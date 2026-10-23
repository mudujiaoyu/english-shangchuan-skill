# 听力切分细则

整卷 mp3 → 每个听力单元一段。**最容易返工的一步**，按下面顺序做。

## 1. 先分层，不要直接切

```bash
ffmpeg -hide_banner -nostats -i 听力.mp3 -af silencedetect=noise=-35dB:d=1.2 -f null NUL 2> silence.txt
```

看**长静音**的分层：

| 停顿长度 | 含义 |
| --- | --- |
| 0.8–2.0s | 题内（两遍朗读之间、句中） |
| 8–15s | 题间（上一题读完到下一题报题号） |
| 20–30s | 大题间（预留作答时间） |

## 2. 找锚点

优先级：**录音念出的题号** > 长静音中点 > 中文大题指令。

```bash
python scripts/cut_audio.py --audio 听力.mp3 --transcribe
```

念出的 "Number 7" 常被识别成 `7.`、"Nine"→`Nine`、"Thirteen"→`Thirteen`。

**不要相信转写的时间戳**：试音是 1kHz 单音，VAD 会切出几十个碎片，时间戳整体漂移。
做法是：用静音表定骨架，用转写只找题号出现在第几个长静音之后。

## 3. 切

```bash
python scripts/cut_audio.py --audio 听力.mp3 \
  --anchors 40.1,66.6,99.6,136.2,174.3,243.4,319.4,473.2,643.3 \
  --intro-end 29.1 --out 02_audio/ --verify
```

- `--intro-end`：丢弃试音，**必须显式给**；`--trim-intro` 只吸死气，不认识试音。
- `--ends`：首尾各收一次，防止吞进下一题报题号或大段空白。
- 编码 `-ac 1 -ar 22050 -b:a 48k`。

## 4. 回读校验（不可跳过）

每段切 20–30 秒做一次转写，与听力稿首句比对：

```bash
ffmpeg -y -ss <start> -t 30 -i 原.mp3 -ac 1 -ar 16000 /tmp/p.wav
python scripts/cut_audio.py --audio /tmp/p.wav --transcribe
```

**全中才算过**。个别因音质存疑的，记在交接单。

## 5. 量级自检

同类单元时长应接近（短对话彼此差 2 倍以内）。某段明显偏长 → 切点把下一题的播报吞进来了。

## 已知坑

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 两遍朗读被劈开 | 按静音切在题内停顿 | 切点落在题间长静音 |
| li-01 里有人重复 "Thank you." | 卷首试音没切 | `--intro-end` |
| 段数与题数不符 | 段的单位是「听力单元」不是「小题」 | 按 structure.json 的单元数切 |
| 转写时间戳对不上 | VAD 抖动 | 用静音表定骨架 |
