import type { ReactNode } from 'react'
import { Pill } from './Pill'

export const NETWORK_ERROR_TEXT = 'Нет связи с сервером. Проверьте интернет и повторите.'
export const SERVER_ERROR_TEXT = 'Это сбой на нашей стороне, ваши данные не пострадали. Попробуйте ещё раз.'

interface EmptyStateProps {
  icon: string
  title: string
  text: string
  actions?: ReactNode
  testId?: string
}

/** White card with an icon, a title, a text and buttons (design/screens/transactions.md, "Пусто"). */
export function EmptyState({ icon, title, text, actions, testId }: EmptyStateProps) {
  return (
    <div className="state-card state-card--wide state-card--center" data-testid={testId}>
      <span className="state-card__emoji" aria-hidden="true">
        {icon}
      </span>
      <h3 className="state-card__title">{title}</h3>
      <p className="state-card__text">{text}</p>
      {actions && <div className="state-card__actions">{actions}</div>}
    </div>
  )
}

interface LoadErrorCardProps {
  title: string
  network: boolean
  retrying: boolean
  onRetry: () => void
  testId?: string
}

/** Block that replaces content that failed to load: red left border, a word, a button. */
export function LoadErrorCard({ title, network, retrying, onRetry, testId }: LoadErrorCardProps) {
  return (
    <div className="state-card state-card--wide state-card--error" role="alert" data-testid={testId}>
      <Pill variant="danger">не загрузилось</Pill>
      <h3 className="state-card__title">{title}</h3>
      <p className="state-card__text">{network ? NETWORK_ERROR_TEXT : SERVER_ERROR_TEXT}</p>
      <button type="button" className="btn" onClick={onRetry} disabled={retrying}>
        {retrying ? 'Загружаем…' : 'Повторить'}
      </button>
    </div>
  )
}

/** Message inside a dialog or card: red text on a soft red background, announced at once. */
export function InlineAlert({ children, testId }: { children: ReactNode; testId?: string }) {
  return (
    <div className="inline-alert" role="alert" data-testid={testId}>
      {children}
    </div>
  )
}
