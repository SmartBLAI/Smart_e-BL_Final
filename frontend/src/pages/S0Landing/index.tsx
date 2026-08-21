import { ArrowRight, Ship } from 'lucide-react';
import { Link } from 'react-router-dom';
import heroPortImage from '../../assets/hero-port.webp';

/**
 * 랜딩 페이지 — 서비스 소개 + 대시보드 진입.
 *
 * ⚠ 로그인 기능은 없습니다. "작성 시작하기"는 그냥 /shipments 로 이동하는
 *   링크일 뿐이고, 인증·계정 개념 자체가 아직 없습니다. 나중에 로그인이
 *   생기면 이 버튼이 그 흐름의 시작점이 됩니다.
 *
 * 이 화면만 NavBar를 두르지 않습니다 (App.tsx의 AppLayout 밖에 있음) —
 * 로고가 별도 상단 바가 아니라 히어로 사진 위에 얹혀 있어서, NavBar를
 * 씌우면 로고 두 개가 겹쳐 보입니다.
 *
 * ⚠ 로고 이미지: 시안은 로고 파일(logo-warm.png)을 히어로에 얹지만, 그
 *   파일을 디자인 도구에서 받아오다 256KB 제한에 걸려 깨진 채로 왔습니다
 *   (PNG 마무리 조각 없음). 진짜 로고 파일이 생기기 전까지는 기존
 *   BrandBadge(남색 알약 + 배 아이콘)를 그대로 히어로에 얹어 씁니다.
 */

/** 히어로 아래 번호 매긴 기능 목록. 문구는 실제 구현 범위에 맞췄습니다 (없는 기능 홍보 금지) */
const FEATURES: { title: string; body: string }[] = [
  { title: '항목 자동 추출', body: '서류 4종에서 26개 항목을 뽑고 출처를 표시합니다.' },
  { title: 'UCP600 기준 판정', body: '위반·주의·참고로 나누어 근거와 함께 제시합니다.' },
  { title: '현실 데이터 대조', body: '통관·선박 실적과의 차이를 경보로 알립니다.' },
];

/** 헤더·본문·푸터가 공유하는 좌우 여백 */
const GUTTER = 'var(--space-6)';

