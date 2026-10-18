import { describe, expect, it } from 'vitest'
import { callReducer, initialCall, type CallState } from './voiceCall'

const step = (s: CallState, ...events: Parameters<typeof callReducer>[1][]) => events.reduce((acc, e) => callReducer(acc, e), s)

describe('browser call controller', () => {
  it('starts listening when the call starts and hangs up to idle', () => {
    const s = callReducer(initialCall, { type: 'start' })
    expect(s).toEqual({ active: true, phase: 'listening', noSpeech: 0 })
    expect(callReducer(s, { type: 'hangup' })).toEqual({ active: false, phase: 'idle', noSpeech: 0 })
  })
  it('hands the recognized text over and waits for Span, then speaks, then listens again', () => {
    const s = step(initialCall, { type: 'start' }, { type: 'heard' })
    expect(s.phase).toBe('thinking')
    const speaking = callReducer(s, { type: 'speech_started' })
    expect(speaking.phase).toBe('speaking')
    expect(callReducer(speaking, { type: 'speech_ended' })).toEqual({ active: true, phase: 'listening', noSpeech: 0 })
  })
  it('re-arms after silence up to three times, then rests without ending the call', () => {
    let s = step(initialCall, { type: 'start' })
    s = callReducer(s, { type: 'no_speech' }); expect(s).toEqual({ active: true, phase: 'listening', noSpeech: 1 })
    s = step(s, { type: 'no_speech' }, { type: 'no_speech' })
    expect(s).toEqual({ active: true, phase: 'resting', noSpeech: 3 })
    expect(callReducer(s, { type: 'speech_ended' }).phase).toBe('listening')  // Span spoke again: listen again
  })
  it('does not listen again after speech when the call is not active, and mic errors end the call', () => {
    const idle = callReducer(initialCall, { type: 'speech_ended' })
    expect(idle).toEqual(initialCall)
    const s = step(initialCall, { type: 'start' }, { type: 'mic_error' })
    expect(s).toEqual({ active: false, phase: 'idle', noSpeech: 0 })
  })
})
