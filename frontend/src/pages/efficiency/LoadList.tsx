import type { ReactNode } from 'react'
import type { DoctorLoad, EfficiencyReport, RoomLoad } from '../../api/types'
import { FigureButton } from '../../components/FigureButton'
import { LoadBar } from '../../components/LoadBar'
import { formatCount, formatFigure, pluralRu } from '../../lib/format'

export function hoursWord(count: number): string {
  return pluralRu(count, 'час', 'часа', 'часов')
}

interface HoursRow {
  id: string
  name: string
  load: RoomLoad['load_pct'] | null
  busy: RoomLoad['busy_hours'] | null
  available: RoomLoad['available_hours'] | null
  free: RoomLoad['free_hours'] | null
}

function captionOf(row: HoursRow): string | null {
  if (!row.busy || !row.available || !row.free) return null
  return `${formatFigure(row.busy)} из ${formatFigure(row.available)} ч · свободно ${formatFigure(row.free)} ч`
}

function spokenOf(row: HoursRow): string {
  if (!row.load || !row.busy || !row.available || !row.free) return row.name
  return `${row.name}, загрузка ${formatFigure(row.load)}, занято ${formatFigure(row.busy)} из ${formatFigure(row.available)} ${hoursWord(row.available.value)}, свободно ${formatFigure(row.free)}`
}

function barLabelOf(row: HoursRow): string {
  if (!row.load || !row.busy || !row.available) return ""
  return `Загрузка ${formatFigure(row.load)}, занято ${formatFigure(row.busy)} из ${formatFigure(row.available)} ${hoursWord(row.available.value)}`
}

function LoadItem({ row, index, kind, missing }: { row: HoursRow; index: number; kind: 'room' | 'doctor'; missing: ReactNode }) {
  const figureKey = `${kind === 'room' ? 'rooms' : 'doctors'}.${index}.load_pct`
  return (
    <li className="eff-load__item" data-testid="efficiency-load-row" data-id={row.id} data-kind={kind}>
      <LoadBar barLabel={barLabelOf(row)} name={row.name} load={row.load} caption={captionOf(row)} spoken={spokenOf(row)} missing={missing} figureKey={row.load ? figureKey : undefined} />
    </li>
  )
}

interface LoadListProps {
  report: EfficiencyReport
  onSetHours: () => void
}

function roomRow(room: RoomLoad): HoursRow {
  return { id: room.id, name: room.name, load: room.load_pct, busy: room.busy_hours, available: room.available_hours, free: room.free_hours }
}

function doctorRow(doctor: DoctorLoad): HoursRow {
  return { id: doctor.id, name: doctor.name, load: doctor.load_pct, busy: doctor.busy_hours, available: doctor.available_hours, free: doctor.free_hours }
}

function NoHours({ doctor, onSetHours }: { doctor: DoctorLoad; onSetHours: () => void }) {
  return (
    <>
      <span data-testid="efficiency-no-hours">часы приёма не указаны</span>
      <FigureButton figure={doctor.visits} title={`${doctor.name} · приёмы`} className="eff-load__visits">
        {`${formatCount(doctor.visits.value)} ${pluralRu(doctor.visits.value, 'приём', 'приёма', 'приёмов')}`}
      </FigureButton>
      <button type="button" className="btn btn--text" data-testid="efficiency-hours-open-row" onClick={onSetHours}>
        Указать
      </button>
    </>
  )
}

/** The list of rooms (the room schedule exists) or of doctors (the fallback mode, the main one at the start). */
export function LoadList({ report, onSetHours }: LoadListProps) {
  if (report.load_by === 'rooms') {
    return (
      <ul className="eff-load">
        {report.rooms.map((room, index) => (
          <LoadItem key={room.id} row={roomRow(room)} index={index} kind="room" missing={<span>расписание не передано</span>} />
        ))}
      </ul>
    )
  }
  return (
    <ul className="eff-load">
      {report.doctors.map((doctor, index) => (
        <LoadItem key={doctor.id} row={doctorRow(doctor)} index={index} kind="doctor" missing={<NoHours doctor={doctor} onSetHours={onSetHours} />} />
      ))}
    </ul>
  )
}
