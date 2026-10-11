import { Link } from 'react-router-dom'
import { PageHeader } from '../components/PageHeader'
import { usePageTitle } from '../lib/usePageTitle'

/** Opened by typing the address of a section that is not built yet. */
export function ComingSoonPage({ title }: { title: string }) {
  return (
    <>
      <PageHeader title={title} />
      <div className="state-card">
        <p className="state-card__text">Этот раздел откроем позже. Сейчас доступен Рабочий стол.</p>
        <Link className="btn" to="/">
          На Рабочий стол
        </Link>
      </div>
    </>
  )
}

export function NotFoundPage() {
  usePageTitle('Страница не найдена')
  return (
    <>
      <PageHeader title="Такой страницы нет" />
      <div className="state-card">
        <Link className="btn" to="/">
          На Рабочий стол
        </Link>
      </div>
    </>
  )
}
