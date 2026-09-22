/** What each trust flag means to a reader. The benchmark sends codes, we write. */
export const FLAG_TEXT: Record<string, string> = {
  few_samples: 'too few questions for the figures to be meaningful',
  judges_disagree: 'the graders disagreed too often',
  uneven_coverage: 'some task types were barely measured',
  pending_verdicts: 'part of the run was never graded',
  failed_calls: 'some calls failed during the run'
};

export function percent(value: number | null | undefined): string {
  if (value == undefined) return '—';
  return `${String(Math.round(value * 100))}%`;
}
