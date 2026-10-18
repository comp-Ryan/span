/** Browser "call" with Span: listen → hand the words to Span → Span speaks → listen again, until the owner hangs up. */
export type CallPhase = 'idle' | 'listening' | 'thinking' | 'speaking' | 'resting'
export type CallState = { active: boolean; phase: CallPhase; noSpeech: number }
export type CallEvent =
  | { type: 'start' } | { type: 'hangup' } | { type: 'heard' } | { type: 'no_speech' } | { type: 'mic_error' }
  | { type: 'speech_started' } | { type: 'speech_ended' }

export const initialCall: CallState = { active: false, phase: 'idle', noSpeech: 0 }
export const MAX_SILENCES = 3

export function callReducer(state: CallState, event: CallEvent): CallState {
  switch (event.type) {
    case 'start': return { active: true, phase: 'listening', noSpeech: 0 }
    case 'hangup': case 'mic_error': return { ...initialCall }
    case 'heard': return state.active ? { ...state, phase: 'thinking', noSpeech: 0 } : state
    case 'no_speech': {
      if (!state.active) return state
      const n = state.noSpeech + 1
      return { ...state, noSpeech: n, phase: n >= MAX_SILENCES ? 'resting' : 'listening' }
    }
    case 'speech_started': return state.active ? { ...state, phase: 'speaking' } : state
    case 'speech_ended': return state.active ? { active: true, phase: 'listening', noSpeech: 0 } : state
  }
}

export const callStatusLabel = (s: CallState) =>
  s.phase === 'listening' ? 'Listening… just talk' : s.phase === 'thinking' ? 'Span is working on it' : s.phase === 'speaking' ? 'Span is speaking'
    : s.phase === 'resting' ? 'Quiet for a while. Tap the mic or say something after Span speaks.' : ''
