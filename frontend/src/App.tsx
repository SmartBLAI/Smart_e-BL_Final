import { lazy, Suspense, type ReactNode } from 'react'
import { Loader2 } from 'lucide-react'
import { Routes, Route, Link } from 'react-router-dom'
import { S0Landing } from './pages/S0Landing'
import { S1Dashboard } from './pages/S1Dashboard'
import { ComingSoon } from './components/ComingSoon'
import { AppLayout } from './components/AppLayout'
import { PageContainer } from './components/PageContainer'
import { EmptyState } from './components/EmptyState'

// 화면별 코드 분할: S0/S1(진입 화면)만 처음부터 받고 나머지는 이동할 때 받습니다.
const lazyPage = <K extends string>(load: () => Promise<Record<K, React.ComponentType>>, name: K) =>
  lazy(() => load().then((m) => ({ default: m[name] })))
const S2Upload = lazyPage(() => import('./pages/S2Upload'), 'S2Upload')
const S3Draft = lazyPage(() => import('./pages/S3Draft'), 'S3Draft')
const S4Verdicts = lazyPage(() => import('./pages/S4Verdicts'), 'S4Verdicts')
const S5Timeline = lazyPage(() => import('./pages/S5Timeline'), 'S5Timeline')
const S6Alerts = lazyPage(() => import('./pages/S6Alerts'), 'S6Alerts')
const S7Report = lazyPage(() => import('./pages/S7Report'), 'S7Report')

/** 지연 로딩되는 화면이 도착할 때까지 기존 로딩 화면과 같은 모양을 보여줍니다 */
function Page({ children }: { children: ReactNode }) {
  return (
    <Suspense
      fallback={
        <PageContainer>
          <EmptyState icon={Loader2} message="불러오는 중입니다…" spin />
        </PageContainer>
      }
    >
      {children}
    </Suspense>
  )
}

function NotFound() {
  return (
    <div style={{ padding: 32, textAlign: 'center' }}>
      <p>존재하지 않는 페이지입니다.</p>
      <Link to="/shipments">대시보드로 이동</Link>
    </div>
  );
}

function App() {
  return (
    <Routes>
      {/* 랜딩은 자체 헤더가 있어서 AppLayout(NavBar) 밖에 둡니다 */}
      <Route path="/" element={<S0Landing />} />

      {/* 나머지 화면 — 공통 NavBar를 두른 레이아웃 안쪽.
          대시보드가 "/"에서 "/shipments"로 옮겨졌습니다 (랜딩이 "/"를 씀) */}
      <Route element={<AppLayout />}>
        <Route path="/shipments" element={<S1Dashboard />} />
        <Route path="/shipments/new" element={<Page><S2Upload /></Page>} />
        <Route path="/shipments/:id/draft" element={<Page><S3Draft /></Page>} />
        <Route path="/shipments/:id/verdicts" element={<Page><S4Verdicts /></Page>} />
        <Route path="/shipments/:id" element={<Page><S5Timeline /></Page>} />
        <Route path="/alerts" element={<Page><S6Alerts /></Page>} />
        <Route path="/shipments/:id/report" element={<Page><S7Report /></Page>} />
        <Route path="/shipments/:id/outcome" element={<ComingSoon label="S10 결과 기록" />} />
        <Route path="/settings" element={<ComingSoon label="S11 설정" />} />
        {/* 오타 URL 등 어디에도 안 걸리는 경로 — NavBar 없는 빈 화면 대신 안내 표시(P1-14) */}
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  )
}

export default App
