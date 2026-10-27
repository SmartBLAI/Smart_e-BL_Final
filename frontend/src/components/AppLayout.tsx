import { Outlet } from 'react-router-dom';
import { NavBar } from './NavBar';
import { DataSourceNotice } from './DataSourceNotice';
import { isDemoFixtures } from '../shared/shipmentStore';

/**
 * 상단 NavBar를 두르는 공통 레이아웃.
 *
 * <Outlet />은 "이 자리에 자식 화면을 끼워 넣어라"는 뜻의 react-router 부품입니다.
 * App.tsx에서 이 레이아웃을 부모 라우트로 두면, 그 안의 화면들만 NavBar를
 * 갖게 됩니다 — 랜딩(S0)은 자체 헤더가 있어서 이 레이아웃 밖에 둡니다.
 *
 * 픽스처 모드(`?demo=1`)일 때는 모든 화면 위에 목데이터임을 밝히는 띠를 답니다.
 * 화면마다 붙이지 않고 여기 한 곳에만 두는 이유: 한 화면이라도 빠뜨리면 그
 * 화면에서는 목데이터가 실제 결과처럼 읽힙니다 (규약 §5 — 근거 없는 값 표시 금지).
 */
export function AppLayout() {
  return (
    <>
      <NavBar />
      {isDemoFixtures() && (
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: 4,
            padding: 'var(--space-2) var(--space-3) 0',
            textAlign: 'left',
          }}
        >
          {/* reason은 넘기지 않습니다 — DataSourceNotice의 reason은 "aiService
              응답 실패: …"로 그려지는데, 데모 모드에서는 aiService를 아예 부르지
              않으므로 실패했다고 쓰면 사실이 아닙니다. */}
          <DataSourceNotice source="mock" />
          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
            목업 시연 모드(<code>?demo=1</code>)입니다. F5·F6·F7은 아직 백엔드가 없어 픽스처로만
            그립니다. 끄려면 주소에 <code>?demo=0</code>을 붙이세요.
          </span>
        </div>
      )}
      <Outlet />
    </>
  );
}
