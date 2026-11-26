import type { SVGProps } from 'react'

const base: SVGProps<SVGSVGElement> = {
  width: 16, height: 16, viewBox: '0 0 16 16', fill: 'none', stroke: 'currentColor',
  strokeWidth: 1.6, strokeLinecap: 'round', strokeLinejoin: 'round', 'aria-hidden': true,
}
type P = SVGProps<SVGSVGElement>

export const ErrorIcon = (p: P) => (
  <svg {...base} {...p}><circle cx="8" cy="8" r="6.2" /><path d="M5.8 5.8l4.4 4.4M10.2 5.8l-4.4 4.4" /></svg>
)
export const WarnIcon = (p: P) => (
  <svg {...base} {...p}><path d="M8 2.2l6.2 11H1.8z" /><path d="M8 6.6v3.2M8 11.6v.1" /></svg>
)
export const InfoIcon = (p: P) => (
  <svg {...base} {...p}><circle cx="8" cy="8" r="6.2" /><path d="M8 7.2v4M8 4.8v.1" /></svg>
)
export const CheckIcon = (p: P) => (
  <svg {...base} {...p}><path d="M3 8.4l3.2 3.2L13 4.6" /></svg>
)
export const LockIcon = (p: P) => (
  <svg {...base} {...p}><rect x="3.4" y="7" width="9.2" height="6.6" rx="1.2" /><path d="M5.4 7V5.2a2.6 2.6 0 015.2 0V7" /></svg>
)
export const ChevronIcon = (p: P) => (
  <svg {...base} {...p}><path d="M5.6 3.6L10 8l-4.4 4.4" /></svg>
)
export const CloseIcon = (p: P) => (
  <svg {...base} {...p}><path d="M4 4l8 8M12 4l-8 8" /></svg>
)
