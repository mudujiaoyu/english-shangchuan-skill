# -*- coding: utf-8 -*-
"""听力音频按「题号播报」锚点切段，可选逐段回读验证。

三步走（推荐顺序）:

1) 看停顿分层，确认题数：
       python cut_audio.py --audio 18年.mp3 --report

2) 转写定位，找出每段首句时间（打印带时间戳的转写，人工/脚本挑锚点）：
       python cut_audio.py --audio 18年.mp3 --transcribe

3) 按锚点切分 + 回读验证：
       python cut_audio.py --audio 18年.mp3 --out audio18 --anchors 47,76,100.8,112.2,... --verify

   跨大题、或想让每段只含本段内容（不吞后面的中文题头/长空白）时，用 --ends 给显式终点：
       python cut_audio.py --audio x.mp3 --out audio \
           --anchors 43.19,73.79,... --ends 68.65,100.90,...
   不给 --ends 时，每段会一直切到**下一个锚点**，段尾会带 5s 静音甚至下一大题的播报。

为什么不能只用 silencedetect：
    每个小题读两遍，题内也有 1~2 秒停顿；按静音中点切会把「第一遍/第二遍」劈开。
    用录音里念出的题号（"7." / "Nine" / "Thirteen"）当锚点最稳。

faster-whisper 坑：
    新版 av 下 decode_audio 会报 `metadata_errors`；本脚本先 ffmpeg 转 16k 单声道 wav，
    再用 numpy 传入，绕开该问题。模型走 HF_ENDPOINT=https://hf-mirror.com。
"""
import argparse
import os
import re
import subprocess
import sys
import wave


def run(cmd):
    # Windows 下 text=True 默认按 GBK 解码，ffmpeg stderr 含非 GBK 字节会抛
    # UnicodeDecodeError（表现为线程崩溃、log 变 None）。显式 UTF-8 + replace。
    return subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def silencedetect(audio, noise="-35dB", dur="1.0"):
    p = run(["ffmpeg", "-hide_banner", "-nostats", "-i", audio,
             "-af", f"silencedetect=noise={noise}:d={dur}", "-f", "null", "-"])
    log = p.stderr
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", log)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", log)]
    durs = [float(x) for x in re.findall(r"silence_duration: ([\d.]+)", log)]
    return list(zip(starts, ends, durs))


def duration(audio):
    p = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", audio])
    return float(p.stdout.strip())


def report(audio):
    sil = silencedetect(audio)
    total = duration(audio)
    print(f"时长 {total:.1f}s | 静音 {len(sil)} 处")
    tiers = {}
    for _, _, d in sil:
        tiers[round(d, 1)] = tiers.get(round(d, 1), 0) + 1
    print("停顿时长分布（>=1.0s）:")
    for k in sorted(tiers, reverse=True):
        if k >= 1.0:
            print(f"  {k:5.1f}s : {tiers[k]:2d}")
    print("\n提示: 出现一档明显多出来的等长停顿（如 9.1s×14），通常就是题间停顿。")


def load_model(model_size="tiny.en"):
    os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
    from faster_whisper import WhisperModel
    root = os.path.join(os.path.expanduser("~"), ".cache", "whisper")
    return WhisperModel(model_size, device="cpu", compute_type="int8", download_root=root)


def audio_array(audio):
    import numpy as np
    wav = os.path.join(os.environ.get("TEMP", "/tmp"), "_cut_audio_tmp.wav")
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", audio,
                    "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", wav], check=True)
    with wave.open(wav, "rb") as w:
        data = w.readframes(w.getnframes())
    os.remove(wav)
    return np.frombuffer(data, dtype=np.int16).astype("float32") / 32768.0


def transcribe(audio):
    model = load_model()
    segs, _ = model.transcribe(audio_array(audio), beam_size=1, language="en",
                               vad_filter=False, condition_on_previous_text=False)
    rows = [(round(s.start, 2), round(s.end, 2), s.text.strip()) for s in segs]
    print(f"转写 {len(rows)} 段（时间戳仅作参考，优先找念出的题号）:")
    for st, en, tx in rows:
        print(f"{st:7.2f}-{en:7.2f}  {tx[:110]}")
    return rows


