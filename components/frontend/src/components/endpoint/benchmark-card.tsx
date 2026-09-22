import { memo } from 'react';

import type {
  BenchmarkModelRow,
  BenchmarkSkillRow,
  BenchmarkCard as Card,
  EndpointQuality
} from '@/lib/types';

import { formatDateLong, formatRelativeTime } from '@/lib/date-utils';
import { cn } from '@/lib/utils';

import { FLAG_TEXT, percent } from './benchmark-format';

export interface BenchmarkCardProperties {
  quality?: EndpointQuality;
}

function signedPercent(value: number | null | undefined): string {
  if (value == undefined) return '—';
  const rounded = Math.round(value * 100);
  return `${rounded > 0 ? '+' : ''}${String(rounded)}%`;
}

function Figure({ label, value, hint }: Readonly<{ label: string; value: string; hint: string }>) {
  return (
    <div className='space-y-0.5'>
      <div className='text-foreground text-lg font-semibold'>{value}</div>
      <div className='text-foreground text-xs font-medium'>{label}</div>
      <div className='text-muted-foreground text-xs'>{hint}</div>
    </div>
  );
}

/**
 * What a reader gets if he plugs in his own model.
 *
 * By name and as a spread, never as one number: an average would move whenever
 * the benchmark changed its own list of models while nothing had happened to
 * this endpoint, and it would hide what the reader came for — how much the
 * result depends on what he brings.
 */
function ModelSpread({ models }: Readonly<{ models: BenchmarkModelRow[] }>) {
  if (models.length === 0) return null;

  const accuracies = models.map((row) => row.accuracy);
  const spread =
    accuracies.length > 1
      ? { low: Math.min(...accuracies), high: Math.max(...accuracies) }
      : undefined;

  return (
    <div className='space-y-2'>
      <div className='flex items-baseline justify-between'>
        <h4 className='text-foreground text-xs font-medium'>
          With your own model ({models.length} measured)
        </h4>
        {spread ? (
          <span className='text-muted-foreground text-xs'>
            {percent(spread.low)} – {percent(spread.high)}
          </span>
        ) : null}
      </div>
      <ul className='space-y-1'>
        {models.map((row) => (
          <ModelRow key={row.model} row={row} />
        ))}
      </ul>
    </div>
  );
}

function ModelRow({ row }: Readonly<{ row: BenchmarkModelRow }>) {
  return (
    <li className='flex items-center gap-2 text-xs'>
      <span className='text-muted-foreground w-48 truncate' title={row.model}>
        {row.model}
      </span>
      <div className='bg-muted h-1.5 flex-1 overflow-hidden rounded-full'>
        <div
          className='bg-foreground/60 h-full'
          style={{ width: `${String(Math.round(row.accuracy * 100))}%` }}
        />
      </div>
      <span className='text-foreground w-10 text-right font-medium'>{percent(row.accuracy)}</span>
      {row.context_gain == undefined ? null : (
        <span
          className={cn(
            'w-10 text-right',
            row.context_gain > 0 ? 'text-red-600 dark:text-red-500' : 'text-muted-foreground'
          )}
          title="What this endpoint did to that model's honesty. Positive means the context made it bolder, not better."
        >
          {signedPercent(row.context_gain)}
        </span>
      )}
    </li>
  );
}

