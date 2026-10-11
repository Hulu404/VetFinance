import iconsSprite from '../assets/icons.svg?raw'

export type IconId = 'ic-home' | 'ic-tx' | 'ic-price' | 'ic-report' | 'ic-plan' | 'ic-anal' | 'ic-set' | 'ic-logo'

/** The sprite from design/icons.svg, inserted once near the root. It is our own static asset, not user input. */
export function IconSprite() {
  return <div aria-hidden="true" dangerouslySetInnerHTML={{ __html: iconsSprite }} />
}

export function Icon({ id, className }: { id: IconId; className?: string }) {
  return (
    <svg className={className ? `icon ${className}` : 'icon'} viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <use href={`#${id}`} />
    </svg>
  )
}