def cut(audio, outdir, anchors, verify, tail, ends=None, trim_intro=False, intro_end=None,
        expect=None, verify_seconds=0):
    os.makedirs(outdir, exist_ok=True)
    total = duration(audio)
    anchors = list(anchors)
    if not ends and (trim_intro or intro_end is not None):
        sil = silencedetect(audio)
        if intro_end is not None:
            # 显式指定：卷首到第几秒为止全是试音/播报（用转写看第一条正文开口时间）。
            new_start = max(anchors[0], float(intro_end))
            print(f"去试音：卷首 {new_start:.2f}s 之前的内容丢弃（显式 --intro-end）")
            anchors[0] = new_start
        else:
            # 自动：只吸掉锚点所在的这段静音（死气/换气），不越过任何语音，
            # 因此绝不会把第一遍朗读切掉。真正的试音段请用 --intro-end 显式指定。
            inside = [b for a, b, d in sil if a - 0.1 <= anchors[0] <= b]
            if inside:
                new_start = max(inside)
                if new_start - anchors[0] > 0.2:
                    print(f"去试音：首段起点 {anchors[0]:.2f}s -> {new_start:.2f}s（只吸掉开头这段静音）")
                    anchors[0] = new_start
            else:
                print("去试音：锚点不在静音里，未做自动调整；若卷首确有试音，请用 --intro-end 指定结束秒数")
    if ends:
        # 显式起止：各段之间可以不连续。跨大题时用它跳过中文题头播报与超长空白，
        # 否则「每段切到下一个锚点」会把下一大题的播报吞进上一段（2020 安徽踩过）。
        if len(ends) != len(anchors):
            raise SystemExit(f"--ends 与 --anchors 数量必须一致：{len(ends)} vs {len(anchors)}")
        pairs = [(s, e) for s, e in zip(anchors, ends)]
    else:
        cuts = list(anchors) + [tail]
        if cuts[-1] is None or cuts[-1] > total:
            cuts[-1] = total
        pairs = [(cuts[i], cuts[i + 1]) for i in range(len(cuts) - 1)]
    files = []
    for i, (s, e) in enumerate(pairs, 1):
        if e > total:
            e = total
        out = os.path.join(outdir, f"li-{i:02d}.mp3")
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                        "-ss", f"{s:.2f}", "-to", f"{e:.2f}", "-i", audio,
                        "-ac", "1", "-ar", "22050", "-b:a", "48k", out], check=True)
        files.append((out, e - s))
    print(f"\n切出 {len(files)} 段 -> {outdir}")
    for p, d in files:
        print(f"  {os.path.basename(p)}  {d:6.1f}s")
    if expect is not None and len(files) != expect:
        raise SystemExit(f"段数不符：切出 {len(files)} 段，预期 {expect} 段（检查锚点数）")
    if not verify:
        return files

    model = load_model()
    scope = f"前 {verify_seconds}s" if verify_seconds else "整段"
    print(f"\n回读验证（{scope}，比对每段首句）:")
    import shutil as _sh, tempfile as _tf
    for p, _ in files:
        src = p
        tmp = None
        if verify_seconds:
            # 只切首 N 秒喂给 whisper：整段转写对「首句是否对得上」是浪费（长段尤其明显）
            tmp = os.path.join(_tf.gettempdir(), "_verify_head.mp3")
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                            "-t", str(verify_seconds), "-i", p,
                            "-ac", "1", "-ar", "16000", tmp], check=True)
            src = tmp
        segs, _ = model.transcribe(audio_array(src), beam_size=1, language="en",
                                   condition_on_previous_text=False)
        head = " ".join(s.text.strip() for s in segs)[:80]
        print(f"  {os.path.basename(p)}  {head}")
        if tmp and os.path.exists(tmp):
            os.remove(tmp)
    print("\n逐段与听力材料首行比对，命中率应 >= 18/19；不达标就调锚点重切，不要凑合。")
    return files


def main():
    ap = argparse.ArgumentParser(description="听力音频切分与验证")
    ap.add_argument("--audio", required=True)
    ap.add_argument("--report", action="store_true", help="只看停顿分层")
    ap.add_argument("--transcribe", action="store_true", help="转写并打印时间戳")
    ap.add_argument("--out", help="切分输出目录")
    ap.add_argument("--anchors", help="各段起点秒数，逗号分隔")
    ap.add_argument("--ends", help="各段终点秒数，逗号分隔（与 --anchors 等长）；"
                                   "缺省时每段切到下一个起点")
    ap.add_argument("--tail", type=float, default=None, help="最后一段终点，默认到文件末尾")
    ap.add_argument("--verify", action="store_true", help="切完逐段回读")
    ap.add_argument("--verify-seconds", type=float, default=0,
                    help="回读只取每段前 N 秒（0=整段）。校验「首句是否对得上」用 20 秒足够，长段能省数倍时间")
    ap.add_argument("--intro-end", type=float, default=None,
                    help="卷首试音结束秒数，之前的内容全部丢弃（用转写看第一条正文开口时间）")
    ap.add_argument("--trim-intro", action="store_true",
                    help="自动吸掉首段起点所在的静音（死气）；不会越过语音")
    ap.add_argument("--expect", type=int, default=None,
                    help="预期段数；切完数量不符直接报错（防锚点数错）")
    a = ap.parse_args()

    if a.report or not (a.transcribe or a.out):
        report(a.audio)
    if a.transcribe:
        transcribe(a.audio)
    if a.out:
        if not a.anchors:
            ap.error("--out 需要配合 --anchors")
        anchors = [float(x) for x in a.anchors.split(",") if x.strip()]
        ends = [float(x) for x in a.ends.split(",") if x.strip()] if a.ends else None
        cut(a.audio, a.out, anchors, a.verify, a.tail, ends, a.trim_intro, a.intro_end,
            a.expect, a.verify_seconds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
