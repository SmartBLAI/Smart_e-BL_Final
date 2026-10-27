/**
 * `/report` 응답(`wireReport.ts`) → 화면이 쓰는 모양 번역기.
 *
 * S7은 이미 S4의 판정 카드(`VerdictCard`)·검사못한목록(`SkippedList`)을 그대로
 * 재사용하고 있어서, `risks[]`를 `adapters.ts`의 `Verdict`로, `unchecked[]`를
 * 같은 `SkippedRuleView`로 옮기기만 하면 새 컴포넌트 없이 붙습니다.
 *
 * ⚠ `risks[]`의 조치문(action_hint)은 지어내지 않고 비웁니다 — 백엔드
 *   `recommendations[]`가 조치문을 담고 있긴 하지만, `risks`와 `recommendations`는
 *   서로 다른 정렬 기준으로 만들어져 있어(`report/builder.py`의 `_risks`·
 *   `_recommendations`) 같은 인덱스가 같은 위반이라는 보장이 없습니다. 근거
 *   없는 짝짓기로 엉뚱한 조치문을 붙이는 것보다, 없는 채로 두는 편이 낫습니다.
 */

import { toScreenFieldName, toSkipped, type SkippedRuleView } from './adapters';
import type { DefectPrediction, Severity, Verdict } from '../types/domain';
import type { WireSeverity } from './wire';
import type { WireReportResponse, WireRiskItem } from './wireReport';

const SEVERITY_MAP: Record<WireSeverity, Severity> = {
  critical: 'Critical',
  warning: 'Warning',
  info: 'Info',
};

export interface ReportView {
  verdicts: Verdict[];
  prediction: DefectPrediction;
  unchecked: SkippedRuleView[];
  /** "xgboost-v1" = 학습 모델, "rules-v1" = 룰 가중치 합 (WirePrediction.model과 같은 뜻) */
  predictionModel: string;
}

function toVerdict(
  r: WireRiskItem,
  index: number,
  judgedAt: string,
  ruleVersion: string,
  modelVersion: string,
): Verdict {
  return {
    verdict_id: `${r.rule_id}#${index}`,
    rule_id: r.rule_id,
    target_fields: r.fields.map(toScreenFieldName),
    result: 'VIOLATION',
    severity: SEVERITY_MAP[r.severity],
    message: r.message,
    action_hint: null,
    evidence: { clause_text: r.source },
    judged_at: judgedAt,
    rule_version: ruleVersion,
    model_version: modelVersion,
  };
}

export function toReportView(res: WireReportResponse, receivedAt: string): ReportView {
  const ruleVersion = res.summary.rule_catalog?.label ?? 'unknown';

  return {
    verdicts: res.risks.map((r, i) => toVerdict(r, i, receivedAt, ruleVersion, res.summary.model)),
    prediction: {
      probability: res.summary.defect_probability,
      // 백엔드에 SHAP 기여도가 없습니다 (F3와 같은 문서화된 공백)
      top_factors: [],
      deferred_count: res.unchecked.length,
    },
    unchecked: res.unchecked.map(toSkipped),
    predictionModel: res.summary.model,
  };
}
