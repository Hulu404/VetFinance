// Helpers for mock Figures. Numbers are literals written by hand: the mock is a fake backend, the client never computes.
import type { Figure, FigureSource } from '../api/types'

export function rubFigure(
  value: number,
  breakdown: [string, number][],
  source: FigureSource[],
  note: string,
): Figure {
  return {
    value,
    unit: 'rub',
    breakdown: breakdown.map(([label, amount]) => ({ label, value: amount, unit: 'rub' as const })),
    source,
    note,
  }
}

export function countFigure(value: number, breakdown: [string, number][], source: FigureSource[], note: string): Figure {
  return {
    value,
    unit: 'count',
    breakdown: breakdown.map(([label, amount]) => ({ label, value: amount, unit: 'count' as const })),
    source,
    note,
  }
}
