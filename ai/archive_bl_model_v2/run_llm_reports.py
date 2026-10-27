"""5개 이미지 sLLM 검증 실행 및 소요시간 측정"""
import subprocess
import time
import os

BASE = os.path.dirname(os.path.abspath(__file__))
IMG_DIR = os.path.join(
    BASE,
    "Sample Data/025.OCR 데이터(금융 및 물류)/01-1.정식개방데이터"
    "/Training/01.원천데이터/TS_물류_3.선하증권_BL01",
)
OUT_DIR = os.path.join(BASE, "reports_image_pdf_llm_v2")
os.makedirs(OUT_DIR, exist_ok=True)

TASKS = [
    ("IMG_OCR_6_T_BL_000002.png", "lc_data/LC-2022-001.json", "COMPLIANT 예상"),
    ("IMG_OCR_6_T_BL_000003.png", "lc_data/LC-2022-002.json", "DISCREPANT - 선적일 초과"),
    ("IMG_OCR_6_T_BL_000006.png", "lc_data/LC-2022-005.json", "COMPLIANT 예상"),
    ("IMG_OCR_6_T_BL_000007.png", "lc_data/LC-2022-006.json", "DISCREPANT - 화물명세 키워드"),
    ("IMG_OCR_6_T_BL_000016.png", "lc_data/LC-2022-008.json", "DISCREPANT - 중량 초과"),
]

timings = []
total_start = time.time()

for idx, (img_file, lc_file, label) in enumerate(TASKS, 1):
    img_path = os.path.join(IMG_DIR, img_file)
    lc_path  = os.path.join(BASE, lc_file)

    print(f"\n{'━'*55}")
    print(f"[{idx}/5] {img_file}")
    print(f"        L/C: {lc_file}  ({label})")
    print(f"{'━'*55}")

    t0 = time.time()
    result = subprocess.run(
        [
            "python", "main.py",
            "--mode", "image",
            "--input", img_path,
            "--lc",   lc_path,
            "--output", OUT_DIR,
            "--llm",
        ],
        capture_output=True,
        text=True,
        cwd=BASE,
    )
    elapsed = time.time() - t0

    # 핵심 줄만 출력
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if any(kw in stripped for kw in [
            "검증 결과", "하자(ERROR)", "경고(WARNING)",
            "종합 판정", "오감지", "LLM 신규", "Llama 3 문맥",
            "❌", "✅", "⚠️",
        ]):
            print(" ", stripped)

    if result.returncode != 0:
        for line in result.stderr.splitlines()[-5:]:
            print("  [ERR]", line)

    ms = int(elapsed * 1000)
    timings.append((img_file, label, ms))
    print(f"\n  ⏱  소요시간: {ms:,} ms  ({elapsed:.1f}초)")

total_elapsed = time.time() - total_start
print(f"\n{'━'*55}")
print("소요시간 요약")
print(f"{'━'*55}")
for img_file, label, ms in timings:
    name = img_file.replace("IMG_OCR_6_T_BL_", "BL_")
    print(f"  {name:<30} {ms:>7,} ms  ({ms/1000:.1f}s)  [{label}]")
print(f"{'━'*55}")
print(f"  {'합계':<30} {int(total_elapsed*1000):>7,} ms  ({total_elapsed:.1f}s)")

# 생성된 PDF 목록
print(f"\n{'━'*55}")
print("생성된 PDF 파일 목록")
print(f"{'━'*55}")
for f in sorted(os.listdir(OUT_DIR)):
    if f.endswith(".pdf"):
        size = os.path.getsize(os.path.join(OUT_DIR, f))
        print(f"  {f}  ({size/1024:.1f} KB)")
