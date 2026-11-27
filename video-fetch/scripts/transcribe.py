# /// script
# requires-python = ">=3.10"
# dependencies = ["mlx-audio==0.6.5"]
# ///
"""把一段音频转成逐句字幕 transcript.srt 和口播稿 transcript.txt。

用法：uv run transcribe.py <audio16k.wav> <输出目录>
流程：按停顿切成不超过 CHUNK_MAX 秒的块（ForcedAligner 一次只能处理约 3 分钟）
     -> Qwen3-ASR 转写（带标点）-> Qwen3-ForcedAligner 给每个字时间
     -> 按标点断句，每句的首末字时间写成一条字幕。
最后一行 stdout 是 JSON：{"lines": N, "aligned": M}；进度写 stderr。
"""
import difflib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

CHUNK_MIN, CHUNK_MAX = 60.0, 150.0
LINE_MAX = 22  # 一条字幕超过这么多字，就在逗号处再断

ASR_NAME = "Qwen3-ASR-1.7B-8bit"
ALIGNER_NAME = "Qwen3-ForcedAligner-0.6B-8bit"
HF_PREFIX = "mlx-community/"


def model_paths():
    candidates = [
        os.environ.get("VIDEO_FETCH_MODELS_DIR"),
        os.path.expanduser("~/.omlx/models/mlx-community"),
        "/Users/Shared/.omlx/models/mlx-community",
    ]
    for d in candidates:
        # 两个模型要在同一个目录里才用，避免一半本地一半下载
        if d and os.path.isdir(os.path.join(d, ASR_NAME)) and os.path.isdir(os.path.join(d, ALIGNER_NAME)):
            return os.path.join(d, ASR_NAME), os.path.join(d, ALIGNER_NAME)
    return HF_PREFIX + ASR_NAME, HF_PREFIX + ALIGNER_NAME


def duration(p):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p],
                         capture_output=True, text=True, check=True)
    return float(out.stdout)


def pauses(p):
    log = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", p, "-af", "silencedetect=n=-35dB:d=0.3",
                          "-f", "null", "-"], capture_output=True, text=True).stderr
    s = [float(x) for x in re.findall(r"silence_start: (-?[0-9.]+)", log)]
    e = [float(x) for x in re.findall(r"silence_end: ([0-9.]+)", log)]
    return list(zip(s, e))


def chunks(dur, gaps):
    out, t = [], 0.0
    while dur - t > CHUNK_MAX:
        cands = [g for g in gaps if t + CHUNK_MIN < (g[0] + g[1]) / 2 <= t + CHUNK_MAX]
        if cands:
            longest = max(cands, key=lambda g: g[1] - g[0])
            cut = (longest[0] + longest[1]) / 2
        else:
            # 找不到停顿就硬切；背景音乐盖住停顿时会这样，代价是切点附近一两个字可能对不准
            cut = t + CHUNK_MAX
        out.append((t, cut))
        t = cut
    out.append((t, dur))
    return out


def norm(s):
    return "".join(ch for ch in s.lower() if ch.isalnum())


def split_lines(text):
    # 先按句末标点断，过长的句子再按逗号类标点断
    lines = []
    for sent in re.findall(r"[^。！？!?；;]+[。！？!?；;]?", text):
        sent = sent.strip()
        if len(sent) <= LINE_MAX:
            lines.append(sent)
            continue
        cur = ""
        for part in re.findall(r"[^，,、：:]+[，,、：:]?", sent):
            if cur and len(cur) + len(part) > LINE_MAX:
                lines.append(cur)
                cur = ""
            cur += part
        if cur:
            lines.append(cur)
    return [l.strip() for l in lines if norm(l)]


def ts(t):
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def main():
    if len(sys.argv) != 3:
        sys.exit("用法：uv run transcribe.py <audio16k.wav> <输出目录>")
    audio, outdir = sys.argv[1], Path(sys.argv[2])

    # 放函数里：测试纯函数时不需要装 mlx-audio
    from mlx_audio.stt.utils import load_model

    asr_path, aligner_path = model_paths()
    log(f"模型：{asr_path} / {aligner_path}")
    plan = chunks(duration(audio), pauses(audio))
    asr = load_model(asr_path)
    aligner = load_model(aligner_path)

    texts, items = [], []  # items: [字, 起, 止]，绝对秒
    with tempfile.TemporaryDirectory(prefix="video-fetch-asr-") as work:
        for k, (a, b) in enumerate(plan):
            wav = os.path.join(work, f"c{k:02d}.wav")
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{a:.3f}", "-to", f"{b:.3f}", "-i", audio,
                            "-ac", "1", "-ar", "16000", wav], check=True)
            text = asr.generate(wav, language="zh").text.strip()
            texts.append(text)
            r = aligner.generate(audio=wav, text=text, language="Chinese")
            got = r.items if hasattr(r, "items") else r
            items += [[i.text, a + i.start_time, a + i.end_time] for i in got]
            log(f"块 {k}: {a:7.1f}-{b:7.1f} 秒，{len(got)} 项")

    full = "".join(texts)
    lines = split_lines(full)
    # 把每行的字映射到对齐项：两边都去掉标点后用 difflib 对齐
    line_str, owner = "", []
    for n, l in enumerate(lines):
        t = norm(l)
        line_str += t
        owner += [n] * len(t)
    heard, item_of = "", []
    for j, (t, _, _) in enumerate(items):
        t = norm(t)
        heard += t
        item_of += [j] * len(t)
    first, last = [None] * len(lines), [None] * len(lines)
    for blk in difflib.SequenceMatcher(None, line_str, heard, autojunk=False).get_matching_blocks():
        for d in range(blk.size):
            n, j = owner[blk.a + d], item_of[blk.b + d]
            first[n] = j if first[n] is None else first[n]
            last[n] = j

    srt, n_out = [], 0
    for n, l in enumerate(lines):
        if first[n] is None:
            continue  # 极少见：整行没对上，跳过而不是编造时间
        n_out += 1
        start, end = items[first[n]][1], items[last[n]][2]
        srt.append(f"{n_out}\n{ts(start)} --> {ts(end)}\n{l.rstrip('，,、：:；;。')}\n")
    (outdir / "transcript.srt").write_text("\n".join(srt), encoding="utf-8")
    # 纯文本稿：按句末标点分段，一句一行
    paras = re.sub(r"([。！？!?])", r"\1\n", full)
    (outdir / "transcript.txt").write_text(paras.strip() + "\n", encoding="utf-8")
    print(json.dumps({"lines": len(lines), "aligned": n_out}))


if __name__ == "__main__":
    main()
