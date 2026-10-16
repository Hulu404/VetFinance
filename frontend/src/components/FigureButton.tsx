import type { ReactNode } from 'react'
import { formatDeltaAware } from '../lib/format'
import { FigureTip, type TipFigure } from './FigureTip'
import './FigureButton.css'

interface FigureButtonProps {
  figure: TipFigure
  /** Name of the metric in the tip header and in the accessible name. */
  title: string
  /** Visible text; the formatted figure by default. */
  children?: ReactNode
  className?: string
  /** Text of the accessible name before ", показать из чего состоит"; the formatted figure by default. */
  spokenValue?: string
  /** Path of the API field, for `data-figure`. */
  figureKey?: string
  /** Name of the tip header's emoji. */
  emoji?: string
  /** Replaces the value in the tip header; the visible text and the accessible name stay as given. */
  tipValue?: string
}

/** A number in a table cell or a line that opens the tip with its breakdown (rule 4 of CLAUDE.md). */
export function FigureButton({ figure, title, children, className, spokenValue, figureKey, emoji, tipValue }: FigureButtonProps) {
  const text = formatDeltaAware(figure)
  return (
    <FigureTip figure={figure} title={title} emoji={emoji} valueText={tipValue}>
      {(triggerProps) => (
        <button
          {...triggerProps}
          type="button"
          data-figure={figureKey}
          className={className ? `figbtn ${className}` : 'figbtn'}
          aria-label={`${spokenValue ?? text}, показать из чего состоит`}
        >
          {children ?? text}
        </button>
      )}
    </FigureTip>
  )
}