export function S0Landing() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', flex: 1, textAlign: 'left' }}>
      {/* ── 히어로: 항만 사진 전면 배경 ── */}
      <div style={{ position: 'relative', minHeight: 440, display: 'flex', overflow: 'hidden' }}>
        <img
          src={heroPortImage}
          alt=""
          aria-hidden="true"
          style={{
            position: 'absolute',
            inset: 0,
            width: '100%',
            height: '100%',
            objectFit: 'cover',
            filter: 'saturate(0.62) contrast(1.04)',
          }}
        />

        {/* 사진 위 오버레이 3장 — 전부 --brand-primary(rgb 30,58,95)나 순수
            검정에서만 뽑았습니다. 시안의 색(#1d4a7a 계열)을 베끼지 않고
            기존 브랜드 색만 우려서 썼습니다 (CLAUDE.md 1번) */}
        <div
          style={{
            position: 'absolute',
            inset: 0,
            backgroundColor: 'var(--brand-primary)',
            opacity: 0.42,
            mixBlendMode: 'multiply',
            pointerEvents: 'none',
          }}
        />
        <div
          style={{
            position: 'absolute',
            inset: 0,
            background:
              'linear-gradient(180deg, rgba(30,58,95,0.5) 0%, rgba(30,58,95,0.08) 34%, rgba(30,58,95,0.88) 100%)',
            pointerEvents: 'none',
          }}
        />
        <div
          style={{
            position: 'absolute',
            inset: 0,
            background: 'linear-gradient(180deg, rgba(0,0,0,0.3) 0%, rgba(0,0,0,0) 20%)',
            pointerEvents: 'none',
          }}
        />

        {/* 히어로 내용 — 위 오버레이보다 위 레이어(position: relative)에 둡니다 */}
        <div
          style={{
            position: 'relative',
            flex: 1,
            display: 'flex',
            flexDirection: 'column',
            padding: `var(--space-4) ${GUTTER} var(--space-6)`,
            boxSizing: 'border-box',
          }}
        >
          <BrandBadge />

          <div
            style={{
              marginTop: 'auto',
              display: 'flex',
              flexDirection: 'column',
              gap: 'var(--space-4)',
              maxWidth: 640,
            }}
          >

            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
              <h1
                style={{
                  margin: 0,
                  fontSize: 44,
                  fontWeight: 700,
                  lineHeight: 1.2,
                  letterSpacing: '-1.4px',
                  color: '#fff',
                  wordBreak: 'keep-all',
                }}
              >
                B/L 작성, 더 정확하게.
              </h1>
              <p
                style={{
                  margin: 0,
                  fontSize: 16,
                  fontWeight: 500,
                  lineHeight: 1.6,
                  color: 'rgba(255,255,255,0.92)',
                  wordBreak: 'keep-all',
                  maxWidth: 480,
                }}
              >
                관련 서류를 비교해 작성 과정의 오류와 누락을 미리 확인합니다.
              </p>
            </div>

            {/* 사이트 어디서나 쓰는 .btn-primary(남색 배경)를 여기 그대로 쓰면
                남색 사진 위에서 거의 안 보입니다. 이 버튼만 반대로 밝은
                배경 + 남색 글자로 둡니다 — 새 색이 아니라 기존 토큰을
                뒤집어 쓴 것뿐입니다 */}
            <Link
              to="/shipments"
              style={{
                display: 'inline-flex',
                alignSelf: 'flex-start',
                alignItems: 'center',
                gap: 7,
                padding: '12px 22px',
                borderRadius: 'var(--radius-card)',
                backgroundColor: 'var(--bg)',
                color: 'var(--brand-primary)',
                fontSize: 15,
                fontWeight: 700,
                boxShadow: 'var(--shadow-card)',
              }}
            >
              작성 시작하기
              <ArrowRight size={16} aria-hidden="true" />
            </Link>
          </div>
        </div>
      </div>

      {/* ── 히어로 아래: 기능 목록 (3열) ──
          auto-fit + minmax 를 쓰면 미디어쿼리 없이도 폭에 따라 열 수가 알아서
          줄어듭니다 — 넓으면 3열, 좁아지면 2열, 더 좁으면 1열. 인라인 style로는
          미디어쿼리를 못 쓰는데 이 방식은 CSS가 알아서 해주므로 클래스를 따로
          만들 필요가 없습니다. 260px는 제목 한 줄이 안 깨지는 최소 폭입니다. */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
          alignItems: 'stretch',
          gap: 'var(--space-6)',
          padding: `var(--space-6) ${GUTTER}`,
        }}
      >
        {FEATURES.map((feature, index) => (
          <NumberedFeature key={feature.title} index={index + 1} {...feature} />
        ))}
      </div>

      {/* ── 푸터 ── */}
      <footer
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'flex-end',
          gap: 'var(--space-3)',
          padding: `var(--space-2) ${GUTTER}`,
          borderTop: '1px solid var(--border-default)',
          fontSize: 12,
          color: 'var(--text-muted)',
        }}
      >
        <span>이용약관</span>
        <span>개인정보처리방침</span>
      </footer>
    </div>
  );
}

/** 남색 알약 안에 배 아이콘 + 서비스명 — 히어로 위에 얹는 임시 로고 */
function BrandBadge() {
  return (
    <span
      style={{
        display: 'inline-flex',
        alignSelf: 'flex-start',
        alignItems: 'center',
        gap: 'var(--space-1)',
        padding: '5px 10px',
        borderRadius: 6,
        backgroundColor: 'var(--brand-primary)',
        color: '#fff',
        fontSize: 13,
        fontWeight: 600,
        letterSpacing: '-0.2px',
        boxShadow: 'var(--shadow-card)',
      }}
    >
      <Ship size={15} aria-hidden="true" />
      B/L Copilot
    </span>
  );
}

/** 번호(1/2/3) + 제목 + 설명 한 줄. 위아래 구분선으로 목록임을 표시합니다 */
function NumberedFeature({
  index,
  title,
  body,
}: {
  index: number;
  title: string;
  body: string;
}) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: 'var(--space-3)',
        padding: '18px 0',
        // 세로로 쌓을 때는 마지막 칸에만 아래 선을 더 그었지만(isLast), 가로로
        // 나란히 놓이면 위 선 하나가 세 칸을 가로지르는 줄로 읽히므로 그것만
        // 남깁니다.
        borderTop: '1px solid var(--border-default)',
      }}
    >
      <span
        style={{
          display: 'inline-flex',
          flexShrink: 0,
          alignItems: 'center',
          justifyContent: 'center',
          width: 26,
          height: 26,
          borderRadius: 999,
          backgroundColor: 'var(--bg-card)',
          color: 'var(--text-secondary)',
          fontSize: 12,
          fontWeight: 700,
        }}
      >
        {index}
      </span>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4, minWidth: 0 }}>
        <span style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-primary)' }}>{title}</span>
        <span style={{ fontSize: 13.5, lineHeight: 1.6, color: 'var(--text-secondary)', wordBreak: 'keep-all' }}>
          {body}
        </span>
      </div>
    </div>
  );
}