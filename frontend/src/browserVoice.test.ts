import { describe, expect, it } from 'vitest'
import { approvalChoice, assistantSpeechText, claimSpeechEvent, recognitionErrorMessage, recognitionUnavailableMessage } from './browserVoice'

describe('browser voice helpers', () => {
  it('explains unsupported or insecure speech recognition and recoverable errors', () => {
    expect(recognitionUnavailableMessage()).toMatch(/not available/)
    expect(recognitionUnavailableMessage(false)).toMatch(/localhost or HTTPS/)
    expect(recognitionErrorMessage('not-allowed')).toMatch(/denied/)
    expect(recognitionErrorMessage('no-speech')).toMatch(/No speech/)
  })

  it('claims persisted speech event IDs only once per session', () => {
    const entries = new Map<string, string>()
    const storage = {
      getItem: (key: string) => entries.get(key) ?? null,
      setItem: (key: string, value: string) => { entries.set(key, value) },
    }
    expect(claimSpeechEvent(undefined, storage)).toBe(false)
    expect(claimSpeechEvent('event-1', storage)).toBe(true)
    expect(claimSpeechEvent('event-1', storage)).toBe(false)
    expect(claimSpeechEvent('event-2', storage)).toBe(true)
  })

  it('only returns assistant speech and never caller speech', () => {
    expect(assistantSpeechText({ event: 'speech', data: { text: '  You are covered. ' } })).toBe('You are covered.')
    expect(assistantSpeechText({ event: 'speech', data: { text: 'What do you mean?', kind: 'caller' } })).toBe('')
    expect(assistantSpeechText({ event: 'speech', data: { text: 'What do you mean?', speaker: 'caller' } })).toBe('')
    expect(assistantSpeechText({ event: 'node.update', data: { text: 'Not speech' } })).toBe('')
  })

  it('parses only unambiguous explicit approval and decline choices', () => {
    const options = [
      { id: 'yes', label: 'Yes, text them' },
      { id: 'chase_only', label: "Text, don't touch bills" },
      { id: 'no', label: 'Not now' },
    ]
    expect(approvalChoice('Yes, please.', options)).toBe('yes')
    expect(approvalChoice('not now', options)).toBe('no')
    expect(approvalChoice("text, don't touch bills", options)).toBe('chase_only')
    expect(approvalChoice('Maybe yes, but only if they agree', options)).toBeUndefined()
    expect(approvalChoice('sure', options)).toBeUndefined()
    expect(approvalChoice('yes', [{ id: 'a', label: 'Approve' }, { id: 'b', label: 'Yes please' }])).toBeUndefined()
  })
})
