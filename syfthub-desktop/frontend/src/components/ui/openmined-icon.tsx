import type React from 'react';

import { cn } from '@/lib/utils';

interface OpenMinedIconProps {
  className?: string;
}

/**
 * OpenMined logo icon component.
 * Can be styled with className like lucide-react icons.
 */
export function OpenMinedIcon({ className }: Readonly<OpenMinedIconProps>): React.ReactElement {
  return (
    <svg
      xmlns='http://www.w3.org/2000/svg'
      viewBox='0 0 397 397'
      fill='none'
      className={cn('h-6 w-6', className)}
    >
      <path
        d='M177.773 11.955L117.066 117.066L198.474 70.074L326.874 198.474L219.227 11.955C210.015 -3.98501 186.985 -3.98501 177.773 11.955Z'
        fill='#F0AC74'
      />
      <path
        d='M279.882 117.066L326.874 198.474L198.526 326.822L385.045 219.124C400.985 209.912 400.985 186.881 385.045 177.669L279.882 116.963V117.066Z'
        fill='#F0AC74'
      />
      <path
        d='M198.526 70.074L11.955 177.773C-3.98501 186.985 -3.98501 210.015 11.955 219.227L117.066 279.934L70.074 198.526L198.526 70.074Z'
        fill='#F0AC74'
      />
      <path
        d='M198.526 326.874L70.1776 198.526L177.876 385.045C187.088 400.985 210.119 400.985 219.331 385.045L280.037 279.882L198.629 326.874H198.526Z'
        fill='#F0AC74'
      />
      <path d='M198.526 198.526H275.535L198.526 121.517V198.526Z' fill='#F0AC74' />
      <path d='M198.526 198.526L121.517 198.526L198.526 275.535L198.526 198.526Z' fill='#F0AC74' />
      <path d='M198.526 198.526L198.526 275.535L275.535 198.526H198.526Z' fill='#F0AC74' />
      <path d='M198.526 198.526V121.517L121.517 198.526L198.526 198.526Z' fill='#F0AC74' />
      <path
        d='M177.8 11.9422L117.12 117.056L198.508 70.0654V70.0971L326.903 198.492L219.217 11.9581C210.006 -3.98604 186.995 -3.98604 177.784 11.9581L177.8 11.9422Z'
        fill='url(#paint0_linear_5687_13602)'
      />
      <path
        d='M279.912 117.056L326.919 198.476L326.871 198.492L198.508 326.855L385.042 219.184C400.986 209.974 400.986 186.963 385.042 177.752L279.912 117.056Z'
        fill='url(#paint1_linear_5687_13602)'
      />
      <path
        d='M70.1127 198.46L198.508 70.0654L11.9737 177.736C-3.97041 186.947 -3.97041 209.958 11.9737 219.169L117.148 279.864L70.0969 198.476L70.1127 198.46Z'
        fill='url(#paint2_linear_5687_13602)'
      />
      <path
        d='M198.524 326.871V326.839L70.1607 198.476H70.1289L177.815 385.01C187.026 400.954 210.037 400.954 219.248 385.01L279.96 279.864L198.556 326.871H198.524Z'
        fill='url(#paint3_linear_5687_13602)'
      />
      <path
        d='M198.523 198.492V275.497L275.529 198.492H198.523Z'
        fill='url(#paint4_linear_5687_13602)'
      />
      <path
        d='M198.524 198.492H121.519L198.524 275.497V198.492Z'
        fill='url(#paint5_linear_5687_13602)'
      />
      <path
        d='M198.524 198.492V121.487L121.519 198.492H198.524Z'
        fill='url(#paint6_linear_5687_13602)'
      />
      <path
        d='M198.523 198.492H275.529L198.523 121.487V198.492Z'
        fill='url(#paint7_linear_5687_13602)'
      />
      <defs>
        <linearGradient
          id='paint0_linear_5687_13602'
          x1='117.104'
          y1='99.2222'
          x2='326.919'
          y2='99.2222'
          gradientUnits='userSpaceOnUse'
        >
          <stop stopColor='#E6AF7B' />
          <stop offset='0.42' stopColor='#F3C07A' />
          <stop offset='0.8' stopColor='#C5A48A' />
          <stop offset='1' stopColor='#87A9A0' />
        </linearGradient>
        <linearGradient
          id='paint1_linear_5687_13602'
          x1='297.778'
          y1='117.056'
          x2='297.778'
          y2='326.871'
          gradientUnits='userSpaceOnUse'
        >
          <stop stopColor='#BACC9B' />
          <stop offset='0.29' stopColor='#9FCFA1' />
          <stop offset='0.52' stopColor='#81BEA5' />
          <stop offset='0.79' stopColor='#7EA3A3' />
          <stop offset='1' stopColor='#8D7997' />
        </linearGradient>
        <linearGradient
          id='paint2_linear_5687_13602'
          x1='99.2537'
          y1='279.88'
          x2='99.2537'
          y2='70.0654'
          gradientUnits='userSpaceOnUse'
        >
          <stop stopColor='#A85684' />
          <stop offset='0.27' stopColor='#C35074' />
          <stop offset='0.53' stopColor='#E27D69' />
          <stop offset='1' stopColor='#C9BC8F' />
        </linearGradient>
        <linearGradient
          id='paint3_linear_5687_13602'
          x1='70.0971'
          y1='297.73'
          x2='279.928'
          y2='297.73'
          gradientUnits='userSpaceOnUse'
        >
          <stop stopColor='#F6796C' />
          <stop offset='0.25' stopColor='#C5707C' />
          <stop offset='0.49' stopColor='#927393' />
          <stop offset='0.78' stopColor='#757FA3' />
          <stop offset='1' stopColor='#60A4AF' />
        </linearGradient>
        <linearGradient
          id='paint4_linear_5687_13602'
          x1='179.276'
          y1='256.25'
          x2='256.281'
          y2='179.245'
          gradientUnits='userSpaceOnUse'
        >
          <stop stopColor='#757FA3' />
          <stop offset='1' stopColor='#60A4AF' />
        </linearGradient>
        <linearGradient
          id='paint5_linear_5687_13602'
          x1='217.787'
          y1='256.234'
          x2='140.782'
          y2='179.229'
          gradientUnits='userSpaceOnUse'
        >
          <stop stopColor='#C5707C' />
          <stop offset='1' stopColor='#ED986C' />
        </linearGradient>
        <linearGradient
          id='paint6_linear_5687_13602'
          x1='140.766'
          y1='217.739'
          x2='217.771'
          y2='140.734'
          gradientUnits='userSpaceOnUse'
        >
          <stop stopColor='#F3C07A' />
          <stop offset='1' stopColor='#ED986C' />
        </linearGradient>
        <linearGradient
          id='paint7_linear_5687_13602'
          x1='179.276'
          y1='140.734'
          x2='256.281'
          y2='217.739'
          gradientUnits='userSpaceOnUse'
        >
          <stop stopColor='#5CB6A5' />
          <stop offset='1' stopColor='#99CC99' />
        </linearGradient>
      </defs>
    </svg>
  );
}
