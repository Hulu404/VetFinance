import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import './Banner.css'

interface BannerAction {
  label: string
  /** Internal route. */
  to?: string
  onClick?: () => void
}

interface BannerProps {
  variant: 'warning' | 'danger'
  children: ReactNode
  action?: BannerAction
  testId?: string
}

/** Message strip above a screen (design/components.md, section 12). It disappears when its cause is gone. */
export function Banner({ variant, children, action, testId }: BannerProps) {
  return (
    <div className={`banner banner--${variant}`} role={variant === 'danger' ? 'alert' : 'status'} data-testid={testId}>
      <span className="banner__text">{children}</span>
      {action &&
        (action.to ? (
          <Link className="banner__action" to={action.to}>
            {action.label}
          </Link>
        ) : (
          <button type="button" className="banner__action" onClick={action.onClick}>
            {action.label}
          </button>
        ))}
    </div>
  )
}
