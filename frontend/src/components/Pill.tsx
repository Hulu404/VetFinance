import type { ReactNode } from 'react'
import './Pill.css'

export type PillVariant = 'warning' | 'danger' | 'success' | 'neutral' | 'vetmanager' | 'bot' | 'on-dark'

export function Pill({ variant = 'warning', children }: { variant?: PillVariant; children: ReactNode }) {
  if (children === null || children === undefined || children === '') return null
  return <span className={`pill pill--${variant}`}>{children}</span>
}
