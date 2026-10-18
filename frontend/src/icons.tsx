import type { ReactNode } from 'react'

const sv = (d: ReactNode) => <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.7">{d}</svg>
export const ICONS = {
  chat: sv(<path d="M3 3.5h10a1 1 0 0 1 1 1v6a1 1 0 0 1-1 1H7l-3 2.5V11.5H3a1 1 0 0 1-1-1v-6a1 1 0 0 1 1-1z"/>),
  book: sv(<><rect x="2.5" y="4" width="11" height="8.5" rx="1"/><path d="M2.5 7h11"/></>),
  card: sv(<><rect x="2" y="4" width="12" height="9" rx="1.5"/><path d="M2 7.5h12M5 11h3"/></>),
  trend: sv(<path d="M2.5 12.5 6 8l3 2.5 4.5-6"/>),
  person: sv(<><circle cx="8" cy="5.5" r="2.5"/><path d="M3 14c.8-3 2.6-4 5-4s4.2 1 5 4"/></>),
  people: sv(<><circle cx="6" cy="5.5" r="2.5"/><path d="M1.5 13c.8-3 2.6-4 4.5-4s3.7 1 4.5 4M11 6l1.3 1.3L14.5 5"/></>),
  link: sv(<path d="M6.5 9.5l3-3M7 4.5l1-1a2.5 2.5 0 0 1 3.5 3.5l-1 1M9 11.5l-1 1A2.5 2.5 0 0 1 4.5 9l1-1"/>),
  check: sv(<path d="M3 8.5l3 3 7-7"/>),
  clock: sv(<><circle cx="8" cy="8" r="5.5"/><path d="M8 5v3.5l2 1.5"/></>),
  arrow: sv(<path d="M3 8h9M8.5 4.5 12 8l-3.5 3.5"/>),
  doc: sv(<><path d="M4 2h5.5L12 4.5V14H4z"/><path d="M9.5 2v2.5H12M6 8h4M6 10.5h4"/></>),
  bell: sv(<path d="M4 11V7a4 4 0 0 1 8 0v4l1 1.5H3zM6.5 14h3"/>),
  reply: sv(<path d="M6.5 4 3 7.5 6.5 11M3 7.5h6.5a3.5 3.5 0 0 1 3.5 3.5v1"/>),
  handshake: sv(<path d="M2 8l3-3h3l3 3M14 8l-3 3-2-1-2 1.5L4.5 9M8 5l2.5-1L14 8"/>),
}
