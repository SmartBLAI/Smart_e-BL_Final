#!/bin/bash
# 4개 청크 JSON 파일 생성 완료 대기 후 자동 병합

CHUNK_DIR="/Users/ethanyang/Documents/B_L_model v2/reports_eval_2000"
LOG="$CHUNK_DIR/merge.log"
CHUNKS=("chunk_0" "chunk_1" "chunk_2" "chunk_3")

echo "[$(date)] 청크 JSON 완료 대기 시작..." | tee "$LOG"

while true; do
  all_done=true
  for chunk in "${CHUNKS[@]}"; do
    json="$CHUNK_DIR/$chunk/eval_report.json"
    if [ ! -f "$json" ]; then
      all_done=false
      break
    fi
  done

  if $all_done; then
    echo "[$(date)] 모든 청크 완료 감지. 병합 시작..." | tee -a "$LOG"
    break
  fi

  # 30초마다 진행 상태 출력
  for chunk in "${CHUNKS[@]}"; do
    count=$(grep -c "평가 중" "$CHUNK_DIR/$chunk/run.log" 2>/dev/null || echo "?")
    json="$CHUNK_DIR/$chunk/eval_report.json"
    status="진행중($count/500)"
    [ -f "$json" ] && status="완료"
    echo "  $chunk: $status"
  done | tee -a "$LOG"

  sleep 30
done

cd "/Users/ethanyang/Documents/B_L_model v2"
python3.13 merge_eval_chunks.py 2>&1 | tee -a "$LOG"
echo "[$(date)] 병합 완료!" | tee -a "$LOG"
