/**
 * icons.jsx — IntentOS Icon System
 * =================================
 * Single source of truth for all icons used across the dashboard.
 *
 * STRATEGY:
 *   - Only imports icons actually used (tree-shakeable, no bundle bloat)
 *   - All icons routed through <I> wrapper for consistent sizing & color
 *   - Skill → icon mapping centralized here so ExecutionTimeline + any
 *     future component always stay in sync
 *
 * USAGE:
 *   import { I, skillIcon, statusIcon, NavIcons } from './icons'
 *   <I icon={faCheck} color="var(--success)" size="sm" />
 */

import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'

// ── Solid icons ─────────────────────────────────────────────────────────────
import {
  faCheck,
  faXmark,
  faClock,
  faSpinner,
  faBolt,
  faCircleExclamation,
  faTriangleExclamation,
  faLock,
  faGlobe,
  faFolder,
  faFolderPlus,
  faFile,
  faFileCode,
  faPen,
  faBook,
  faTerminal,
  faCode,
  faPlay,
  faRocket,
  faBrain,
  faEnvelope,
  faEnvelopeOpen,
  faCalendar,
  faCalendarCheck,
  faVideo,
  faMessage,
  faMagnifyingGlass,
  faCamera,
  faChartBar,
  faGear,
  faPlugCircleBolt,
  faArrowsRotate,
  faClipboard,
  faPause,
  faForwardStep,
  faCircleStop,
  faStar,
  faListCheck,
  faHouseChimney,
  faTableColumns,
  faWrench,
  faEllipsis,
  faAngleRight,
  faCircle,
  faMicrophone,
  faPaperPlane,
  faDownload,
  faCloudArrowUp,
  faTrash,
  faArrowRight,
  faDatabase,
  faNetworkWired,
  faEye,
  faEyeSlash,
} from '@fortawesome/free-solid-svg-icons'

import {
  faCircle as farCircle,
  faClock as farClock,
} from '@fortawesome/free-regular-svg-icons'

// ─────────────────────────────────────────────────────────────────────────────
// Base wrapper — keeps sizing & style consistent everywhere
// ─────────────────────────────────────────────────────────────────────────────

/**
 * I — universal icon wrapper
 * @param {object} props
 * @param {object} props.icon   - FA icon object, e.g. faCheck
 * @param {string} [props.color]  - CSS color string
 * @param {string} [props.size]   - FA size string: "xs"|"sm"|"lg"|"xl"|"2x" etc.
 * @param {object} [props.style]  - extra inline styles
 * @param {string} [props.className]
 * @param {boolean} [props.spin]
 * @param {boolean} [props.pulse]
 */
