import type { ReactNode } from 'react'
import { usePageTitle } from '../lib/usePageTitle'
import { BalanceBadge } from './BalanceBadge'
import './PageHeader.css'

interface PageHeaderProps {
  title: string
  /** Line under the title: data freshness, not promo text. */
  subtitle?: ReactNode
  /** When true the subtitle is replaced by a loading placeholder. */
  subtitleLoading?: boolean
  actions?: ReactNode
  /** Total balance in the corner: on every screen except the dashboard (design/screens/shell.md). */
  balance?: boolean
}

export function PageHeader({ title, subtitle, subtitleLoading = false, actions, balance = false }: PageHeaderProps) {
  usePageTitle(title)
  return (
    <header className="page-head">
      <div className="page-head__title">
        <h1 tabIndex={-1}>{title}</h1>
        {subtitleLoading ? (
          <span className="page-head__skeleton" aria-hidden="true" />
        ) : subtitle ? (
          <p className="page-head__sub" data-testid="page-subtitle">
            {subtitle}
          </p>
        ) : null}
      </div>
      {(actions || balance) && (
        <div className="page-head__right">
          {actions && <div className="page-head__actions">{actions}</div>}
          {balance && <BalanceBadge />}
        </div>
      )}
    </header>
  )
}
