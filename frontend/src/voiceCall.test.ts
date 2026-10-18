import { describe, expect, it } from 'vitest'
import { callReducer, initialCall, type CallState } from './voiceCall'

const step = (s: CallState, ...events: Parameters<typeof callReducer>[1][]) => events.reduce((acc, e) => callReducer(acc, e), s)

describe('browser call controller', () => {
  it('starts listening when the call starts and hangs up to idle', () => {
    const s = callReducer(initialCall, { type: 'start' })
    expect(s).toEqual({ active: true, phase: 'listening', noSpeech: 0, muted: false })
    expect(callReducer(s, { type: 'hangup' })).toEqual({ active: false, phase: 'idle', noSpeech: 0, muted: false })
  })
  it('hands the recognized text over and waits for Span, then speaks, then listens again', () => {
    const s = step(initialCall, { type: 'start' }, { type: 'heard' })
    expect(s.phase).toBe('thinking')
    const speaking = callReducer(s, { type: 'speech_started' })
    expect(speaking.phase).toBe('speaking')
    expect(callReducer(speaking, { type: 'speech_ended' })).toEqual({ active: true, phase: 'listening', noSpeech: 0, muted: false })
  })
  it('re-arms after silence up to three times, then rests without ending the call', () => {
    let s = step(initialCall, { type: 'start' })
    s = callReducer(s, { type: 'no_speech' }); expect(s).toEqual({ active: true, phase: 'listening', noSpeech: 1, muted: false })
    s = step(s, { type: 'no_speech' }, { type: 'no_speech' })
    expect(s).toEqual({ active: true, phase: 'resting', noSpeech: 3, muted: false })
    expect(callReducer(s, { type: 'speech_ended' }).phase).toBe('listening')  // Span spoke again: listen again
  })
  it('does not listen again after speech when the call is not active, and mic errors end the call', () => {
    const idle = callReducer(initialCall, { type: 'speech_ended' })
    expect(idle).toEqual(initialCall)
    const s = step(initialCall, { type: 'start' }, { type: 'mic_error' })
    expect(s).toEqual({ active: false, phase: 'idle', noSpeech: 0, muted: false })
  })
})

describe('mute (Span stays silent, the call keeps going in text)', () => {
  it('starts unmuted', () => {
    expect(initialCall.muted).toBe(false)
  })
  it('a muted call skips the speaking phase and goes straight back to listening', () => {
    const s = step(initialCall, { type: 'start' }, { type: 'mute' }, { type: 'heard' })
    expect(s.muted).toBe(true)
    expect(s.phase).toBe('thinking')
    expect(callReducer(s, { type: 'speech_started' })).toEqual({ active: true, phase: 'listening', noSpeech: 0, muted: true })
  })
  it('unmute restores speaking; mute survives hangup and start so it is remembered for the next call', () => {
    const s = step(initialCall, { type: 'start' }, { type: 'mute' }, { type: 'unmute' }, { type: 'heard' }, { type: 'speech_started' })
    expect(s.phase).toBe('speaking')
    const hung = step(initialCall, { type: 'start' }, { type: 'mute' }, { type: 'hangup' })
    expect(hung).toEqual({ active: false, phase: 'idle', noSpeech: 0, muted: true })
    expect(callReducer(hung, { type: 'start' }).muted).toBe(true)
  })
  it('muting while Span is speaking returns to listening at once', () => {
    const speaking = step(initialCall, { type: 'start' }, { type: 'heard' }, { type: 'speech_started' })
    expect(callReducer(speaking, { type: 'mute' })).toEqual({ active: true, phase: 'listening', noSpeech: 0, muted: true })
  })
})
