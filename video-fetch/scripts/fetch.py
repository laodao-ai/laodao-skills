# /// script
# requires-python = ">=3.10"
# dependencies = ["yt-dlp==2026.11.23", "playwright==1.65.2"]
# ///
"""下载视频、抽音频、转写口播稿。用法见 SKILL.md。

退出码：0 全部成功；2 视频已下载但转写失败；1 下载失败。
"""
import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

from platforms import FetchError, bilibili, douyin  # noqa: E402

PLATFORMS = [bilibili, douyin]

# 抖音 App 分享文本是「文字 + 短链 + 口令」，只取第一个链接
URL_RE = re.compile(r"https?://[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+")


def extract_url(text):
    found = URL_RE.search(text)
    return found.group(0) if found else None


def find_platform(url):
    for p in PLATFORMS:
        if p.match(url):
            return p
    return None


def run_ffmpeg(args):
    return subprocess.run(["ffmpeg", "-y", "-v", "error", *args], capture_output=True, text=True)


def extract_audio(outdir):
    video = str(outdir / "video.mp4")
    # 先原样拷贝，不重新编码；音轨不是 mp4 能装的编码时再转 aac
    r = run_ffmpeg(["-i", video, "-vn", "-c:a", "copy", str(outdir / "audio.m4a")])
    if r.returncode != 0:
        r = run_ffmpeg(["-i", video, "-vn", "-c:a", "aac", str(outdir / "audio.m4a")])
    if r.returncode != 0:
        raise FetchError(f"抽音频失败：{r.stderr.strip()}。检查 video.mp4 是否有音轨。")


def make_wav16k(outdir):
    wav = outdir / "audio16k.wav"
    r = run_ffmpeg(["-i", str(outdir / "video.mp4"), "-vn", "-ac", "1", "-ar", "16000", str(wav)])
    if r.returncode != 0:
        raise FetchError(f"生成 16k 音频失败：{r.stderr.strip()}")
    return wav


def transcribe(wav, outdir):
    """返回 meta.json 里的 transcript 字段。"""
    cmd = ["uv", "run", str(SCRIPTS_DIR / "transcribe.py"), str(wav), str(outdir)]
    try:
        r = subprocess.run(cmd, stdout=subprocess.PIPE, text=True)
    except OSError as e:
        return {"status": "failed", "lines": 0, "error": f"无法运行 uv：{e}"}
    if r.returncode != 0:
        return {"status": "failed", "lines": 0, "error": f"transcribe.py 退出码 {r.returncode}，原因见上方输出"}
    try:
        result = json.loads(r.stdout.strip().splitlines()[-1])
    except (IndexError, ValueError):
        return {"status": "failed", "lines": 0, "error": f"无法解析转写结果：{r.stdout[-200:]!r}"}
    return {"status": "ok", "lines": result["aligned"], "error": ""}


def main():
    ap = argparse.ArgumentParser(description="下载 B站/抖音视频并转写口播稿")
    ap.add_argument("input", help="视频链接，或抖音 App 复制的整段分享文本")
    ap.add_argument("--output", help="输出目录；默认在当前目录建 <平台>-<视频ID>/")
    ap.add_argument("--cookies", help="Netscape 格式 cookies.txt（目前只有 B站用）")
    ap.add_argument("--cookies-from-browser", help="从浏览器读 cookie，如 chrome（目前只有 B站用）")
    ap.add_argument("--no-asr", action="store_true", help="只下载，不转写")
    opts = ap.parse_args()

    url = extract_url(opts.input)
    if url is None:
        sys.exit("错误：输入里没有找到 http(s) 链接。请给出视频链接或抖音分享文本。")
    platform = find_platform(url)
    if platform is None:
        sys.exit(f"错误：不支持这个链接：{url}\n目前支持：{', '.join(p.NAME for p in PLATFORMS)}。")

    outdir = None  # resolve 失败时还没有输出目录
    try:
        video_id, canonical = platform.resolve(url)
        outdir = Path(opts.output) if opts.output else Path.cwd() / f"{platform.NAME}-{video_id}"
        if outdir.exists() and any(outdir.iterdir()):
            # 没有 meta.json 说明是上次失败留下的半成品
            leftover = "" if (outdir / "meta.json").exists() else "（没有 meta.json，是上次失败留下的部分文件）"
            sys.exit(f"错误：输出目录 {outdir} 已存在且不为空{leftover}，不会覆盖。换一个 --output，或先清理该目录。")
        outdir.mkdir(parents=True, exist_ok=True)
        print(f"{platform.NAME} {video_id} -> {outdir}", file=sys.stderr)

        info = platform.fetch(canonical, video_id, outdir, opts)
        extract_audio(outdir)
        wav = make_wav16k(outdir) if not opts.no_asr else None
    except FetchError as e:
        hint = f"\n输出目录 {outdir} 里可能留有部分文件，重跑前清理它或换 --output。" if outdir else ""
        sys.exit(f"错误：{e}{hint}")

    if opts.no_asr:
        transcript = {"status": "skipped", "lines": 0, "error": ""}
    else:
        transcript = transcribe(wav, outdir)
        wav.unlink()

    meta = {
        "platform": platform.NAME,
        "id": video_id,
        "url": canonical,
        "title": info["title"],
        "author": info["author"],
        "duration": info["duration"],
        "description": info["description"],
        "fetched_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "platform_subtitles": info["platform_subtitles"],
        "transcript": transcript,
    }
    (outdir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"完成：{outdir}（转写：{transcript['status']}，{transcript['lines']} 行）")
    if transcript["status"] == "failed":
        print(f"转写失败：{transcript['error']}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
