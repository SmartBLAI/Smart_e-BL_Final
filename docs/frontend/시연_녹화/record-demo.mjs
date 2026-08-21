// F1~F4 시연 자동 녹화. 설치된 Chrome 을 몰면서 화면을 webm 으로 남깁니다.
//
// 준비 (한 번만):
//   npm i playwright-core                      # 브라우저는 안 받습니다. 설치된 Chrome 을 씁니다
//   node node_modules/playwright-core/cli.js install ffmpeg   # 녹화용 1MB 짜리
//
// 실행:
//   ./scripts/demo-check.sh                    # 전부 ✓ 인지 먼저 확인
//   PW=$PWD/node_modules/playwright-core/index.js node docs/frontend/시연_녹화/record-demo.mjs
//
// 두 가지 사례를 찍습니다. CASE 로 고릅니다:
//   CASE=defect (기본)  하자가 잡히는 사례 → F1-F4_시연.webm
//   CASE=clean          하자 0건으로 통과하는 사례 → F1-F4_시연_통과.webm
//
// 통과본 샘플은 촬영 당일에 다시 만들어야 합니다. 제시기간(21일)이 실행일
// 기준이라 묵히면 같은 파일이 하자로 바뀝니다:
//   python docs/frontend/시연_녹화/make-clean-sample.py
//
// PW 는 playwright-core 를 어디에 깔았는지 알려주는 값입니다. 이 스크립트가
// docs 안에 있어서 저장소 루트의 node_modules 를 스스로 못 찾습니다.
//
// 녹화되는 것은 페이지 내용뿐입니다 — 주소창·탭은 안 찍히고 소리도 없습니다.
// 내레이션은 후시 녹음하세요. 대본은 ../시연_촬영_대본.md.
//
// 이 스크립트는 실제 백엔드를 그대로 씁니다. 돌리면 선적이 하나 생깁니다.
// 촬영본이 마음에 안 들면 대본 부록의 삭제 명령으로 비우고 다시 도세요.

import { fileURLToPath } from 'node:url';
import path from 'node:path';
import fs from 'node:fs/promises';

const pw = await import(process.env.PW ?? 'playwright-core');
const chromium = pw.chromium ?? pw.default.chromium;

const HERE = path.dirname(fileURLToPath(import.meta.url));
const DOCS = path.dirname(HERE);
const CLEAN = process.env.CASE === 'clean';
const BL = path.join(DOCS, CLEAN ? '샘플_통과_B_L.pdf' : '샘플_B_L_SHP-2026-0812-001.pdf');
const LC = path.join(DOCS, CLEAN ? '샘플_통과_L_C_MT700.txt' : '샘플_L_C_MT700_SHP-2026-0812-001.txt');
const BASE = process.env.BASE ?? 'http://localhost:8080';

// 사람이 읽을 시간. 자동화는 사람보다 훨씬 빨라서 이걸 안 넣으면
// 화면이 휙휙 넘어가 영상으로 못 씁니다.
const beat = (ms) => new Promise((r) => setTimeout(r, ms));

const browser = await chromium.launch({ channel: 'chrome', headless: false });
const ctx = await browser.newContext({
  viewport: { width: 1440, height: 900 },
  recordVideo: { dir: HERE, size: { width: 1440, height: 900 } },
});
const page = await ctx.newPage();

async function scrollTo(locator) {
  await locator.scrollIntoViewIfNeeded();
  await beat(600);
}

// 컷 1 — 랜딩 · 대시보드
await page.goto(BASE);
await beat(3500);
await page.getByRole('link', { name: '시작하기' }).click();
await page.waitForURL('**/shipments');
await beat(2500);
await page.getByRole('link', { name: '새 선적' }).click();
await page.waitForURL('**/shipments/new');
await beat(2000);

// 컷 2 — F1 인테이크. L/C 를 먼저 넣습니다. B/L 이 먼저 들어가면
// L/C 입력이 잠기고 그대로 다음 화면으로 떠나버립니다.
const inputs = page.locator('input[type=file]');
await inputs.nth(0).setInputFiles(LC);
await page.getByText('태그').first().waitFor({ timeout: 15000 });
await beat(3000);
await inputs.nth(1).setInputFiles(BL);
await page.waitForURL('**/draft', { timeout: 60000 });
await beat(3000);

