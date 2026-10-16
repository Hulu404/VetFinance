import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { NormGauge } from './NormGauge'

function zoneAndMarker(container: HTMLElement) {
  const zone = container.querySelector('.gauge__zone') as HTMLElement
  const marker = container.querySelector('.gauge__marker') as HTMLElement
  return { zone, marker }
}

describe('NormGauge', () => {
  it('is an image with the words for a screen reader', () => {
    render(<NormGauge minPct={22} maxPct={28} actualPct={24.6} tone="good" label="Норма 22–28%, у вас 24,6%: в норме" />)

    expect(screen.getByRole('img', { name: 'Норма 22–28%, у вас 24,6%: в норме' })).toHaveAttribute('data-testid', 'norm-gauge')
  })

  it('scales the track to 1.6 of the upper bound, so the zone and the marker keep their places', () => {
    const { container } = render(<NormGauge minPct={20} maxPct={25} actualPct={27.4} tone="bad" label="x" />)
    const { zone, marker } = zoneAndMarker(container)

    // top = max(25 * 1.6, 27.4 * 1.25) = 40
    expect(zone.style.left).toBe('50%')
    expect(zone.style.width).toBe('12.5%')
    expect(marker.style.left).toBe('68.5%')
    expect(marker).toHaveClass('gauge__marker--bad')
  })

  it('stretches the track when the value is far above the norm', () => {
    const { container } = render(<NormGauge minPct={3} maxPct={6} actualPct={20} tone="bad" label="x" />)
    const { zone } = zoneAndMarker(container)

    // top = max(6 * 1.6, 20 * 1.25) = 25
    expect(zone.style.left).toBe('12%')
    expect(zone.style.width).toBe('12%')
  })

  it('draws no left border for a norm that starts at zero', () => {
    const { container } = render(<NormGauge minPct={0} maxPct={0.8} actualPct={1.9} tone="bad" label="x" />)
    const { zone } = zoneAndMarker(container)

    expect(zone).toHaveClass('gauge__zone--open-left')
    expect(zone.style.left).toBe('0%')
  })

  it('runs the zone to the end of the track when there is no upper bound', () => {
    const { container } = render(<NormGauge minPct={12} maxPct={null} actualPct={11.7} tone="bad" label="x" />)
    const { zone } = zoneAndMarker(container)

    expect(zone).toHaveClass('gauge__zone--open-right')
    // top = max(12 * 2, 11.7 * 1.25) = 24: the zone runs from 50% to the end
    expect(zone.style.left).toBe('50%')
    expect(zone.style.width).toBe('50%')
  })

  it('keeps the marker inside the track: the centre stays within 2-98%, a negative value sits at the left edge', () => {
    const high = render(<NormGauge minPct={1} maxPct={2} actualPct={100} tone="warn" label="x" />)
    // top = max(2 * 1.6, 100 * 1.25) = 125: the marker is at 80%
    expect(zoneAndMarker(high.container).marker.style.left).toBe('80%')
    high.unmount()
    const negative = render(<NormGauge minPct={12} maxPct={20} actualPct={-4} tone="bad" label="x" />)
    expect(zoneAndMarker(negative.container).marker.style.left).toBe('2%')
  })

  it('hides the drawing from assistive technology', () => {
    const { container } = render(<NormGauge minPct={5} maxPct={10} actualPct={6.9} tone="neutral" label="x" />)

    for (const part of container.querySelectorAll('.gauge__zone, .gauge__marker')) expect(part).toHaveAttribute('aria-hidden', 'true')
  })
})