export function I({ icon, color, size = 'sm', style = {}, className, spin, pulse }) {
  return (
    <FontAwesomeIcon
      icon={icon}
      size={size}
      spin={spin}
      pulse={pulse}
      className={className}
      style={{ color: color || 'inherit', ...style }}
    />
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Skill → Icon mapping  (ExecutionTimeline + any future consumers)
// ─────────────────────────────────────────────────────────────────────────────

const SKILL_ICON_MAP = {
  // Browser
  'browser.navigate':      { icon: faGlobe,           label: 'Opening browser' },
  'browser.search':        { icon: faMagnifyingGlass, label: 'Searching the web' },
  'browser.screenshot':    { icon: faCamera,           label: 'Taking screenshot' },
  'browser.extract_text':  { icon: faBook,             label: 'Extracting page text' },
  'browser.fill_form':     { icon: faPen,              label: 'Filling form' },
  'browser.click':         { icon: faPlay,             label: 'Clicking element' },
  // Files
  'files.write_file':      { icon: faPen,              label: 'Writing file' },
  'files.read_file':       { icon: faBook,             label: 'Reading file' },
  'files.create_dir':      { icon: faFolderPlus,       label: 'Creating directory' },
  'files.delete':          { icon: faTrash,            label: 'Deleting file' },
  'files.move':            { icon: faArrowRight,       label: 'Moving file' },
  'files.copy':            { icon: faClipboard,        label: 'Copying file' },
  'files.list_dir':        { icon: faFolder,           label: 'Listing directory' },
  'files.download':        { icon: faDownload,         label: 'Downloading file' },
  // Apps
  'apps.open_app':         { icon: faRocket,           label: 'Launching application' },
  'apps.press_keys':       { icon: faCode,             label: 'Pressing keys' },
  'apps.type_text':        { icon: faPen,              label: 'Typing text' },
  // Terminal
  'terminal.execute':      { icon: faTerminal,         label: 'Running command' },
  'terminal.execute_background': { icon: faTerminal,   label: 'Running background command' },
  // AI
  'ai.ask':                { icon: faBrain,            label: 'Thinking…' },
  'ai.summarize':          { icon: faListCheck,        label: 'Summarizing' },
  // Extension — Google apps
  'extension.navigate':    { icon: faGlobe,            label: 'Navigating page' },
  'extension.getEvents':   { icon: faCalendar,         label: 'Fetching calendar events' },
  'extension.createEvent': { icon: faCalendarCheck,    label: 'Creating calendar event' },
  'extension.sendMail':    { icon: faPaperPlane,       label: 'Sending email' },
  'extension.composeMail': { icon: faPen,              label: 'Composing email' },
  'extension.getUnread':   { icon: faEnvelopeOpen,     label: 'Checking inbox' },
  'extension.searchMail':  { icon: faMagnifyingGlass,  label: 'Searching email' },
  'extension.searchYouTube': { icon: faMagnifyingGlass, label: 'Searching YouTube' },
  'extension.playYouTube': { icon: faPlay,             label: 'Playing video' },
  'extension.joinMeet':    { icon: faVideo,            label: 'Joining meeting' },
  'extension.scheduleMeet':{ icon: faVideo,            label: 'Scheduling meeting' },
  'extension.searchDrive': { icon: faMagnifyingGlass,  label: 'Searching Drive' },
  'extension.web_agent':   { icon: faPlugCircleBolt,   label: 'Running web agent' },
  'extension.get_events':  { icon: faCalendar,         label: 'Fetching calendar events' },
  // Messaging
  'messaging.send_message':{ icon: faMessage,          label: 'Sending message' },
  'messaging.open_chat':   { icon: faMessage,          label: 'Opening chat' },
  // Vision
  'vision.capture_screen': { icon: faCamera,           label: 'Capturing screen' },
  // RAG
  'rag.search':            { icon: faDatabase,         label: 'Searching memory' },
  'rag.store':             { icon: faDatabase,         label: 'Storing memory' },
}

/**
 * Returns { icon (FA object), label (string) } for a given skill.action pair.
 */
export function skillIcon(skill, action, description) {
  const key = `${skill}.${action}`
  const match = SKILL_ICON_MAP[key]
  if (match) return { icon: match.icon, label: description || match.label }

  // Fallback by skill category
  const fallbacks = {
    browser:   { icon: faGlobe,         label: description || 'Browser action' },
    files:     { icon: faFile,          label: description || 'File operation' },
    apps:      { icon: faRocket,        label: description || 'App action' },
    terminal:  { icon: faTerminal,      label: description || 'Terminal command' },
    ai:        { icon: faBrain,         label: description || 'AI reasoning' },
    extension: { icon: faPlugCircleBolt,label: description || 'Extension action' },
    messaging: { icon: faMessage,       label: description || 'Messaging' },
    vision:    { icon: faCamera,        label: description || 'Screen action' },
    rag:       { icon: faDatabase,      label: description || 'Memory lookup' },
  }
  return fallbacks[skill] || { icon: faGear, label: description || key }
}

// ─────────────────────────────────────────────────────────────────────────────
// Status icon helpers
// ─────────────────────────────────────────────────────────────────────────────

export const STATUS_ICONS = {
  done:    { icon: faCheck,              color: '#10b981' },
  running: { icon: faSpinner,            color: '#f59e0b', spin: true },
  failed:  { icon: faXmark,             color: '#ef4444' },
  skipped: { icon: faForwardStep,        color: '#6b7280' },
  pending: { icon: farCircle,            color: 'rgba(255,255,255,0.2)' },
  queued:  { icon: farClock,             color: 'rgba(255,255,255,0.2)' },
  blocked: { icon: faLock,              color: '#f59e0b' },
  warning: { icon: faTriangleExclamation, color: '#f59e0b' },
  confirm: { icon: faCircleExclamation, color: '#7c6fff' },
}

export function statusIcon(status) {
  return STATUS_ICONS[status] || STATUS_ICONS.pending
}

// ─────────────────────────────────────────────────────────────────────────────
// Nav / UI icon exports — used in App.jsx nav items, control bar, etc.
// ─────────────────────────────────────────────────────────────────────────────

export const NavIcons = {
  intentRunner: faBolt,
  auditLog:     faListCheck,
  skills:       faPlugCircleBolt,
  settings:     faGear,
  history:      faBook,
}

export const ControlIcons = {
  pause:  faPause,
  resume: faPlay,
  skip:   faForwardStep,
  abort:  faCircleStop,
  retry:  faArrowsRotate,
  copy:   faClipboard,
  mic:    faMicrophone,
  run:    faArrowRight,
}

export const StatusBadgeIcons = {
  running:   faBolt,
  completed: faCheck,
  failed:    faXmark,
  paused:    faPause,
  idle:      faCircle,
}

// Re-export raw icons for direct usage where needed
export {
  faCheck, faXmark, faBolt, faSpinner, faGlobe, faTerminal, faBrain,
  faRocket, faGear, faClipboard, faPause, faPlay, faForwardStep,
  faCircleStop, faArrowsRotate, faMicrophone, faArrowRight, faEye, faEyeSlash,
  faAngleRight, faChartBar, faNetworkWired, faWrench, faEllipsis, faCircle,
  faTriangleExclamation, faCircleExclamation, faLock, faStar, faHouseChimney,
  faTableColumns, faCloudArrowUp, faFileCode, faEnvelope, faCalendar, faMessage,
  faListCheck, faFile, faFolder, faPlugCircleBolt,
}
