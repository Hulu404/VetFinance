import { useEffect } from 'react'

/** "Название экрана · ВетФинанс" */
export function usePageTitle(title: string): void {
  useEffect(() => {
    document.title = `${title} · ВетФинанс`
  }, [title])
}
