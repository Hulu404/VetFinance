import type { ReactNode } from 'react'

interface DashEmptyProps {
  icon: string
  title?: string
  text: string
  actions?: ReactNode
  testId?: string
  /** Level of the title: 2 where no section heading comes before it, 3 inside a section. */
  level?: 2 | 3
  /** The card of "all is well" has no accent: it is a plain white card. */
  className?: string
}

/** White card with an emoji, a title and a text (v6 `.empty`): no accounts, empty month, no advice. */
export function DashEmpty({ icon, title, text, actions, testId, level = 3, className }: DashEmptyProps) {
  const Heading = level === 2 ? 'h2' : 'h3'
  return (
    <div className={className ? `dash-empty ${className}` : 'dash-empty'} data-testid={testId}>
      <span className="dash-empty__icon" aria-hidden="true">
        {icon}
      </span>
      <div>
        {title && <Heading className="dash-empty__title">{title}</Heading>}
        <p className={title ? 'dash-empty__text' : 'dash-empty__text dash-empty__text--plain'}>{text}</p>
        {actions && <div className="dash-empty__actions">{actions}</div>}
      </div>
    </div>
  )
}
