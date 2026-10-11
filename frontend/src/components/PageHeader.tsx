import type { ReactNode } from 'react'
import { usePageTitle } from '../lib/usePageTitle'
import './PageHeader.css'

interface PageHeaderProps {
  title: string
  /** Line under the title: data freshness, not promo text. */
  subtitle?: ReactNode
  /** When true the subtitle is replaced by a loading placeholder. */
  subtitleLoading?: boolean
  actions?: ReactNode
}

export function PageHeader({ title, subtitle, subtitleLoading = false, actions }: PageHeaderProps) {
  usePageTitle(title)
  return (
    <header className="page-head">
      <div>
        <h1 tabIndex={-1}>{title}</h1>
        {subtitleLoading ? (
          <span className="page-head__skeleton" aria-hidden="true" />
        ) : subtitle ? (
          <p className="page-head__sub">{subtitle}</p>
        ) : null}
      </div>
      {actions && <div className="page-head__actions">{actions}</div>}
    </header>
  )
}
