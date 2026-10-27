"""
B/L AI 하자 검증 시스템 - 메인 진입점

사용 예시:
  # Rule-based만 (기본)
  python main.py --mode json --input <json_path> --lc lc_sample.json

  # Llama 3 sLLM 보완 포함
  python main.py --mode json --input <json_path> --lc lc_sample.json --llm

  # 배치 처리 (Rule-based)
  python main.py --mode batch --max 5

  # 배치 처리 (Llama 3 포함)
  python main.py --mode batch --max 5 --llm --llm-model llama3.2

  # 이미지 OCR vs 라벨링 JSON 정확도 평가 (배치)
  python main.py --mode eval --max 10 --output reports_eval/

  # 이미지 OCR vs 라벨링 JSON 정확도 평가 (단일)
  python main.py --mode eval-single --input <image_path> --label <label_json_path>

  # 이미지 디렉토리/라벨 디렉토리 직접 지정
  python main.py --mode eval --image-dir <img_dir> --label-dir <lbl_dir> --max 20

  # ollama 상태 확인
  python main.py --check-llm
"""

import argparse
import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from config import TRAINING_LABEL_DIR, TRAINING_IMAGE_DIR
from src.pipeline import BLVerificationPipeline
from src.validator import LCConditions


def load_lc(lc_path: str) -> LCConditions:
    with open(lc_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return LCConditions.from_dict(data)


def cmd_check_llm(args):
    """ollama 서버 및 모델 상태 확인"""
    from src.sllm_judge import LlamaJudge
    model = args.llm_model or "llama3.2"
    judge = LlamaJudge(model=model, host=args.llm_host or "http://localhost:11434")

    print(f"\n[ollama 상태 확인]")
    print(f"  서버 주소: {judge.host}")
    print(f"  대상 모델: {model}")

    models = judge.list_models()
    if not models:
        print("\n  ❌ ollama 서버에 연결할 수 없습니다.")
        print("\n  [설치 및 실행 방법]")
        print("  1. ollama 설치  : https://ollama.com")
        print(f"  2. 모델 다운로드: ollama pull {model}")
        print("  3. 서버 시작    : ollama serve")
        return

    print(f"\n  ✅ ollama 서버 연결 성공")
    print(f"  설치된 모델: {', '.join(models)}")

    base = model.split(":")[0]
    if any(m.startswith(base) for m in models):
        print(f"  ✅ '{model}' 모델 사용 가능")
    else:
        print(f"  ❌ '{model}' 모델 미설치")
        print(f"  설치 명령: ollama pull {model}")


def cmd_json(args, pipeline: BLVerificationPipeline):
    lc = load_lc(args.lc) if args.lc else None
    result = pipeline.run_from_json(args.input, lc=lc, output_dir=args.output)
    _print_text_report(pipeline, args.input, lc, use_llm=args.llm)


def cmd_image(args, pipeline: BLVerificationPipeline):
    lc = load_lc(args.lc) if args.lc else None
    result = pipeline.run_from_image(
        args.input, lc=lc, output_dir=args.output, preprocess=not args.no_preprocess
    )
    _print_text_report(pipeline, args.input, lc, use_llm=args.llm, is_image=True)


def cmd_eval(args, pipeline: BLVerificationPipeline):
    """이미지 OCR vs 라벨링 JSON 정확도 평가 (배치)"""
    image_dir = args.image_dir or TRAINING_IMAGE_DIR
    label_dir = args.label_dir or TRAINING_LABEL_DIR
    max_files = args.max or 0
    file_offset = getattr(args, "offset", 0) or 0

    print(f"\n[eval 모드] 이미지 OCR vs 라벨링 JSON 정확도 평가")
    print(f"  이미지 디렉토리: {image_dir}")
    print(f"  라벨 디렉토리 : {label_dir}")
    if max_files:
        print(f"  최대 처리 수  : {max_files}건")
    if file_offset:
        print(f"  시작 오프셋   : {file_offset}번째부터")
    print()

    result = pipeline.run_eval_batch(
        image_dir=image_dir,
        label_dir=label_dir,
        output_dir=args.output,
        max_files=max_files,
        file_offset=file_offset,
    )

    print(f"\n{'='*50}")
    print(f"평가 완료: {result['sample_count']}건")
    print(f"  필드 추출 정확도: {result['overall_field_accuracy']:.1%}")
    if result.get("overall_text_f1") is not None:
        print(f"  텍스트 F1      : {result['overall_text_f1']:.1%}")
    if args.output:
        print(f"  리포트 저장    : {args.output}/")
    print(f"{'='*50}")


def cmd_eval_single(args, pipeline: BLVerificationPipeline):
    """단일 이미지-라벨 쌍 정확도 평가"""
    if not args.input:
        raise ValueError("--mode eval-single 에는 --input (이미지 경로) 이 필요합니다")
    if not args.label:
        raise ValueError("--mode eval-single 에는 --label (라벨 JSON 경로) 이 필요합니다")

    print(f"\n[eval-single 모드]")
    print(f"  이미지: {args.input}")
    print(f"  라벨  : {args.label}")

    result = pipeline.run_eval_single(
        image_path=args.input,
        label_path=args.label,
        output_dir=args.output,
    )

    print(f"\n{'='*50}")
    print(f"평가 완료: {result['image_id']}")
    print(f"  필드 정확도: {result['field_accuracy']:.1%}  ({result['field_matched']}/{result['field_total']})")
    if result.get("text_metrics"):
        tm = result["text_metrics"]
        print(f"  텍스트 F1  : {tm['f1']:.1%}  (precision={tm['precision']:.1%}, recall={tm['recall']:.1%})")
    if args.output:
        print(f"  리포트 저장: {args.output}/")
    print(f"{'='*50}")


def cmd_batch(args, pipeline: BLVerificationPipeline):
    label_dir = args.input or TRAINING_LABEL_DIR
    lc = load_lc(args.lc) if args.lc else None
    max_files = args.max or 5

    mode_tag = " [Rule-based + Llama 3]" if args.llm else " [Rule-based]"
    print(f"\n[배치 모드]{mode_tag}")
    print(f"디렉토리: {label_dir}")
    print(f"처리 파일: {max_files}건\n")

    results = pipeline.run_batch(label_dir, lc=lc, output_dir=args.output, max_files=max_files)

    total = len(results)
    valid = sum(1 for r in results if r.get("is_valid"))
    errors = sum(1 for r in results if "error" in r)
    defective = total - valid - errors

    print(f"\n{'='*50}")
    print(f"배치 처리 완료: {total}건")
    print(f"  정상     : {valid}건")
    print(f"  하자 발견: {defective}건")
    print(f"  처리 실패: {errors}건")
    if args.output:
        print(f"  리포트 저장: {args.output}/")
    print(f"{'='*50}")


def _print_text_report(pipeline, source, lc, use_llm=False, is_image=False):
    """콘솔 텍스트 리포트 출력"""
    from src.field_parser import FieldParser
    from src.ocr_extractor import OCRExtractor
    from src.validator import BLValidator

    try:
        if is_image:
            ocr = OCRExtractor().from_image(source)
        else:
            ocr = OCRExtractor().from_json(source)

        bl = FieldParser().parse(ocr)
        lc_obj = lc or LCConditions()
        rule_result = BLValidator().validate(bl, lc_obj)

        llm_data = None
        if use_llm and pipeline._judge is not None:
            try:
                from src.sllm_judge import merge_results
                judgment = pipeline._judge.judge(bl, lc_obj, rule_result)
                llm_data = merge_results(rule_result, judgment)
            except RuntimeError:
                pass  # ollama 미접속 시 rule-based 결과만 출력

        text = pipeline.reporter.to_text(bl, lc_obj, rule_result, llm_data=llm_data)
        print(text)

    except Exception as e:
        print(f"[텍스트 리포트 생성 실패: {e}]")


def main():
    parser = argparse.ArgumentParser(
        description="B/L AI 하자 검증 시스템 (Rule-based + Llama 3 sLLM)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--mode",
        choices=["json", "image", "batch", "eval", "eval-single"],
        default="batch",
        help="실행 모드 (기본값: batch). eval=이미지OCR vs 라벨링JSON 배치 정확도평가",
    )
    parser.add_argument("--input", "-i", help="입력 파일 또는 디렉토리 경로 (eval-single: 이미지 경로)")
    parser.add_argument("--lc", help="L/C 조건 JSON 파일 경로")
    parser.add_argument("--label", help="라벨링 JSON 파일 경로 (eval-single 전용)")
    parser.add_argument("--image-dir", help="이미지 디렉토리 경로 (eval 전용, 기본: TRAINING_IMAGE_DIR)")
    parser.add_argument("--label-dir", help="라벨링 JSON 디렉토리 경로 (eval 전용, 기본: TRAINING_LABEL_DIR)")
    parser.add_argument("--output", "-o", help="리포트 출력 디렉토리")
    parser.add_argument("--max", type=int, default=0, help="배치 최대 처리 파일 수 (기본: 0=전체)")
    parser.add_argument("--offset", type=int, default=0, help="배치 시작 파일 인덱스 (병렬 분할 시 사용)")
    parser.add_argument("--no-preprocess", action="store_true", help="이미지 전처리 생략")
    parser.add_argument("--gpu", action="store_true", help="GPU 사용 (PaddleOCR)")

    # sLLM 옵션
    llm_group = parser.add_argument_group("Llama 3 sLLM 옵션")
    llm_group.add_argument(
        "--llm", action="store_true",
        help="Llama 3 sLLM 문맥 판단 활성화 (ollama 서버 필요)",
    )
    llm_group.add_argument(
        "--llm-model", default="llama3.2",
        help="ollama 모델명 (기본: llama3.2, 고정밀: llama3)",
    )
    llm_group.add_argument(
        "--llm-host", default="http://localhost:11434",
        help="ollama 서버 주소 (기본: http://localhost:11434)",
    )
    llm_group.add_argument(
        "--llm-timeout", type=int, default=120,
        help="LLM 응답 최대 대기 시간(초) (기본: 120)",
    )
    llm_group.add_argument(
        "--check-llm", action="store_true",
        help="ollama 서버·모델 상태 확인 후 종료",
    )

    args = parser.parse_args()

    if args.check_llm:
        cmd_check_llm(args)
        return

    pipeline = BLVerificationPipeline(
        use_gpu=args.gpu,
        use_llm=args.llm,
        llm_model=args.llm_model,
        llm_host=args.llm_host,
        llm_timeout=args.llm_timeout,
    )

    if args.mode == "json":
        if not args.input:
            parser.error("--mode json 에는 --input 이 필요합니다")
        cmd_json(args, pipeline)
    elif args.mode == "image":
        if not args.input:
            parser.error("--mode image 에는 --input 이 필요합니다")
        cmd_image(args, pipeline)
    elif args.mode == "eval":
        cmd_eval(args, pipeline)
    elif args.mode == "eval-single":
        cmd_eval_single(args, pipeline)
    else:
        cmd_batch(args, pipeline)


if __name__ == "__main__":
    main()
