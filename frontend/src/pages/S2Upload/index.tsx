import { useRef, useState } from 'react';
import type { ChangeEvent, DragEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { UploadCloud } from 'lucide-react';
import type { Job } from '../../types/domain';
import { JOB_STATUS_LABEL, SUPPORTED_INPUT } from '../../constants/domain';
import { useCreateDraft } from '../../shared/shipmentStore';
import { useExtract } from '../../api/useExtract';
import { LcUpload } from './LcUpload';
import { PageContainer } from '../../components/PageContainer';

function getExtension(fileName: string): string {
  const dotIndex = fileName.lastIndexOf('.');
  return dotIndex === -1 ? '' : fileName.slice(dotIndex).toLowerCase();
}

export function S2Upload() {
  const navigate = useNavigate();
  const createDraft = useCreateDraft();
  const { run: runExtract } = useExtract();
  const inputRef = useRef<HTMLInputElement>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [rejectMessage, setRejectMessage] = useState<string | null>(null);
  // 신용장은 B/L 보다 먼저 고르지만, 서버에는 선적이 생긴 뒤에야 올라갑니다
  // (선적 id 가 있어야 서류를 붙일 수 있음). 그때까지 파일을 여기 들고 있습니다.
  const [lcFile, setLcFile] = useState<File | null>(null);

  // 새 선적은 게이트웨이(src/smart_e_bl) DB에 저장됩니다 — 탭을 닫아도 남습니다.
  async function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = ''; // 같은 파일을 다시 골라도 change 이벤트가 나도록 비움
    if (file) await processFile(file);
  }

  // 드롭존에 파일을 끌어놓았을 때. 드래그 중에도 dragover에서 preventDefault를
  // 안 하면 브라우저가 기본 동작(파일을 새 탭으로 열기)을 그대로 실행합니다(P1-13).
  function handleDragOver(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
  }

  async function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    if (job !== null && job.status !== 'FAILED') return; // 진행 중엔 클릭과 동일하게 무시
    const file = event.dataTransfer.files?.[0];
    if (file) await processFile(file);
  }

  async function processFile(file: File) {
    const ext = getExtension(file.name);
    const acceptedExt: readonly string[] = SUPPORTED_INPUT.ACCEPTED_EXT;
    const deferredExt: readonly string[] = SUPPORTED_INPUT.DEFERRED_EXT;

    if (!acceptedExt.includes(ext)) {
      const isDeferred = deferredExt.includes(ext);
      setRejectMessage(
        isDeferred
          ? `${ext} 형식은 이번 기간에는 아직 지원하지 않습니다.`
          : `${ext || '이 형식'}은(는) 지원하지 않는 파일 형식입니다.`,
      );
      return;
    }

    setRejectMessage(null);
    setJob({ job_id: `JOB-${Date.now()}`, status: 'PENDING', progress: null, failure_reason: null });
    // 실제 진행률 신호는 없지만(백엔드가 동기 응답), 기존 2단계 연출은 유지합니다.
    setJob((prev) => (prev ? { ...prev, status: 'EXTRACTING' } : prev));

    const result = await runExtract(file);

    // 화면전이_정의.md: "job DONE 전에는 S3로 이동하지 않는다" / FAILED면 S2에 머문다
    if (!result.ok) {
      setJob((prev) => (prev ? { ...prev, status: 'FAILED', failure_reason: result.message } : prev));
      return;
    }

    // 게이트웨이에 선적 생성 → 서류 업로드 → 필드값 저장까지 끝나야 S3로 넘어갑니다.
    try {
      const shipmentId = await createDraft(file, result.fields, lcFile);
      setJob((prev) => (prev ? { ...prev, status: 'DONE' } : prev));
      navigate(`/shipments/${shipmentId}/draft`);
    } catch (err) {
      const message = err instanceof Error ? err.message : '선적 저장에 실패했습니다.';
      setJob((prev) => (prev ? { ...prev, status: 'FAILED', failure_reason: message } : prev));
    }
  }

  function openFilePicker() {
    if (job !== null && job.status !== 'FAILED') return;
    inputRef.current?.click();
  }

  return (
    // 목록·폼 화면은 narrow로 콘텐츠 폭을 좁힙니다 (S1·S4~S7과 같은 기준).
    // 전체 폭을 쓰는 건 뷰어+폼을 좌우로 놓는 S3뿐입니다.
    <PageContainer narrow>
      <h1>서류 업로드</h1>

      <LcUpload
        file={lcFile}
        onChange={setLcFile}
        disabled={job !== null && job.status !== 'FAILED'}
      />

      <input
        ref={inputRef}
        type="file"
        accept={SUPPORTED_INPUT.ACCEPTED_EXT.join(',')}
        onChange={handleFileChange}
        style={{ display: 'none' }}
      />

      <div
        onClick={openFilePicker}
        onDragOver={handleDragOver}
        onDrop={handleDrop}
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 'var(--space-3)',
          height: 300,
          border: '2px dashed var(--border-default)',
          borderRadius: 'var(--radius-card)',
          backgroundColor: 'var(--bg-card)',
          cursor: job !== null && job.status !== 'FAILED' ? 'default' : 'pointer',
          opacity: job !== null && job.status !== 'FAILED' ? 0.6 : 1,
          textAlign: 'center',
        }}
      >
        <UploadCloud size={32} color="var(--text-muted)" aria-hidden="true" />
        <p style={{ margin: 0, color: 'var(--text-secondary)' }}>
          B/L 파일을 드래그하거나 클릭해서 선택하세요
        </p>
        <button
          type="button"
          className="btn-primary"
          onClick={(event) => {
            event.stopPropagation();
            openFilePicker();
          }}
          disabled={job !== null && job.status !== 'FAILED'}
        >
          파일 선택
        </button>
      </div>

      <p style={{ fontSize: 13, color: 'var(--text-muted)', marginTop: 'var(--space-3)' }}>
        지원 형식: {SUPPORTED_INPUT.ACCEPTED_EXT.join(', ')}
      </p>

      {rejectMessage !== null && (
        <p style={{ color: 'var(--severity-critical)' }}>{rejectMessage}</p>
      )}

      {job !== null && job.status !== 'FAILED' && <p>진행 상태: {JOB_STATUS_LABEL[job.status]}</p>}

      {job?.status === 'FAILED' && (
        <p style={{ color: 'var(--severity-critical)' }}>
          추출 실패: {job.failure_reason} 다시 시도해주세요.
        </p>
      )}
    </PageContainer>
  );
}
