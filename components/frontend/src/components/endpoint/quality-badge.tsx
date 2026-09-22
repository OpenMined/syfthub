import Search from 'lucide-react/dist/esm/icons/search';
import Target from 'lucide-react/dist/esm/icons/target';
import TriangleAlert from 'lucide-react/dist/esm/icons/triangle-alert';

import type { EndpointQuality } from '@/lib/types';

import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger
} from '@/components/ui/tooltip';
import { formatDateLong, formatRelativeTime } from '@/lib/date-utils';
import { cn } from '@/lib/utils';

import { FLAG_TEXT, percent } from './benchmark-format';

interface QualityBadgeProperties {
  quality: EndpointQuality;
  /** `compact` fits a listing row; `full` is for the endpoint page. */
  size?: 'compact' | 'full';
  className?: string;
}

/**
 * How stale a card may get before it stops being reassuring.
 * A benchmark run is deliberate, not a heartbeat, so the window is generous —
 * but a year-old number should not look like today's.
 */
const STALE_AFTER_DAYS = 30;

/** Score thresholds. Deliberately conservative: these numbers face buyers. */
const SCORE_GOOD = 0.85;
const SCORE_FAIR = 0.6;

/**
 * Above this share of inventions on questions the corpus cannot answer, the
 * warning turns red. Lower than one might set for ordinary mistakes, and on
 * purpose: there is no right answer to these questions, so every one of them is
 * something the endpoint made up, and the reader has nothing to check it
 * against.
 */
const FABRICATION_HIGH = 0.05;

function scoreTone(score: number, muted: boolean): string {
  if (muted) return 'text-muted-foreground';
  if (score >= SCORE_GOOD) return 'text-green-600 dark:text-green-500';
  if (score >= SCORE_FAIR) return 'text-yellow-600 dark:text-yellow-500';
  return 'text-red-600 dark:text-red-500';
}

function fabricationTone(rate: number, muted: boolean): string {
  if (muted) return 'text-muted-foreground';
  return rate > FABRICATION_HIGH
    ? 'text-red-600 dark:text-red-500'
    : 'text-muted-foreground';
}

function isStale(checkedAt: string): boolean {
  const ageDays = (Date.now() - new Date(checkedAt).getTime()) / 86_400_000;
  return ageDays > STALE_AFTER_DAYS;
}

interface ExplanationProperties {
  searching: boolean;
  score: number;
  fabrication?: number;
  samples?: number;
  checkedAt: string;
  stale: boolean;
  unvouched: boolean;
  doubts: string[];
}

/** The words behind the badge. Split out so the badge stays one shape. */
function BadgeExplanation({
  searching,
  score,
  fabrication,
  samples,
  checkedAt,
  stale,
  unvouched,
  doubts
}: Readonly<ExplanationProperties>) {
  return (
    <div className='space-y-1'>
      <p className='font-semibold'>
        {searching ? 'Search quality, benchmarked' : 'Answer quality, benchmarked'}
      </p>
      <p>
        Measured {formatDateLong(checkedAt)} ({formatRelativeTime(checkedAt)})
        {stale ? ' — this result is stale' : ''}
      </p>
      <p>
        {searching
          ? `${percent(score)} of questions found the right material`
          : `${percent(score)} of answers matched the reference`}
        {samples == undefined ? '' : ` over ${String(samples)} questions`}.
      </p>
      {fabrication == undefined ? null : (
        <p>
          {percent(fabrication)} of questions the corpus cannot answer were answered
          anyway. There is no right answer to those, so each one was made up.
        </p>
      )}
      {unvouched ? (
        <div className='border-t pt-1'>
          <p className='font-semibold'>Not vouched for</p>
          {doubts.length > 0 ? (
            <ul className='list-disc pl-4'>
              {doubts.map((flag) => (
                <li key={flag}>{FLAG_TEXT[flag] ?? flag}</li>
              ))}
            </ul>
          ) : (
            <p>The benchmark does not stand behind these figures.</p>
          )}
        </div>
      ) : null}
    </div>
  );
}

/**
 * Benchmark badge: two figures and a state.
 *
 * Two, not one, because either alone can be played. A badge showing only
 * accuracy rewards an endpoint that answers everything regardless; a badge
 * showing only inventions rewards one that refuses everything. Together they
 * cannot both be gamed: the refuser scores zero on the first, and the reckless
 * one scores a hundred on the second.
 *
 * The headline is labelled by kind. An endpoint that only searches never writes
 * an answer, so it has no accuracy — its product is what it found, and its
 * share of the blame is whether the material it hands over pushes someone
 * else's model into inventing.
 *
 * Renders nothing when nobody ever measured this endpoint. That is deliberate:
 * an unmeasured endpoint and a bad one are different things, and a "0%" badge
 * would libel the former.
 */
export function QualityBadge({
  quality,
  size = 'compact',
  className
}: Readonly<QualityBadgeProperties>) {
  const {
    quality_kind: kind,
    quality_score: score,
    quality_fabrication_rate: fabricationRate,
    quality_samples: samples,
    quality_reliable: reliable,
    quality_checked_at: checkedAt,
    quality_report: report
  } = quality;

  if (score == undefined || checkedAt == undefined || kind == undefined) return null;

  const stale = isStale(checkedAt);
  // A figure nobody vouches for is worse than no figure: absence is visible to
  // a reader and a bare number is not. So it is shown, but never in the colour
  // of a result.
  const unvouched = reliable === false;
  const muted = stale || unvouched;
  const fabrication = fabricationRate ?? undefined;
  const full = size === 'full';
  const searching = kind === 'retrieval';
  const ScoreIcon = searching ? Search : Target;
  const scoreWord = searching ? 'found' : 'correct';
  const doubts = report?.trust?.flags ?? [];

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <div
            className={cn(
              'inline-flex items-center gap-2 rounded-md border px-2 py-0.5',
              full ? 'text-sm' : 'text-xs',
              muted && 'border-dashed',
              className
            )}
            aria-label={`Benchmark: ${percent(score)} ${scoreWord}${
              fabrication == undefined ? '' : `, ${percent(fabrication)} invented`
            }, measured ${formatDateLong(checkedAt)}${
              unvouched ? ', not vouched for' : ''
            }`}
          >
            <span className={cn('inline-flex items-center gap-1', scoreTone(score, muted))}>
              <ScoreIcon className={full ? 'size-4' : 'size-3'} aria-hidden='true' />
              <span className='font-semibold'>{percent(score)}</span>
              {full ? <span className='text-muted-foreground font-normal'>{scoreWord}</span> : null}
            </span>
            {fabrication == undefined ? null : (
              <span
                className={cn(
                  'inline-flex items-center gap-1',
                  fabricationTone(fabrication, muted)
                )}
              >
                <TriangleAlert className={full ? 'size-4' : 'size-3'} aria-hidden='true' />
                <span className='font-semibold'>{percent(fabrication)}</span>
                {full ? (
                  <span className='text-muted-foreground font-normal'>invented</span>
                ) : null}
              </span>
            )}
          </div>
        </TooltipTrigger>
        <TooltipContent className='max-w-xs'>
          <BadgeExplanation
            searching={searching}
            score={score}
            fabrication={fabrication}
            samples={samples ?? undefined}
            checkedAt={checkedAt}
            stale={stale}
            unvouched={unvouched}
            doubts={doubts}
          />
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
