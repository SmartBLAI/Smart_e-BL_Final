import { useRef, useState } from 'react';
import type { ChangeEvent } from 'react';
import { FileText, X } from 'lucide-react';
import { parseMt700, type LcParse } from '../../api/lc';

/** 게이트웨이가 신용장으로 받아주는 확장자 (`_ALLOWED_LC_UPLOAD_EXT`와 같아야 함) */
const LC_ACCEPTED_EXT = '.txt';

interface LcUploadProps {
  /** 고른 신용장 파일. 아직 안 골랐으면 null */
  file: File | null;
  /** 파일을 고르거나(파싱 성공) 뺐을 때. B/L 업로드 시 같이 올릴 파일을 부모가 들고 있습니다 */
  onChange: (file: File | null) => void;
  /** B/L 추출·저장이 도는 동안은 못 바꾸게 막습니다 */
  disabled: boolean;
}

/**
 * 신용장(MT700) 첨부 — B/L 을 무엇과 대조할지 정하는 자리입니다.
 *
 * 왜 선택이 아니라 사실상 필수인가: 신용장이 없으면 룰엔진이 대조 룰
 * 대부분을 "평가불가"로 건너뛰는데, 결과 화면에는 **위반 0건**으로 보입니다.
 * 하자가 없는 것과 볼 기준이 없는 것이 같은 그림이 되므로, 여기서 안내를
 * 분명히 하고 파싱 결과(`notes`)도 바로 보여줍니다.
 *
 * 고른 즉시 `POST /lc/mt700` 으로 파싱해 보는 이유: 파일은 B/L 업로드가 끝난
 * 뒤에야 서버에 올라가는데, 그때 처음 파싱이 깨지면 사용자는 이미 S3 로
 * 넘어간 뒤입니다. 여기서 미리 읽어보면 못 읽는 전문을 즉시 알 수 있습니다.
 */
export function LcUpload({ file, onChange, disabled }: LcUploadProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [parse, setParse] = useState<LcParse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [parsing, setParsing] = useState(false);

  async function handleChange(event: ChangeEvent<HTMLInputElement>) {
    const picked = event.target.files?.[0];
    event.target.value = '';
    if (!picked) return;

    setError(null);
    setParsing(true);
    try {
      setParse(await parseMt700(await picked.text()));
      onChange(picked);
    } catch (err) {
      // 파싱이 안 되는 파일은 아예 안 받습니다 — 올려봐야 검증에서 못 씁니다.
      setParse(null);
      onChange(null);
      setError(err instanceof Error ? err.message : '신용장 전문을 읽지 못했습니다.');
    } finally {
      setParsing(false);
    }
  }

  function clear() {
    setParse(null);
    setError(null);
    onChange(null);
  }

  const notes = parse?.notes ?? [];
  const isReadNote = (note: string) => note.endsWith('를 읽었습니다.');
  const unusedNotes = notes.filter((note) => !isReadNote(note));
  const readNotes = notes.filter(isReadNote);

  return (
    <section
      style={{
        border: '1px solid var(--border-default)',
        borderRadius: 'var(--radius-card)',
        backgroundColor: 'var(--bg-card)',
        padding: 'var(--space-3)',
        marginBottom: 'var(--space-3)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
        <FileText size={18} color="var(--text-muted)" aria-hidden="true" />
        <strong style={{ flex: 1 }}>신용장(MT700) 첨부</strong>
        <input
          ref={inputRef}
          type="file"
          accept={LC_ACCEPTED_EXT}
          onChange={handleChange}
          style={{ display: 'none' }}
        />
        <button
          type="button"
          className="btn-secondary"
          onClick={() => inputRef.current?.click()}
          disabled={disabled || parsing}
        >
          {parsing ? '읽는 중…' : file ? '다른 파일 고르기' : '전문 파일 선택'}
        </button>
      </div>

      {file === null && error === null && (
        <p style={{ margin: 'var(--space-2) 0 0', fontSize: 13, color: 'var(--text-muted)' }}>
          신용장을 첨부하지 않으면 L/C 대조 룰이 평가불가로 빠지고, 결과 화면에는
          위반 0건으로 보입니다. SWIFT 전문 원문({LC_ACCEPTED_EXT})을 올려주세요.
        </p>
      )}

      {error !== null && (
        <p style={{ margin: 'var(--space-2) 0 0', color: 'var(--severity-critical)' }}>{error}</p>
      )}

      {file !== null && parse !== null && (
        <div style={{ marginTop: 'var(--space-2)', fontSize: 13 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
            <span>
              {file.name} — 태그 {Object.keys(parse.tags).length}개를 읽었습니다
              {typeof parse.lc.lc_no === 'string' ? ` (${parse.lc.lc_no})` : ''}
            </span>
            <button
              type="button"
              onClick={clear}
              disabled={disabled}
              aria-label="신용장 첨부 취소"
              style={{
                border: 'none',
                background: 'none',
                cursor: disabled ? 'default' : 'pointer',
                color: 'var(--text-muted)',
                display: 'inline-flex',
              }}
            >
              <X size={14} aria-hidden="true" />
            </button>
          </div>

          {/* 못 읽은 것을 숨기지 않습니다 — 무엇이 대조에서 빠졌는지가
              대조 결과만큼 중요합니다 (ruleEngine/mt700.py 주석). */}
          {/* 대조에서 빠진 태그(unmapped)는 서버가 이미 notes 에 문장으로 넣어 보내므로
              notes 만 보여줍니다 — 둘 다 그리면 같은 태그가 두 번 나옵니다. */}
          {/* notes 에는 "어디서 무엇을 읽었다"는 안내(…를 읽었습니다)도 섞여 옵니다 — 못 쓴 항목으로
              세면 건수가 부풀어서, 읽은 결과는 아래에 따로 보여줍니다. */}
          {unusedNotes.length > 0 && (
            <details style={{ marginTop: 'var(--space-2)', color: 'var(--text-secondary)' }}>
              <summary style={{ cursor: 'pointer' }}>
                검증에 쓰지 못한 항목 {unusedNotes.length}건
              </summary>
              <ul style={{ margin: 'var(--space-2) 0 0', paddingLeft: '1.2em' }}>
                {unusedNotes.map((note) => (
                  <li key={note}>{note}</li>
                ))}
              </ul>
            </details>
          )}
          {readNotes.map((note) => (
            <p key={note} style={{ margin: 'var(--space-1) 0 0', color: 'var(--text-secondary)' }}>
              {note}
            </p>
          ))}
        </div>
      )}
    </section>
  );
}
