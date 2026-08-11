#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
book_to_video.py — 갓생북 은혜 «책 → 회고 영상» 변환기 (W2 책 마감의 핵심 부품)

갓생북 프로젝트에 모인 사진과 글을 **시간순 그대로** 슬라이드 영상으로 만든다.
로컬 실행(ffmpeg + Pillow) — AI·클라우드 비용 0.

사용법:
  python book_to_video.py <프로젝트폴더> [--title "여름성경학교 2026"] [--out video.mp4]
                          [--music bgm.mp3] [--sec 4] [--closing "함께해 주셔서 감사합니다"]

프로젝트 폴더 규칙:
  - 사진: *.jpg *.jpeg *.png — 파일명 순으로 정렬(갓생북 내보내기가 시간순 이름을 쓰면 그대로 흐름이 된다)
  - 글(선택): 사진과 같은 이름의 .txt (예: 001.jpg + 001.txt) → 그 장면의 자막이 된다
  - captions.json(선택): {"001.jpg": "첫날 도착!", ...} 형식도 지원
원칙:
  - 순서를 창작하지 않는다 — 시간순(파일명순) 그대로.
  - 아이들의 문장을 고치지 않는다 — 자막은 원문 그대로 싣는다.
"""
import argparse, json, subprocess, sys, tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1920, 1080
BG = (16, 18, 24)          # 어두운 남색 배경
FG = (245, 245, 240)       # 자막 색
FONT_CANDIDATES = [        # 한글 폰트 — 위에서부터 시도 (Windows/mac/Linux)
    r"C:\Windows\Fonts\malgunbd.ttf", r"C:\Windows\Fonts\malgun.ttf",
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
]

def find_font(size):
    for p in FONT_CANDIDATES:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    print("[경고] 한글 폰트를 찾지 못했다 — 자막이 깨질 수 있다. FONT_CANDIDATES에 경로를 추가하라.")
    return ImageFont.load_default()

def wrap_text(draw, text, font, max_w):
    lines, line = [], ""
    for ch in text:
        if ch == "\n" or draw.textlength(line + ch, font=font) > max_w:
            lines.append(line); line = "" if ch == "\n" else ch
        else:
            line += ch
    if line: lines.append(line)
    return lines[:4]  # 자막 최대 4줄 — 넘치면 자르지 않고 다음 규칙: 원문 보존 우선이므로 폰트를 줄인다

def make_slide(photo: Path | None, caption: str, out: Path, title_mode=False):
    """사진 + 자막(하단 띠)을 1920x1080 슬라이드로 합성. photo=None이면 텍스트 카드."""
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    if photo is not None:
        ph = Image.open(photo).convert("RGB")
        ph.thumbnail((W, H - (160 if caption else 0)))  # 자막 공간 확보
        img.paste(ph, ((W - ph.width) // 2, ((H - (160 if caption else 0)) - ph.height) // 2))
    if caption:
        size = 84 if title_mode else 54
        font = find_font(size)
        maxw = W - 240
        lines = wrap_text(d, caption, font, maxw)
        while len(lines) > (2 if title_mode else 4) and size > 30:  # 원문 보존: 자르지 말고 줄인다
            size -= 6; font = find_font(size); lines = wrap_text(d, caption, font, maxw)
        lh = size + 14
        block_h = lh * len(lines) + 40
        y0 = (H - block_h) // 2 if title_mode or photo is None else H - block_h - 20
        if photo is not None and not title_mode:
            d.rectangle([0, y0 - 10, W, H], fill=(0, 0, 0))  # 자막 띠
        y = y0 + 20
        for ln in lines:
            x = (W - d.textlength(ln, font=font)) // 2
            d.text((x, y), ln, font=font, fill=FG); y += lh
    img.save(out, "JPEG", quality=92)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project"); ap.add_argument("--title", default="")
    ap.add_argument("--out", default="recap_video.mp4"); ap.add_argument("--music", default="")
    ap.add_argument("--sec", type=float, default=4.0)
    ap.add_argument("--closing", default="함께해 주셔서 감사합니다")
    a = ap.parse_args()

    proj = Path(a.project)
    photos = sorted([p for p in proj.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png")])
    if not photos:
        sys.exit(f"[중단] {proj} 에 사진이 없다.")
    caps = {}
    cj = proj / "captions.json"
    if cj.exists():
        caps = json.loads(cj.read_text(encoding="utf-8"))
    for p in photos:  # 개별 .txt가 있으면 우선
        t = p.with_suffix(".txt")
        if t.exists():
            caps[p.name] = t.read_text(encoding="utf-8").strip()

    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td); n = 0
        def slide(photo, cap, title=False):
            nonlocal n
            make_slide(photo, cap, tdp / f"s{n:04d}.jpg", title_mode=title); n += 1
        if a.title:
            slide(None, a.title, title=True)                       # 여는 타이틀
        for p in photos:
            slide(p, caps.get(p.name, ""))                          # 시간순 장면들
        if a.closing:
            slide(None, a.closing, title=True)                      # 닫는 카드
        # concat 목록 (마지막 프레임 규칙 포함)
        lst = tdp / "list.txt"
        entries = [f"file 's{i:04d}.jpg'\nduration {a.sec}" for i in range(n)]
        entries.append(f"file 's{n-1:04d}.jpg'")
        lst.write_text("\n".join(entries), encoding="utf-8")
        cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst)]
        if a.music:
            cmd += ["-stream_loop", "-1", "-i", a.music]
        cmd += ["-vf", "scale=1920:1080,format=yuv420p", "-r", "30", "-c:v", "libx264", "-preset", "medium"]
        if a.music:
            cmd += ["-c:a", "aac", "-shortest", "-af", "afade=t=out:st=%f:d=2" % max(0, n * a.sec - 2)]
        cmd += [a.out]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            sys.exit(f"[실패] ffmpeg 오류:\n{r.stderr[-1500:]}")
    dur = n * a.sec
    print(f"[완료] {a.out} — 장면 {n}개, 약 {dur:.0f}초. 상영 전 처음부터 끝까지 재생 확인하라(검수는 사람 몫).")

if __name__ == "__main__":
    main()