/** What the endpoint is good for. One share over ten task types hides this. */
function SkillBreakdown({ skills }: Readonly<{ skills: BenchmarkSkillRow[] }>) {
  if (skills.length === 0) return null;

  return (
    <div className='space-y-2'>
      <h4 className='text-foreground text-xs font-medium'>By type of question</h4>
      <ul className='grid grid-cols-1 gap-1 sm:grid-cols-2'>
        {skills.map((skill) => (
          <li key={skill.generator} className='flex items-center gap-2 text-xs'>
            <span className='text-muted-foreground flex-1 truncate'>{skill.generator}</span>
            <span className='text-foreground font-medium'>{percent(skill.accuracy)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * Who measured, and on what.
 *
 * Two endpoints measured by different benchmark installations, or over
 * different windows of a corpus, are not comparable — and nothing else on this
 * page says so.
 */
function Provenance({ report }: Readonly<{ report: Card }>) {
  const window =
    report.dataset && report.dataset.window_days > 0
      ? `the last ${String(report.dataset.window_days)} days of the corpus`
      : 'the whole corpus';

  return (
    <div className='text-muted-foreground space-y-0.5 border-t pt-3 text-xs'>
      <p>
        {report.samples} questions
        {report.retrieval == undefined
          ? ''
          : `, search found the material ${percent(report.retrieval)} of the time`}
        {report.trust?.judges ? `, ${String(report.trust.judges)} graders` : ''}
        {report.trust?.agreement == undefined
          ? ''
          : ` agreeing ${percent(report.trust.agreement)} of the time`}
      </p>
      {report.dataset ? (
        <p>
          Questions built from {window}
          {report.dataset.mode ? ` (${report.dataset.mode})` : ''}.
        </p>
      ) : null}
      {report.instrument ? (
        <p>
          Graded by {report.instrument.judge || 'an undisclosed grader'}
          {report.instrument.profile ? `, profile ${report.instrument.profile}` : ''}. Figures
          compare with other endpoints measured by the same benchmark, not with those measured by
          another.
        </p>
      ) : null}
    </div>
  );
}

/**
 * The benchmark card on an endpoint's public page.
 *
 * The badge answers "is this worth opening". This answers the question someone
 * who opened it actually has: **what do I get if I plug in my own model?**
 *
 * Which is why the subject models appear here by name and as a spread rather
 * than as one number. An average over them would move whenever the benchmark
 * changed its own list of models, while nothing had happened to this endpoint —
 * and it would hide the thing the reader is here for, which is how much the
 * result depends on what he brings.
 */
export const BenchmarkCard = memo(function BenchmarkCard({
  quality
}: Readonly<BenchmarkCardProperties>) {
  const report: Card | null | undefined = quality?.quality_report;
  if (!report) return null;

  const searching = report.kind === 'retrieval';
  const flags = report.trust?.flags ?? [];

  return (
    <div className='border-border bg-card space-y-5 rounded-xl border p-6'>
      <div className='flex items-baseline justify-between'>
        <h3 className='font-rubik text-foreground text-sm font-medium'>
          {searching ? 'Search quality' : 'Answer quality'}
        </h3>
        <span className='text-muted-foreground text-xs'>
          {formatDateLong(report.checked_at)} ({formatRelativeTime(report.checked_at)})
        </span>
      </div>

      {/* Not vouched for — said first, because everything below it is then
          a description of a measurement rather than of the endpoint. */}
      {report.reliable ? null : (
        <div className='rounded-lg border border-dashed p-3 text-xs'>
          <p className='text-foreground font-medium'>
            The benchmark does not stand behind these figures
          </p>
          {flags.length > 0 ? (
            <ul className='text-muted-foreground mt-1 list-disc pl-4'>
              {flags.map((flag) => (
                <li key={flag}>{FLAG_TEXT[flag] ?? flag}</li>
              ))}
            </ul>
          ) : null}
        </div>
      )}

      <div className='grid grid-cols-2 gap-4 sm:grid-cols-4'>
        <Figure
          label={searching ? 'found' : 'correct'}
          value={percent(report.score)}
          hint={
            searching
              ? 'the search returned the right material'
              : 'the answer matched the reference'
          }
        />
        <Figure
          label='invented'
          value={percent(report.fabrication_rate)}
          hint='answered a question the corpus cannot answer'
        />
        <Figure
          label='risk per answer'
          value={percent(report.answerable?.lmi)}
          hint='of the times it answered, how often it was wrong'
        />
        <Figure
          label='silence is a signal'
          value={signedPercent(report.discrimination)}
          hint='refuses more when there is nothing to find'
        />
      </div>

      <ModelSpread models={report.models} />
      <SkillBreakdown skills={report.skills} />

      <Provenance report={report} />
    </div>
  );
});
