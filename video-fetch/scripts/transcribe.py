# /// script
# requires-python = ">=3.10"
# dependencies = ["mlx-audio==0.6.5"]
# ///
"""把一段音频转成逐句字幕 transcript.srt 和口播稿 transcript.txt。

用法：uv run transcribe.py <audio16k.wav> <输出目录> [--lang <Qwen3 语言名>]，默认 Chinese
流程：按停顿切成不超过 CHUNK_MAX 秒的块（ForcedAligner 一次只能处理约 3 分钟）
     -> Qwen3-ASR 转写（带标点）-> Qwen3-ForcedAligner 给每个字时间
     -> 按标点断句，每句的首末字时间写成一条字幕。
最后一行 stdout 是 JSON：{"lines": N, "aligned": M}；进度写 stderr。
"""
import argparse
import difflib
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

CHUNK_MIN, CHUNK_MAX = 60.0, 150.0
LINE_MAX = 22  # 一条字幕超过这么多字，就在逗号处再断
LINE_MAX_SPACED = 42  # 有空格语言的每条字幕字符上限
# 中日韩粤不用空格分词：块文本直接拼接
UNSPACED_LANGUAGES = {"Chinese", "Japanese", "Korean", "Cantonese"}
AUTO = "auto"  # 让 ASR 自己识别语言

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


def is_unspaced(lang):
    return lang in UNSPACED_LANGUAGES


def wrap_words(text, limit):
    """按词换行，每行不超过 limit；单个词超长时原样成行。"""
    out, cur = [], ""
    for word in text.split():
        if cur and len(cur) + 1 + len(word) > limit:
            out.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}" if cur else word
    if cur:
        out.append(cur)
    # 末行只剩一个词时并回上一行：孤词单独一条字幕常常时长为零，读着也断
    if len(out) >= 2 and " " not in out[-1]:
        orphan = out.pop()
        out[-1] = f"{out[-1]} {orphan}"
    return out


def split_lines_spaced(text):
    lines = []
    # 句末标点后跟空白才断，避免拆开小数点和缩写里的点
    for sent in re.split(r"(?<=[.!?;])\s+", text.strip()):
        sent = sent.strip()
        if len(sent) <= LINE_MAX_SPACED:
            lines.append(sent)
            continue
        cur = ""
        for part in re.split(r"(?<=[,:])\s+", sent):
            if cur and len(cur) + 1 + len(part) > LINE_MAX_SPACED:
                lines.append(cur)
                cur = ""
            cur = f"{cur} {part}" if cur else part
        if cur:
            lines.append(cur)
    out = []
    for l in lines:
        # 逗号断完仍超长的，再按词换行
        out += wrap_words(l, LINE_MAX_SPACED) if len(l) > LINE_MAX_SPACED and " " in l else [l]
    return [l.strip() for l in out if norm(l)]


def split_lines(text, lang="Chinese"):
    if not is_unspaced(lang):
        return split_lines_spaced(text)
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


def split_sentences_txt(full, lang="Chinese"):
    """口播稿纯文本：一句一行。"""
    if is_unspaced(lang):
        return re.sub(r"([。！？!?])", r"\1\n", full).strip()
    # 英文句号后跟空白才断；中文标点（混合内容）照常断
    return re.sub(r"([。！？]|[.!?](?=\s|$))\s*", r"\1\n", full).strip()


def ts(t):
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def main():
    ap = argparse.ArgumentParser(description="音频转逐句字幕与口播稿")
    ap.add_argument("audio", help="16k 单声道 wav")
    ap.add_argument("outdir", help="输出目录")
    ap.add_argument("--lang", default="Chinese", help=f"Qwen3 语言名，如 Chinese、English；{AUTO} 为自动识别；默认 Chinese")
    args = ap.parse_args()
    audio, outdir, lang = args.audio, Path(args.outdir), args.lang

    # 放函数里：测试纯函数时不需要装 mlx-audio
    from mlx_audio.stt.utils import load_model

    asr_path, aligner_path = model_paths()
    log(f"模型：{asr_path} / {aligner_path}")
    plan = chunks(duration(audio), pauses(audio))
    asr = load_model(asr_path)
    aligner = load_model(aligner_path)

    texts, items = [], []  # items: [字, 起, 止]，绝对秒
    detected = []  # lang 为 auto 时，每块识别出的语言
    with tempfile.TemporaryDirectory(prefix="video-fetch-asr-") as work:
        for k, (a, b) in enumerate(plan):
            wav = os.path.join(work, f"c{k:02d}.wav")
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{a:.3f}", "-to", f"{b:.3f}", "-i", audio,
                            "-ac", "1", "-ar", "16000", wav], check=True)
            if lang == AUTO:
                # 不指定语言时模型自己识别，识别结果在 language 列表里
                res = asr.generate(wav)
                langs = res.language if isinstance(res.language, list) else [res.language]
                chunk_lang = langs[0] if langs and langs[0] else "Chinese"
                detected.append(chunk_lang)
            else:
                res = asr.generate(wav, language=lang)
                chunk_lang = lang
            text = res.text.strip()
            texts.append(text)
            r = aligner.generate(audio=wav, text=text, language=chunk_lang)
            got = r.items if hasattr(r, "items") else r
            items += [[i.text, a + i.start_time, a + i.end_time] for i in got]
            log(f"块 {k}: {a:7.1f}-{b:7.1f} 秒，{chunk_lang}，{len(got)} 项")

    if lang == AUTO:
        # 拼接与断句按多数块的语言；混语视频以主语言为准
        lang = Counter(detected).most_common(1)[0][0]
        log(f"自动识别语言：{lang}")
    full =("" if is_unspaced(lang) else " ").join(texts)
    lines = split_lines(full, lang)
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
    # 有空格语言的句号是英文 .，也一并去掉行尾
    strip_chars = "，,、：:；;。" if is_unspaced(lang) else "，,、：:；;。."
    for n, l in enumerate(lines):
        if first[n] is None:
            continue  # 极少见：整行没对上，跳过而不是编造时间
        n_out += 1
        start, end = items[first[n]][1], items[last[n]][2]
        srt.append(f"{n_out}\n{ts(start)} --> {ts(end)}\n{l.rstrip(strip_chars)}\n")
    (outdir / "transcript.srt").write_text("\n".join(srt), encoding="utf-8")
    # 纯文本稿：按句末标点分段，一句一行
    (outdir / "transcript.txt").write_text(split_sentences_txt(full, lang) + "\n", encoding="utf-8")
    print(json.dumps({"lines": len(lines), "aligned": n_out, "language": lang}))


if __name__ == "__main__":
    main()