// 컷 3 — F1 결과 · F2 교정 제안.
// 접힌 그룹("출처 없음", "확인 권고")을 펼쳐야 제안 6건이 다 보입니다.
for (const label of ['출처 없음', '확인 권고']) {
  const group = page.getByRole('button', { name: new RegExp(`${label} \\d+건`) });
  if (await group.count()) {
    await scrollTo(group.first());
    await group.first().click();
    await beat(1800);
  }
}
await page.mouse.wheel(0, -2000);
await beat(2000);

// 필수 확인 필드를 먼저 해소하고 그 다음 승인합니다. 확인한 필드가 목록 맨 아래
// "확정" 그룹으로 내려가서 그 뒤의 first()가 제안 카드를 집게 됩니다.
//
// 한때는 순서 자체가 함정 회피책이었습니다 — 선적항·양륙항에 BUSAN→KRPUS 제안이
// 떴고, 승인하면 F3 가 D003·D004 치명 하자를 새로 만들어냈습니다. 지금은 항구
// 제안이 항구명으로만 나가고 이미 맞는 표기에는 카드가 안 떠서 그 함정이 없습니다.

// 남은 필수 확인 필드를 해소해야 "검증 실행" 이 열립니다.
//
// count()가 0이 되면 끝, 으로 짜면 안 됩니다 — 확인한 필드가 다른 그룹으로
// 옮겨가면서 목록이 통째로 다시 그려지는 순간에 0이 잡혀 한 건 남기고
// 빠져나옵니다. 끝났는지는 버튼 개수가 아니라 "검증 실행"이 열렸는지로
// 판단합니다.
const verify = page.getByRole('button', { name: '검증 실행', exact: true });
for (let i = 0; i < 12 && !(await verify.isEnabled()); i += 1) {
  const btn = page.getByRole('button', { name: '값 확인함', exact: true }).first();
  if (!(await btn.count())) {
    await beat(700);
    continue;
  }
  await scrollTo(btn);
  await btn.click();
  await beat(1200);
}
// 제안 승인 — 자동 반영이 아니라 사람이 누른다는 걸 보여주는 장면입니다.
for (let i = 0; i < 3; i += 1) {
  const btn = page.getByRole('button', { name: '승인', exact: true }).first();
  if (!(await btn.count())) break;
  await scrollTo(btn);
  await btn.click();
  await beat(1800);
}

if (!(await verify.isEnabled())) {
  console.error('검증 실행이 안 열렸습니다. 화면이 말하는 이유:');
  console.error(await page.getByText(/남아 있습니다|있습니다$/).allTextContents());
  throw new Error('필수 확인 필드가 남아 있습니다');
}
await beat(1500);

// 컷 4 — F3 판정
await scrollTo(verify);
await verify.click();
await page.waitForURL('**/verdicts', { timeout: 60000 });
await beat(4000);

// 판정 카드를 하나씩 훑습니다.
await page.mouse.wheel(0, 400);
await beat(3000);
await page.mouse.wheel(0, 400);
await beat(3000);

// "검사하지 못한 항목" 은 접혀 있습니다 — 펼쳐야 사유가 보입니다.
const skipped = page.getByText(/검사하지 못한 항목/).first();
if (await skipped.count()) {
  await scrollTo(skipped);
  await skipped.click();
  await beat(4000);
}

// 컷 5 — F4 리포트
const url = new URL(page.url());
await page.goto(`${BASE}${url.pathname.replace(/\/verdicts$/, '/report')}`);
await beat(4000);
await page.mouse.wheel(0, 500);
await beat(3000);
await page.mouse.wheel(0, 500);
await beat(3000);

const video = page.video();
await ctx.close();
await browser.close();

// Playwright 는 임의의 해시 이름으로 저장합니다. 찾기 쉬운 이름으로 바꿉니다.
if (video) {
  const src = await video.path();
  const out = path.join(HERE, CLEAN ? 'F1-F4_시연_통과.webm' : 'F1-F4_시연.webm');
  await fs.rename(src, out);
  console.log(out);
}
