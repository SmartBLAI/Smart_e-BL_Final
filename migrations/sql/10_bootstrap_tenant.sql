-- ============================================================================
-- 부트스트랩 테넌트 · 사용자
--
-- 인증/멀티테넌시 온보딩이 아직 없다(범위 밖). 하지만 shipment.tenant_id 등은
-- NOT NULL FK라 실제 행을 하나 넣지 않으면 어떤 선적도 만들 수 없다. 인증이
-- 생기기 전까지 게이트웨이가 이 고정 UUID 하나로 동작한다 — 값은
-- src/smart_e_bl/config.py 의 BOOTSTRAP_TENANT_ID/BOOTSTRAP_USER_ID 와
-- 반드시 일치해야 한다.
-- ============================================================================

INSERT INTO tenant (id, code, name, is_onpremise) VALUES
  ('00000000-0000-0000-0000-000000000001', 'default', '기본 테넌트', false);

INSERT INTO app_user (id, tenant_id, email, name, role) VALUES
  ('00000000-0000-0000-0000-000000000002',
   '00000000-0000-0000-0000-000000000001',
   'system@bl-copilot.local', '시스템', 'ADMIN');
