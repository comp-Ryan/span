/** Browser "call" with Span: listen → hand the words to Span → Span speaks → listen again, until the owner hangs up. */
export type CallPhase = 'idle' | 'listening' | 'thinking' | 'speaking' | 'resting'
/** `muted`: Span stays silent (text only) but the call keeps listening; remembered across hangups. */
export type CallState = { active: boolean; phase: CallPhase; noSpeech: number; muted: boolean }
export type CallEvent =
  | { type: 'start' } | { type: 'hangup' } | { type: 'heard' } | { type: 'no_speech' } | { type: 'mic_error' }
  | { type: 'speech_started' } | { type: 'speech_ended' } | { type: 'mute' } | { type: 'unmute' }

export const initialCall: CallState = { active: false, phase: 'idle', noSpeech: 0, muted: false }
export const MAX_SILENCES = 3

export function callReducer(state: CallState, event: CallEvent): CallState {
  switch (event.type) {
    case 'start': return { active: true, phase: 'listening', noSpeech: 0, muted: state.muted }
    case 'hangup': case 'mic_error': return { ...initialCall, muted: state.muted }
    case 'heard': return state.active ? { ...state, phase: 'thinking', noSpeech: 0 } : state
    case 'no_speech': {
      if (!state.active) return state
      const n = state.noSpeech + 1
      return { ...state, noSpeech: n, phase: n >= MAX_SILENCES ? 'resting' : 'listening' }
    }
    // Muted: nothing to say aloud, so a "speaking" turn is over before it starts and the mic re-arms.
    case 'speech_started': return !state.active ? state : state.muted ? { ...state, phase: 'listening', noSpeech: 0 } : { ...state, phase: 'speaking' }
    case 'speech_ended': return state.active ? { ...state, phase: 'listening', noSpeech: 0 } : state
    case 'mute': return state.active && state.phase === 'speaking' ? { ...state, phase: 'listening', noSpeech: 0, muted: true } : { ...state, muted: true }
    case 'unmute': return { ...state, muted: false }
  }
}

export const callStatusLabel = (s: CallState) =>
  s.phase === 'listening' ? (s.muted ? 'Listening… Span answers in text while muted' : 'Listening… just talk') : s.phase === 'thinking' ? 'Span is working on it' : s.phase === 'speaking' ? 'Span is speaking'
    : s.phase === 'resting' ? 'Quiet for a while. Tap the mic or say something after Span speaks.' : ''
