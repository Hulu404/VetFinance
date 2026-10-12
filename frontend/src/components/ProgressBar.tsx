import './ProgressBar.css'

interface ProgressBarProps {
  /** Whole percent while bytes go out; null while the server parses the file. */
  percent: number | null
  label: string
}

export function ProgressBar({ percent, label }: ProgressBarProps) {
  const determinate = percent !== null
  return (
    <div className="progress">
      <div
        className={determinate ? 'progress__track' : 'progress__track progress__track--busy'}
        role="progressbar"
        aria-label="Загрузка выписки"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={determinate ? percent : undefined}
      >
        <div className="progress__fill" style={determinate ? { width: `${percent}%` } : undefined} />
      </div>
      <p className="progress__text" aria-live="polite">
        {determinate ? `${label} ${percent}%` : label}
      </p>
    </div>
  )
}
