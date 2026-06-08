import { useEffect, useRef } from 'react';
import { cn } from '@/lib/utils';

interface OtpInputProps {
  /** Current code value (digits only, up to `length` chars). */
  value: string;
  onChange: (value: string) => void;
  /** Fired when all `length` digits have been entered. */
  onComplete?: (value: string) => void;
  length?: number;
  disabled?: boolean;
  autoFocus?: boolean;
}

/** A segmented N-digit numeric code input. Maintains a single string value of
 *  digits; each box renders one character. Paste of a full code is supported. */
export function OtpInput({
  value,
  onChange,
  onComplete,
  length = 6,
  disabled,
  autoFocus,
}: OtpInputProps) {
  const inputs = useRef<(HTMLInputElement | null)[]>([]);

  useEffect(() => {
    if (autoFocus) {
      inputs.current[0]?.focus();
    }
  }, [autoFocus]);

  const digits = value.split('').slice(0, length);

  // Return `value` with the cell at `index` set to `char` ('' clears it),
  // always capped to `length` digits.
  const withCharAt = (index: number, char: string) => {
    const next = value.split('');
    next[index] = char;
    return next.join('').slice(0, length);
  };

  // Push a finished code out, advance focus, and fire onComplete when full.
  // `joined` is built from a length-capped array with no gaps, so a full string
  // means every cell is filled.
  const commit = (joined: string, cursor: number) => {
    onChange(joined);
    inputs.current[Math.min(cursor, length - 1)]?.focus();
    if (joined.length === length) {
      onComplete?.(joined);
    }
  };

  // Strip everything but digits — applied to both typed and pasted input.
  const onlyDigits = (s: string) => s.replace(/\D/g, '');

  const setDigit = (index: number, raw: string) => {
    const sanitized = onlyDigits(raw);
    if (!sanitized) {
      // Clearing this cell.
      onChange(withCharAt(index, ''));
      return;
    }

    // Distribute possibly-multiple characters (e.g. fast typing) starting here.
    const next = value.split('');
    let cursor = index;
    for (const ch of sanitized) {
      if (cursor >= length) break;
      next[cursor] = ch;
      cursor += 1;
    }
    commit(next.join('').slice(0, length), cursor);
  };

  const handleKeyDown = (
    index: number,
    e: React.KeyboardEvent<HTMLInputElement>
  ) => {
    if (e.key === 'Backspace') {
      e.preventDefault();
      if (digits[index]) {
        onChange(withCharAt(index, ''));
      } else if (index > 0) {
        onChange(withCharAt(index - 1, ''));
        inputs.current[index - 1]?.focus();
      }
    } else if (e.key === 'ArrowLeft' && index > 0) {
      e.preventDefault();
      inputs.current[index - 1]?.focus();
    } else if (e.key === 'ArrowRight' && index < length - 1) {
      e.preventDefault();
      inputs.current[index + 1]?.focus();
    }
  };

  const handlePaste = (e: React.ClipboardEvent<HTMLInputElement>) => {
    e.preventDefault();
    const pasted = onlyDigits(e.clipboardData.getData('text')).slice(0, length);
    if (!pasted) return;
    commit(pasted, pasted.length);
  };

  return (
    <div className="flex items-center justify-center gap-2">
      {Array.from({ length }).map((_, index) => (
        <input
          key={index}
          ref={(el) => {
            inputs.current[index] = el;
          }}
          type="text"
          inputMode="numeric"
          autoComplete="one-time-code"
          maxLength={1}
          disabled={disabled}
          value={digits[index] ?? ''}
          onChange={(e) => setDigit(index, e.target.value)}
          onKeyDown={(e) => handleKeyDown(index, e)}
          onPaste={handlePaste}
          aria-label={`Digit ${index + 1}`}
          className={cn(
            'h-12 w-11 rounded-md border border-input bg-transparent text-center text-lg font-mono tabular-nums shadow-xs transition-[color,box-shadow] outline-none',
            'dark:bg-input/30',
            'focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]',
            'disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50'
          )}
        />
      ))}
    </div>
  );
}
